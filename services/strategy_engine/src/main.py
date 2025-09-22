import os
import sys
import logging
from datetime import datetime, timedelta
import asyncio
from typing import Dict, List, Any

from .strategies import StrategyFactory, StrategyRegistry
from .risk_manager import RiskManager
from .portfolio_optimizer import PortfolioOptimizer
from .signal_generator import SignalGenerator
from .database import DatabaseManager
from .message_queue import MessageQueue
from .config import Config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class StrategyEngineService:
    def __init__(self):
        self.config = Config()
        self.db = DatabaseManager(self.config)
        self.mq = MessageQueue(self.config)

        self.strategy_registry = StrategyRegistry()
        self.strategy_factory = StrategyFactory()
        self.risk_manager = RiskManager(self.config)
        self.portfolio_optimizer = PortfolioOptimizer()
        self.signal_generator = SignalGenerator()

        self._register_strategies()
        self.active_strategies = {}

    def _register_strategies(self):
        """Register all available strategies"""
        from .strategies.momentum import MomentumStrategy
        from .strategies.mean_reversion import MeanReversionStrategy
        from .strategies.pairs_trading import PairsTradingStrategy
        from .strategies.ml_strategy import MachineLearningStrategy
        from .strategies.volatility import VolatilityStrategy
        from .strategies.trend_following import TrendFollowingStrategy

        self.strategy_registry.register('momentum', MomentumStrategy)
        self.strategy_registry.register('mean_reversion', MeanReversionStrategy)
        self.strategy_registry.register('pairs_trading', PairsTradingStrategy)
        self.strategy_registry.register('machine_learning', MachineLearningStrategy)
        self.strategy_registry.register('volatility', VolatilityStrategy)
        self.strategy_registry.register('trend_following', TrendFollowingStrategy)

    def create_strategy_portfolio(self, risk_profile: str, investment_period: str) -> Dict:
        """Create portfolio of strategies based on risk profile and investment period"""

        risk_allocations = {
            'very_safe': {'momentum': 0.1, 'mean_reversion': 0.3, 'trend_following': 0.6},
            'safe': {'momentum': 0.2, 'mean_reversion': 0.3, 'trend_following': 0.5},
            'normal': {'momentum': 0.3, 'mean_reversion': 0.2, 'trend_following': 0.3, 'ml_strategy': 0.2},
            'risky': {'momentum': 0.3, 'volatility': 0.3, 'ml_strategy': 0.2, 'pairs_trading': 0.2},
            'very_risky': {'momentum': 0.2, 'volatility': 0.4, 'ml_strategy': 0.2, 'pairs_trading': 0.2}
        }

        period_adjustments = {
            'ultra_short': {'leverage': 0.5, 'position_size': 0.3},
            'short': {'leverage': 0.7, 'position_size': 0.5},
            'medium': {'leverage': 1.0, 'position_size': 0.7},
            'long': {'leverage': 1.2, 'position_size': 0.9},
            'ultra_long': {'leverage': 1.5, 'position_size': 1.0}
        }

        base_allocation = risk_allocations.get(risk_profile, risk_allocations['normal'])
        adjustments = period_adjustments.get(investment_period, period_adjustments['medium'])

        portfolio = {
            'strategies': {},
            'risk_profile': risk_profile,
            'investment_period': investment_period,
            'adjustments': adjustments
        }

        for strategy_name, weight in base_allocation.items():
            strategy_class = self.strategy_registry.get(strategy_name)
            if strategy_class:
                config = {
                    'weight': weight,
                    'leverage': adjustments['leverage'],
                    'position_size': adjustments['position_size'] * weight,
                    'risk_profile': risk_profile
                }
                portfolio['strategies'][strategy_name] = {
                    'class': strategy_class,
                    'config': config
                }

        return portfolio

    async def run_strategies(self, symbols: List[str], portfolio: Dict) -> Dict:
        """Run all strategies in the portfolio"""
        results = {}

        for strategy_name, strategy_info in portfolio['strategies'].items():
            try:
                strategy = strategy_info['class'](strategy_info['config'])

                market_data = await self.db.get_market_data_async(symbols)

                signals = await strategy.generate_signals(market_data)

                risk_adjusted = self.risk_manager.adjust_signals(
                    signals,
                    portfolio['risk_profile'],
                    market_data
                )

                results[strategy_name] = {
                    'signals': risk_adjusted,
                    'weight': strategy_info['config']['weight'],
                    'timestamp': datetime.now().isoformat()
                }

                logger.info(f"Strategy {strategy_name} generated {len(risk_adjusted)} signals")

            except Exception as e:
                logger.error(f"Error running strategy {strategy_name}: {e}")
                results[strategy_name] = {
                    'error': str(e),
                    'timestamp': datetime.now().isoformat()
                }

        return results

    def combine_signals(self, strategy_results: Dict) -> List[Dict]:
        """Combine signals from multiple strategies"""
        combined_signals = {}

        for strategy_name, result in strategy_results.items():
            if 'error' in result:
                continue

            weight = result['weight']
            for signal in result.get('signals', []):
                symbol = signal['symbol']
                if symbol not in combined_signals:
                    combined_signals[symbol] = {
                        'symbol': symbol,
                        'total_score': 0,
                        'total_weight': 0,
                        'strategies': [],
                        'action': 'HOLD',
                        'position_size': 0
                    }

                combined_signals[symbol]['total_score'] += signal['score'] * weight
                combined_signals[symbol]['total_weight'] += weight
                combined_signals[symbol]['strategies'].append({
                    'name': strategy_name,
                    'signal': signal['action'],
                    'score': signal['score']
                })

        final_signals = []
        for symbol, data in combined_signals.items():
            if data['total_weight'] > 0:
                final_score = data['total_score'] / data['total_weight']

                if final_score > 0.6:
                    action = 'BUY'
                    position_size = min(final_score, 1.0)
                elif final_score < -0.6:
                    action = 'SELL'
                    position_size = min(abs(final_score), 1.0)
                else:
                    action = 'HOLD'
                    position_size = 0

                final_signals.append({
                    'symbol': symbol,
                    'action': action,
                    'score': final_score,
                    'position_size': position_size,
                    'strategies': data['strategies'],
                    'timestamp': datetime.now().isoformat()
                })

        return final_signals

    async def optimize_portfolio(self, signals: List[Dict], constraints: Dict) -> Dict:
        """Optimize portfolio allocation based on signals"""
        symbols = [s['symbol'] for s in signals if s['action'] != 'HOLD']

        if not symbols:
            return {'allocations': {}, 'expected_return': 0, 'risk': 0}

        historical_data = await self.db.get_historical_returns(symbols, days=252)

        optimization_result = self.portfolio_optimizer.optimize(
            historical_data,
            signals,
            constraints
        )

        return optimization_result

    async def process_market_update(self, message: Dict):
        """Process real-time market updates"""
        try:
            symbols = message.get('symbols', [])
            if not symbols:
                return

            for risk_profile in ['very_safe', 'safe', 'normal', 'risky', 'very_risky']:
                for period in ['short', 'medium', 'long']:
                    portfolio = self.create_strategy_portfolio(risk_profile, period)

                    results = await self.run_strategies(symbols, portfolio)

                    combined_signals = self.combine_signals(results)

                    if combined_signals:
                        constraints = {
                            'max_position_size': 0.2,
                            'max_leverage': portfolio['adjustments']['leverage'],
                            'min_positions': 3,
                            'max_positions': 20
                        }

                        optimized = await self.optimize_portfolio(combined_signals, constraints)

                        await self.db.store_signals(combined_signals)
                        await self.db.store_portfolio(optimized)

                        self.mq.publish('signals_generated', {
                            'risk_profile': risk_profile,
                            'period': period,
                            'signals_count': len(combined_signals),
                            'portfolio': optimized,
                            'timestamp': datetime.now().isoformat()
                        })

            logger.info(f"Processed market update for {len(symbols)} symbols")

        except Exception as e:
            logger.error(f"Error processing market update: {e}")

    async def start(self):
        """Start the strategy engine service"""
        logger.info("Starting Strategy Engine Service")

        self.db.initialize()

        def message_handler(message):
            asyncio.create_task(self.process_market_update(message))

        self.mq.consume('market_updates', message_handler)

        while True:
            try:
                await asyncio.sleep(1)
            except KeyboardInterrupt:
                logger.info("Shutting down Strategy Engine Service")
                break
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                await asyncio.sleep(60)


if __name__ == "__main__":
    service = StrategyEngineService()
    asyncio.run(service.start())