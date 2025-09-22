import pandas as pd
import numpy as np
from typing import List, Dict
import ta

from . import BaseStrategy


class MomentumStrategy(BaseStrategy):
    """Momentum-based trading strategy"""

    def __init__(self, config: Dict):
        super().__init__(config)
        self.rsi_period = config.get('rsi_period', 14)
        self.rsi_overbought = config.get('rsi_overbought', 70)
        self.rsi_oversold = config.get('rsi_oversold', 30)
        self.ma_short = config.get('ma_short', 20)
        self.ma_long = config.get('ma_long', 50)
        self.volume_factor = config.get('volume_factor', 1.5)

    async def generate_signals(self, market_data: pd.DataFrame) -> List[Dict]:
        """Generate momentum-based trading signals"""
        signals = []

        symbols = market_data['symbol'].unique()

        for symbol in symbols:
            df = market_data[market_data['symbol'] == symbol].copy()

            if len(df) < self.ma_long:
                continue

            df = df.sort_values('date')

            df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=self.rsi_period).rsi()

            df['ma_short'] = df['close'].rolling(window=self.ma_short).mean()
            df['ma_long'] = df['close'].rolling(window=self.ma_long).mean()

            df['returns'] = df['close'].pct_change()
            df['momentum'] = df['returns'].rolling(window=20).mean()

            df['volume_ma'] = df['volume'].rolling(window=20).mean()
            df['volume_ratio'] = df['volume'] / df['volume_ma']

            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else latest

            score = 0
            metadata = {}

            if pd.notna(latest['rsi']):
                if latest['rsi'] < self.rsi_oversold:
                    score += 0.3
                    metadata['rsi_signal'] = 'oversold'
                elif latest['rsi'] > self.rsi_overbought:
                    score -= 0.3
                    metadata['rsi_signal'] = 'overbought'

            if pd.notna(latest['ma_short']) and pd.notna(latest['ma_long']):
                if latest['ma_short'] > latest['ma_long'] and prev['ma_short'] <= prev['ma_long']:
                    score += 0.4
                    metadata['ma_crossover'] = 'golden_cross'
                elif latest['ma_short'] < latest['ma_long'] and prev['ma_short'] >= prev['ma_long']:
                    score -= 0.4
                    metadata['ma_crossover'] = 'death_cross'

            if pd.notna(latest['momentum']):
                if latest['momentum'] > 0.01:
                    score += latest['momentum'] * 10
                    metadata['momentum'] = 'positive'
                elif latest['momentum'] < -0.01:
                    score += latest['momentum'] * 10
                    metadata['momentum'] = 'negative'

            if pd.notna(latest['volume_ratio']):
                if latest['volume_ratio'] > self.volume_factor:
                    score *= 1.2
                    metadata['volume'] = 'high'

            recent_volatility = df['returns'].tail(20).std()
            if pd.notna(recent_volatility):
                if recent_volatility > 0.03:
                    score *= 0.8
                    metadata['volatility'] = 'high'

            if abs(score) > 0.1:
                action = 'BUY' if score > 0 else 'SELL'
                signal = self.create_signal(symbol, action, score, metadata)
                signals.append(signal)

        return signals