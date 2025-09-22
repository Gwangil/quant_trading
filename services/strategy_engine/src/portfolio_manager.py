import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class RiskProfile(Enum):
    VERY_SAFE = "very_safe"
    SAFE = "safe"
    NORMAL = "normal"
    RISKY = "risky"
    VERY_RISKY = "very_risky"


class InvestmentPeriod(Enum):
    ULTRA_SHORT = "ultra_short"  # 1-5 days
    SHORT = "short"              # 1-4 weeks
    MEDIUM = "medium"            # 1-3 months
    LONG = "long"                # 3-12 months
    ULTRA_LONG = "ultra_long"    # 1+ years


@dataclass
class StrategyConfig:
    """Configuration for a single strategy instance"""
    name: str
    strategy_type: str
    risk_profile: RiskProfile
    investment_period: InvestmentPeriod
    allocation: float  # Portfolio allocation percentage
    parameters: Dict
    active: bool = True
    rebalance_frequency: int = 30  # days
    max_position_size: float = 0.2
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

    def to_dict(self):
        data = asdict(self)
        data['risk_profile'] = self.risk_profile.value
        data['investment_period'] = self.investment_period.value
        return data


@dataclass
class PortfolioConfig:
    """Configuration for entire portfolio with multiple strategies"""
    name: str
    total_capital: float
    strategies: List[StrategyConfig]
    rebalance_frequency: int = 7  # days
    max_strategies: int = 10
    created_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()

        # Validate allocations sum to 1.0 or less
        total_allocation = sum(s.allocation for s in self.strategies if s.active)
        if total_allocation > 1.0:
            raise ValueError(f"Total allocation {total_allocation} exceeds 100%")


class MultiStrategyPortfolio:
    """Manages multiple strategies with different timeframes simultaneously"""

    def __init__(self, config: PortfolioConfig):
        self.config = config
        self.active_strategies = {}
        self.strategy_performance = {}
        self.positions = {}
        self.cash = config.total_capital
        self.last_rebalance = datetime.now()

    def add_strategy(self, strategy_config: StrategyConfig):
        """Add a new strategy to the portfolio"""
        if len(self.active_strategies) >= self.config.max_strategies:
            raise ValueError(f"Maximum {self.config.max_strategies} strategies allowed")

        # Check total allocation
        current_allocation = sum(s.allocation for s in self.config.strategies if s.active)
        if current_allocation + strategy_config.allocation > 1.0:
            raise ValueError(f"Adding this strategy would exceed 100% allocation")

        self.config.strategies.append(strategy_config)
        self.active_strategies[strategy_config.name] = strategy_config
        logger.info(f"Added strategy: {strategy_config.name}")

    def remove_strategy(self, strategy_name: str):
        """Remove a strategy and liquidate its positions"""
        if strategy_name in self.active_strategies:
            # Mark as inactive
            self.active_strategies[strategy_name].active = False

            # Liquidate positions
            self._liquidate_strategy_positions(strategy_name)

            del self.active_strategies[strategy_name]
            logger.info(f"Removed strategy: {strategy_name}")

    def allocate_capital(self) -> Dict[str, float]:
        """Allocate capital to each active strategy"""
        allocations = {}

        for strategy in self.config.strategies:
            if strategy.active:
                allocations[strategy.name] = self.config.total_capital * strategy.allocation

        return allocations

    def rebalance(self, current_prices: Dict[str, float]):
        """Rebalance portfolio allocations"""
        days_since_rebalance = (datetime.now() - self.last_rebalance).days

        if days_since_rebalance < self.config.rebalance_frequency:
            return

        logger.info("Starting portfolio rebalance")

        # Calculate current portfolio value
        portfolio_value = self._calculate_portfolio_value(current_prices)

        # Calculate target allocations
        target_allocations = self.allocate_capital()

        # Calculate current allocations
        current_allocations = self._calculate_current_allocations(current_prices)

        # Generate rebalancing orders
        rebalance_orders = self._generate_rebalance_orders(
            target_allocations,
            current_allocations,
            current_prices
        )

        self.last_rebalance = datetime.now()

        return rebalance_orders

    def _calculate_portfolio_value(self, current_prices: Dict[str, float]) -> float:
        """Calculate total portfolio value"""
        value = self.cash

        for position in self.positions.values():
            if position['symbol'] in current_prices:
                value += position['quantity'] * current_prices[position['symbol']]

        return value

    def _calculate_current_allocations(self, current_prices: Dict[str, float]) -> Dict[str, float]:
        """Calculate current strategy allocations"""
        allocations = {}

        for strategy_name in self.active_strategies:
            strategy_value = 0

            for position in self.positions.values():
                if position['strategy'] == strategy_name and position['symbol'] in current_prices:
                    strategy_value += position['quantity'] * current_prices[position['symbol']]

            allocations[strategy_name] = strategy_value

        return allocations

    def _generate_rebalance_orders(self, target: Dict, current: Dict, prices: Dict) -> List[Dict]:
        """Generate orders to rebalance portfolio"""
        orders = []

        for strategy_name, target_value in target.items():
            current_value = current.get(strategy_name, 0)
            diff = target_value - current_value

            if abs(diff) > target_value * 0.05:  # 5% threshold
                if diff > 0:
                    # Need to buy more
                    orders.append({
                        'strategy': strategy_name,
                        'action': 'REBALANCE_BUY',
                        'value': diff,
                        'timestamp': datetime.now()
                    })
                else:
                    # Need to sell some
                    orders.append({
                        'strategy': strategy_name,
                        'action': 'REBALANCE_SELL',
                        'value': abs(diff),
                        'timestamp': datetime.now()
                    })

        return orders

    def _liquidate_strategy_positions(self, strategy_name: str):
        """Liquidate all positions for a strategy"""
        positions_to_liquidate = [
            p for p in self.positions.values()
            if p['strategy'] == strategy_name
        ]

        for position in positions_to_liquidate:
            # Mark for liquidation
            position['status'] = 'LIQUIDATE'

        logger.info(f"Marked {len(positions_to_liquidate)} positions for liquidation")


