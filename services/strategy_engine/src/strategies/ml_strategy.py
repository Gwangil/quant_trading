import pandas as pd
import numpy as np
from typing import List, Dict
from sklearn.ensemble import RandomForestClassifier, GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
import ta
import joblib
import os

from . import BaseStrategy


class MachineLearningStrategy(BaseStrategy):
    """Machine learning based trading strategy"""

    def __init__(self, config: Dict):
        super().__init__(config)
        self.lookback_period = config.get('lookback_period', 30)
        self.prediction_horizon = config.get('prediction_horizon', 5)
        self.model_type = config.get('model_type', 'ensemble')
        self.retrain_frequency = config.get('retrain_frequency', 30)
        self.min_confidence = config.get('min_confidence', 0.6)

        self.classifier = None
        self.regressor = None
        self.scaler = StandardScaler()
        self.last_train_date = None

    def _create_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Create technical indicator features for ML model"""
        features = pd.DataFrame(index=df.index)

        features['returns'] = df['close'].pct_change()
        for period in [5, 10, 20, 50]:
            features[f'returns_{period}'] = df['close'].pct_change(period)
            features[f'ma_{period}'] = df['close'].rolling(window=period).mean() / df['close']
            features[f'volume_ma_{period}'] = df['volume'].rolling(window=period).mean() / df['volume']

        features['rsi'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
        features['macd'] = ta.trend.MACD(df['close']).macd()
        features['macd_signal'] = ta.trend.MACD(df['close']).macd_signal()

        bb = ta.volatility.BollingerBands(df['close'])
        features['bb_pband'] = bb.bollinger_pband()
        features['bb_width'] = bb.bollinger_wband()

        features['atr'] = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close']).average_true_range()
        features['volatility'] = df['returns'].rolling(window=20).std()

        features['obv'] = ta.volume.OnBalanceVolumeIndicator(df['close'], df['volume']).on_balance_volume()
        features['adx'] = ta.trend.ADXIndicator(df['high'], df['low'], df['close']).adx()

        features['hl_ratio'] = (df['high'] - df['low']) / df['close']
        features['co_ratio'] = (df['close'] - df['open']) / df['open']

        for lag in range(1, 6):
            features[f'returns_lag_{lag}'] = features['returns'].shift(lag)

        features['day_of_week'] = pd.to_datetime(df.index).dayofweek
        features['month'] = pd.to_datetime(df.index).month

        return features

    def _prepare_training_data(self, df: pd.DataFrame, features: pd.DataFrame):
        """Prepare data for training"""
        future_returns = df['close'].pct_change(self.prediction_horizon).shift(-self.prediction_horizon)

        y_class = (future_returns > 0.01).astype(int)
        y_class[future_returns < -0.01] = -1

        y_reg = future_returns

        features_clean = features.dropna()
        y_class = y_class[features_clean.index]
        y_reg = y_reg[features_clean.index]

        mask = ~(y_class.isna() | y_reg.isna())
        X = features_clean[mask]
        y_class = y_class[mask]
        y_reg = y_reg[mask]

        return X, y_class, y_reg

    def _train_models(self, X, y_class, y_reg):
        """Train ML models"""
        X_scaled = self.scaler.fit_transform(X)

        self.classifier = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            min_samples_split=20,
            random_state=42
        )
        self.classifier.fit(X_scaled, y_class)

        self.regressor = GradientBoostingRegressor(
            n_estimators=100,
            learning_rate=0.1,
            max_depth=5,
            random_state=42
        )
        self.regressor.fit(X_scaled, y_reg)

        self.last_train_date = pd.Timestamp.now()

    async def generate_signals(self, market_data: pd.DataFrame) -> List[Dict]:
        """Generate ML-based trading signals"""
        signals = []

        symbols = market_data['symbol'].unique()

        for symbol in symbols:
            df = market_data[market_data['symbol'] == symbol].copy()

            if len(df) < 200:
                continue

            df = df.sort_values('date').set_index('date')

            features = self._create_features(df)

            if self.classifier is None or self._should_retrain():
                X_train, y_class_train, y_reg_train = self._prepare_training_data(
                    df.iloc[:-self.lookback_period],
                    features.iloc[:-self.lookback_period]
                )

                if len(X_train) > 100:
                    self._train_models(X_train, y_class_train, y_reg_train)

            if self.classifier is None:
                continue

            latest_features = features.iloc[-1:].dropna(axis=1)
            if latest_features.empty:
                continue

            try:
                X_scaled = self.scaler.transform(latest_features)

                class_proba = self.classifier.predict_proba(X_scaled)[0]
                reg_pred = self.regressor.predict(X_scaled)[0]

                confidence = max(class_proba)
                predicted_class = self.classifier.predict(X_scaled)[0]

                score = 0
                metadata = {
                    'confidence': float(confidence),
                    'predicted_return': float(reg_pred),
                    'feature_importance': self._get_top_features(latest_features)
                }

                if confidence >= self.min_confidence:
                    if predicted_class == 1:
                        score = confidence * (1 + abs(reg_pred))
                        metadata['ml_signal'] = 'bullish'
                    elif predicted_class == -1:
                        score = -confidence * (1 + abs(reg_pred))
                        metadata['ml_signal'] = 'bearish'

                    score = np.clip(score, -1.0, 1.0)

                if abs(score) > 0.1:
                    action = 'BUY' if score > 0 else 'SELL'
                    signal = self.create_signal(symbol, action, score, metadata)
                    signals.append(signal)

            except Exception as e:
                continue

        return signals

    def _should_retrain(self) -> bool:
        """Check if model should be retrained"""
        if self.last_train_date is None:
            return True

        days_since_train = (pd.Timestamp.now() - self.last_train_date).days
        return days_since_train >= self.retrain_frequency

    def _get_top_features(self, features: pd.DataFrame) -> List[str]:
        """Get top important features"""
        if self.classifier is None or not hasattr(self.classifier, 'feature_importances_'):
            return []

        importances = self.classifier.feature_importances_
        feature_names = features.columns.tolist()

        feature_importance = list(zip(feature_names, importances))
        feature_importance.sort(key=lambda x: x[1], reverse=True)

        return [f[0] for f in feature_importance[:5]]