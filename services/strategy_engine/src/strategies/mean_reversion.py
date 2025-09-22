import pandas as pd
import numpy as np
from typing import List, Dict
import ta

from . import BaseStrategy


class MeanReversionStrategy(BaseStrategy):
    """Mean reversion trading strategy"""

    def __init__(self, config: Dict):
        super().__init__(config)
        self.bb_window = config.get('bb_window', 20)
        self.bb_std = config.get('bb_std', 2)
        self.z_score_threshold = config.get('z_score_threshold', 2.0)
        self.lookback_period = config.get('lookback_period', 60)

    async def generate_signals(self, market_data: pd.DataFrame) -> List[Dict]:
        """Generate mean reversion trading signals"""
        signals = []

        symbols = market_data['symbol'].unique()

        for symbol in symbols:
            df = market_data[market_data['symbol'] == symbol].copy()

            if len(df) < self.lookback_period:
                continue

            df = df.sort_values('date')

            bb = ta.volatility.BollingerBands(
                close=df['close'],
                window=self.bb_window,
                window_dev=self.bb_std
            )
            df['bb_upper'] = bb.bollinger_hband()
            df['bb_middle'] = bb.bollinger_mavg()
            df['bb_lower'] = bb.bollinger_lband()
            df['bb_width'] = bb.bollinger_wband()
            df['bb_pband'] = bb.bollinger_pband()

            df['returns'] = df['close'].pct_change()
            rolling_mean = df['returns'].rolling(window=self.lookback_period).mean()
            rolling_std = df['returns'].rolling(window=self.lookback_period).std()
            df['z_score'] = (df['returns'] - rolling_mean) / rolling_std

            df['price_mean'] = df['close'].rolling(window=self.lookback_period).mean()
            df['price_std'] = df['close'].rolling(window=self.lookback_period).std()
            df['price_z'] = (df['close'] - df['price_mean']) / df['price_std']

            latest = df.iloc[-1]

            score = 0
            metadata = {}

            if pd.notna(latest['bb_pband']):
                if latest['bb_pband'] < 0:
                    score += 0.4
                    metadata['bb_signal'] = 'below_lower_band'
                elif latest['bb_pband'] > 1:
                    score -= 0.4
                    metadata['bb_signal'] = 'above_upper_band'

                if 0.4 < latest['bb_pband'] < 0.6:
                    if df['bb_pband'].iloc[-5:].mean() < 0.3:
                        score += 0.2
                        metadata['bb_trend'] = 'returning_to_mean_from_below'
                    elif df['bb_pband'].iloc[-5:].mean() > 0.7:
                        score -= 0.2
                        metadata['bb_trend'] = 'returning_to_mean_from_above'

            if pd.notna(latest['z_score']):
                if latest['z_score'] < -self.z_score_threshold:
                    score += 0.3
                    metadata['z_score_signal'] = 'extreme_negative'
                elif latest['z_score'] > self.z_score_threshold:
                    score -= 0.3
                    metadata['z_score_signal'] = 'extreme_positive'

            if pd.notna(latest['price_z']):
                if latest['price_z'] < -2:
                    score += 0.3
                    metadata['price_deviation'] = 'significantly_below_mean'
                elif latest['price_z'] > 2:
                    score -= 0.3
                    metadata['price_deviation'] = 'significantly_above_mean'

            recent_returns = df['returns'].tail(5)
            if len(recent_returns) == 5:
                if (recent_returns < 0).all():
                    score += 0.2
                    metadata['recent_trend'] = 'oversold'
                elif (recent_returns > 0).all():
                    score -= 0.2
                    metadata['recent_trend'] = 'overbought'

            if pd.notna(latest['bb_width']):
                avg_width = df['bb_width'].rolling(window=20).mean().iloc[-1]
                if pd.notna(avg_width) and latest['bb_width'] > avg_width * 1.5:
                    score *= 0.7
                    metadata['volatility'] = 'expanding'

            if abs(score) > 0.2:
                action = 'BUY' if score > 0 else 'SELL'
                signal = self.create_signal(symbol, action, score, metadata)
                signals.append(signal)

        return signals