class StrategyScheduler:
    """Manages strategy execution based on investment periods"""

    def __init__(self):
        self.schedules = {}
        self.execution_history = {}

    def schedule_strategy(self, strategy_config: StrategyConfig):
        """Schedule strategy execution based on investment period"""

        period_to_days = {
            InvestmentPeriod.ULTRA_SHORT: 3,
            InvestmentPeriod.SHORT: 14,
            InvestmentPeriod.MEDIUM: 60,
            InvestmentPeriod.LONG: 180,
            InvestmentPeriod.ULTRA_LONG: 365
        }

        execution_frequency = period_to_days[strategy_config.investment_period]

        self.schedules[strategy_config.name] = {
            'frequency': execution_frequency,
            'last_execution': None,
            'next_execution': datetime.now(),
            'strategy_config': strategy_config
        }

    def get_strategies_to_execute(self) -> List[StrategyConfig]:
        """Get strategies that need to be executed now"""
        strategies_to_run = []
        current_time = datetime.now()

        for name, schedule in self.schedules.items():
            if schedule['next_execution'] <= current_time:
                strategies_to_run.append(schedule['strategy_config'])

                # Update schedule
                schedule['last_execution'] = current_time
                schedule['next_execution'] = current_time + timedelta(days=schedule['frequency'])

                # Record execution
                if name not in self.execution_history:
                    self.execution_history[name] = []
                self.execution_history[name].append(current_time)

        return strategies_to_run

    def get_execution_stats(self, strategy_name: str) -> Dict:
        """Get execution statistics for a strategy"""
        if strategy_name not in self.execution_history:
            return {}

        executions = self.execution_history[strategy_name]

        return {
            'total_executions': len(executions),
            'first_execution': executions[0] if executions else None,
            'last_execution': executions[-1] if executions else None,
            'avg_frequency': self._calculate_avg_frequency(executions)
        }

    def _calculate_avg_frequency(self, executions: List[datetime]) -> float:
        """Calculate average execution frequency in days"""
        if len(executions) < 2:
            return 0

        intervals = []
        for i in range(1, len(executions)):
            interval = (executions[i] - executions[i-1]).days
            intervals.append(interval)

        return sum(intervals) / len(intervals) if intervals else 0


