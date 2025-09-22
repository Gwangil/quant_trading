import pandas as pd
import numpy as np
from typing import Dict, List, Any
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class Position:
    """Represents a trading position"""
    def __init__(self, symbol: str, quantity: int, entry_price: float, entry_date: datetime):
        self.symbol = symbol
        self.quantity = quantity
        self.entry_price = entry_price
        self.entry_date = entry_date
        self.exit_price = None
        self.exit_date = None
        self.pnl = 0
        self.pnl_pct = 0


class Portfolio:
    """Portfolio management for backtesting"""
    def __init__(self, initial_capital: float):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions = {}
        self.closed_positions = []
        self.equity_curve = []
        self.trades = []

    def buy(self, symbol: str, price: float, quantity: int, date: datetime) -> bool:
        """Execute buy order"""
        cost = price * quantity

        if cost > self.cash:
            return False

        self.cash -= cost

        if symbol in self.positions:
            existing = self.positions[symbol]
            total_quantity = existing.quantity + quantity
            avg_price = (existing.entry_price * existing.quantity + price * quantity) / total_quantity
            existing.quantity = total_quantity
            existing.entry_price = avg_price
        else:
            self.positions[symbol] = Position(symbol, quantity, price, date)

        self.trades.append({
            'date': date,
            'symbol': symbol,
            'action': 'BUY',
            'quantity': quantity,
            'price': price,
            'value': cost
        })

        return True

    def sell(self, symbol: str, price: float, quantity: int, date: datetime) -> bool:
        """Execute sell order"""
        if symbol not in self.positions:
            return False

        position = self.positions[symbol]

        if quantity > position.quantity:
            quantity = position.quantity

        proceeds = price * quantity
        self.cash += proceeds

        cost_basis = position.entry_price * quantity
        pnl = proceeds - cost_basis
        pnl_pct = (price - position.entry_price) / position.entry_price

        if quantity == position.quantity:
            position.exit_price = price
            position.exit_date = date
            position.pnl = pnl
            position.pnl_pct = pnl_pct
            self.closed_positions.append(position)
            del self.positions[symbol]
        else:
            position.quantity -= quantity

        self.trades.append({
            'date': date,
            'symbol': symbol,
            'action': 'SELL',
            'quantity': quantity,
            'price': price,
            'value': proceeds,
            'pnl': pnl,
            'pnl_pct': pnl_pct
        })

        return True

    def get_portfolio_value(self, prices: Dict[str, float]) -> float:
        """Calculate total portfolio value"""
        value = self.cash

        for symbol, position in self.positions.items():
            if symbol in prices:
                value += position.quantity * prices[symbol]

        return value

    def update_equity_curve(self, date: datetime, prices: Dict[str, float]):
        """Update equity curve"""
        value = self.get_portfolio_value(prices)
        self.equity_curve.append({
            'date': date,
            'value': value,
            'cash': self.cash,
            'positions_value': value - self.cash,
            'return': (value - self.initial_capital) / self.initial_capital
        })


class Backtester:
    """Main backtesting engine"""

    def __init__(self):
        self.strategies = {}
        self._register_strategies()

    def _register_strategies(self):
        """Register available strategies for backtesting"""
        from .strategies import (
            MomentumBacktestStrategy,
            MeanReversionBacktestStrategy,
            BuyAndHoldStrategy
        )

        self.strategies['momentum'] = MomentumBacktestStrategy
        self.strategies['mean_reversion'] = MeanReversionBacktestStrategy
        self.strategies['buy_and_hold'] = BuyAndHoldStrategy

    def run(self, strategy_name: str, market_data: pd.DataFrame,
            initial_capital: float, parameters: Dict) -> Dict:
        """Run backtest with specified strategy"""

        if strategy_name not in self.strategies:
            raise ValueError(f"Unknown strategy: {strategy_name}")

        strategy_class = self.strategies[strategy_name]
        strategy = strategy_class(parameters)

        portfolio = Portfolio(initial_capital)

        market_data = market_data.sort_values('date')
        dates = market_data['date'].unique()

        for date in dates:
            daily_data = market_data[market_data['date'] == date]

            current_prices = {}
            for _, row in daily_data.iterrows():
                current_prices[row['symbol']] = row['close']

            signals = strategy.generate_signals(daily_data, portfolio)

            for signal in signals:
                self._execute_signal(signal, portfolio, current_prices, date)

            portfolio.update_equity_curve(date, current_prices)

        for symbol in list(portfolio.positions.keys()):
            if symbol in current_prices:
                portfolio.sell(symbol, current_prices[symbol],
                             portfolio.positions[symbol].quantity, date)

        return self._compile_results(portfolio)

    def _execute_signal(self, signal: Dict, portfolio: Portfolio,
                       prices: Dict[str, float], date: datetime):
        """Execute trading signal"""
        symbol = signal['symbol']
        action = signal['action']

        if symbol not in prices:
            return

        price = prices[symbol]

        if action == 'BUY':
            position_size = signal.get('position_size', 0.1)
            value = portfolio.cash * position_size
            quantity = int(value / price)

            if quantity > 0:
                portfolio.buy(symbol, price, quantity, date)

        elif action == 'SELL':
            if symbol in portfolio.positions:
                quantity = portfolio.positions[symbol].quantity
                portfolio.sell(symbol, price, quantity, date)

    def _compile_results(self, portfolio: Portfolio) -> Dict:
        """Compile backtest results"""
        equity_df = pd.DataFrame(portfolio.equity_curve)
        trades_df = pd.DataFrame(portfolio.trades)

        if not equity_df.empty:
            total_return = equity_df['return'].iloc[-1]
            max_drawdown = self._calculate_max_drawdown(equity_df['value'])
        else:
            total_return = 0
            max_drawdown = 0

        winning_trades = [t for t in portfolio.trades if t.get('pnl', 0) > 0]
        losing_trades = [t for t in portfolio.trades if t.get('pnl', 0) < 0]

        results = {
            'initial_capital': portfolio.initial_capital,
            'final_value': portfolio.get_portfolio_value({}) if portfolio.equity_curve else portfolio.initial_capital,
            'total_return': total_return,
            'max_drawdown': max_drawdown,
            'total_trades': len(portfolio.trades),
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'win_rate': len(winning_trades) / len(portfolio.trades) if portfolio.trades else 0,
            'equity_curve': portfolio.equity_curve,
            'trades': portfolio.trades,
            'closed_positions': [self._position_to_dict(p) for p in portfolio.closed_positions]
        }

        return results

    def _calculate_max_drawdown(self, values: pd.Series) -> float:
        """Calculate maximum drawdown"""
        cummax = values.expanding().max()
        drawdown = (values - cummax) / cummax
        return drawdown.min()

    def _position_to_dict(self, position: Position) -> Dict:
        """Convert position to dictionary"""
        return {
            'symbol': position.symbol,
            'quantity': position.quantity,
            'entry_price': position.entry_price,
            'entry_date': position.entry_date,
            'exit_price': position.exit_price,
            'exit_date': position.exit_date,
            'pnl': position.pnl,
            'pnl_pct': position.pnl_pct
        }