class PerformanceTracker:
    """Track performance of multiple strategies over time"""

    def __init__(self):
        self.performance_data = {}
        self.cumulative_returns = {}

    def record_trade(self, strategy_name: str, trade: Dict):
        """Record a trade for performance tracking"""
        if strategy_name not in self.performance_data:
            self.performance_data[strategy_name] = {
                'trades': [],
                'returns': [],
                'positions': []
            }

        self.performance_data[strategy_name]['trades'].append(trade)

        if 'return' in trade:
            self.performance_data[strategy_name]['returns'].append(trade['return'])

    def calculate_strategy_metrics(self, strategy_name: str, period_days: int = None) -> Dict:
        """Calculate performance metrics for a strategy"""
        if strategy_name not in self.performance_data:
            return {}

        data = self.performance_data[strategy_name]
        returns = data['returns']

        if not returns:
            return {}

        # Filter by period if specified
        if period_days:
            cutoff_date = datetime.now() - timedelta(days=period_days)
            filtered_trades = [
                t for t in data['trades']
                if t.get('timestamp', datetime.now()) > cutoff_date
            ]
            returns = [t.get('return', 0) for t in filtered_trades if 'return' in t]

        returns_array = np.array(returns)

        metrics = {
            'total_return': np.sum(returns_array),
            'avg_return': np.mean(returns_array),
            'std_return': np.std(returns_array),
            'sharpe_ratio': self._calculate_sharpe(returns_array),
            'max_drawdown': self._calculate_max_drawdown(returns_array),
            'win_rate': len([r for r in returns if r > 0]) / len(returns) if returns else 0,
            'profit_factor': self._calculate_profit_factor(returns_array),
            'num_trades': len(data['trades'])
        }

        return metrics

    def calculate_portfolio_metrics(self, strategies: List[str]) -> Dict:
        """Calculate combined portfolio metrics"""
        all_returns = []

        for strategy in strategies:
            if strategy in self.performance_data:
                all_returns.extend(self.performance_data[strategy]['returns'])

        if not all_returns:
            return {}

        returns_array = np.array(all_returns)

        return {
            'total_return': np.sum(returns_array),
            'avg_return': np.mean(returns_array),
            'std_return': np.std(returns_array),
            'sharpe_ratio': self._calculate_sharpe(returns_array),
            'max_drawdown': self._calculate_max_drawdown(returns_array),
            'total_trades': len(all_returns)
        }

    def _calculate_sharpe(self, returns: np.ndarray, risk_free_rate: float = 0.02) -> float:
        """Calculate Sharpe ratio"""
        if len(returns) == 0:
            return 0

        excess_returns = returns - risk_free_rate / 252  # Daily risk-free rate
        return np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(252) if np.std(excess_returns) > 0 else 0

    def _calculate_max_drawdown(self, returns: np.ndarray) -> float:
        """Calculate maximum drawdown"""
        cumulative = np.cumprod(1 + returns)
        running_max = np.maximum.accumulate(cumulative)
        drawdown = (cumulative - running_max) / running_max
        return np.min(drawdown)

    def _calculate_profit_factor(self, returns: np.ndarray) -> float:
        """Calculate profit factor"""
        profits = returns[returns > 0]
        losses = abs(returns[returns < 0])

        if len(losses) == 0:
            return float('inf') if len(profits) > 0 else 0

        return np.sum(profits) / np.sum(losses) if np.sum(losses) > 0 else float('inf')


class MultiPeriodBacktester:
    """Backtest strategies with automatic period-based repetition"""

    def __init__(self, initial_capital: float = 100000):
        self.initial_capital = initial_capital
        self.portfolio_manager = None
        self.scheduler = StrategyScheduler()
        self.performance_tracker = PerformanceTracker()

    def run_multiperiod_backtest(self,
                                 portfolio_config: PortfolioConfig,
                                 market_data: pd.DataFrame,
                                 start_date: datetime,
                                 end_date: datetime) -> Dict:
        """
        Run backtest with automatic strategy repetition based on investment periods

        Short-term strategies will be executed multiple times during the backtest period
        Long-term strategies will be held for the entire period
        """

        # Initialize portfolio
        self.portfolio_manager = MultiStrategyPortfolio(portfolio_config)

        # Schedule all strategies
        for strategy in portfolio_config.strategies:
            self.scheduler.schedule_strategy(strategy)

        # Prepare results storage
        results = {
            'portfolio_value': [],
            'strategy_results': {},
            'trades': [],
            'final_metrics': {}
        }

        # Convert market data to daily format
        daily_dates = pd.date_range(start=start_date, end=end_date, freq='D')

        for current_date in daily_dates:
            # Get current market prices
            current_prices = self._get_current_prices(market_data, current_date)

            if not current_prices:
                continue

            # Get strategies to execute today
            strategies_to_execute = self.scheduler.get_strategies_to_execute()

            for strategy_config in strategies_to_execute:
                # Execute strategy
                trades = self._execute_strategy(
                    strategy_config,
                    market_data,
                    current_date,
                    current_prices
                )

                # Record trades
                for trade in trades:
                    self.performance_tracker.record_trade(strategy_config.name, trade)
                    results['trades'].append(trade)

            # Check for rebalancing
            rebalance_orders = self.portfolio_manager.rebalance(current_prices)

            # Record portfolio value
            portfolio_value = self.portfolio_manager._calculate_portfolio_value(current_prices)
            results['portfolio_value'].append({
                'date': current_date,
                'value': portfolio_value,
                'return': (portfolio_value - self.initial_capital) / self.initial_capital
            })

        # Calculate final metrics for each strategy
        for strategy in portfolio_config.strategies:
            strategy_metrics = self.performance_tracker.calculate_strategy_metrics(
                strategy.name
            )
            results['strategy_results'][strategy.name] = {
                'config': strategy.to_dict(),
                'metrics': strategy_metrics,
                'execution_stats': self.scheduler.get_execution_stats(strategy.name)
            }

        # Calculate portfolio-level metrics
        results['final_metrics'] = self.performance_tracker.calculate_portfolio_metrics(
            [s.name for s in portfolio_config.strategies]
        )

        return results

    def _get_current_prices(self, market_data: pd.DataFrame, date: datetime) -> Dict[str, float]:
        """Get current market prices for a given date"""
        day_data = market_data[market_data['date'].dt.date == date.date()]

        if day_data.empty:
            return {}

        prices = {}
        for symbol in day_data['symbol'].unique():
            symbol_data = day_data[day_data['symbol'] == symbol]
            if not symbol_data.empty:
                prices[symbol] = symbol_data.iloc[-1]['close']

        return prices

    def _execute_strategy(self,
                         strategy_config: StrategyConfig,
                         market_data: pd.DataFrame,
                         current_date: datetime,
                         current_prices: Dict[str, float]) -> List[Dict]:
        """Execute a single strategy and return trades"""

        # This is a simplified version - would integrate with actual strategy classes
        trades = []

        # Example trade generation based on strategy type and period
        if strategy_config.strategy_type == 'momentum':
            # Short-term momentum trades
            if strategy_config.investment_period in [InvestmentPeriod.ULTRA_SHORT, InvestmentPeriod.SHORT]:
                # Generate more frequent trades
                trade = {
                    'strategy': strategy_config.name,
                    'date': current_date,
                    'symbol': 'SPY',  # Example
                    'action': 'BUY',
                    'quantity': 100,
                    'price': current_prices.get('SPY', 100),
                    'return': np.random.normal(0.001, 0.02)  # Simulated return
                }
                trades.append(trade)

        return trades