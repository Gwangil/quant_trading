from abc import ABC, abstractmethod
from typing import Dict, List, Any
import pandas as pd
import numpy as np


class BaseStrategy(ABC):
    """Base class for all trading strategies"""

    def __init__(self, config: Dict):
        self.config = config
        self.weight = config.get('weight', 1.0)
        self.leverage = config.get('leverage', 1.0)
        self.position_size = config.get('position_size', 0.1)
        self.risk_profile = config.get('risk_profile', 'normal')

    @abstractmethod
    async def generate_signals(self, market_data: pd.DataFrame) -> List[Dict]:
        """Generate trading signals based on market data"""
        pass

    def calculate_score(self, signal_strength: float) -> float:
        """Calculate normalized score (-1 to 1)"""
        return np.clip(signal_strength, -1.0, 1.0)

    def create_signal(self, symbol: str, action: str, score: float, metadata: Dict = None) -> Dict:
        """Create standardized signal dictionary"""
        signal = {
            'symbol': symbol,
            'action': action,
            'score': self.calculate_score(score),
            'strategy': self.__class__.__name__,
            'position_size': self.position_size * abs(score),
            'leverage': self.leverage
        }

        if metadata:
            signal['metadata'] = metadata

        return signal


class StrategyRegistry:
    """Registry for managing available strategies"""

    def __init__(self):
        self._strategies = {}

    def register(self, name: str, strategy_class):
        """Register a strategy"""
        self._strategies[name] = strategy_class

    def get(self, name: str):
        """Get strategy class by name"""
        return self._strategies.get(name)

    def list_strategies(self) -> List[str]:
        """List all registered strategies"""
        return list(self._strategies.keys())


class StrategyFactory:
    """Factory for creating strategy instances"""

    def __init__(self):
        self.registry = StrategyRegistry()

    def create(self, strategy_name: str, config: Dict) -> BaseStrategy:
        """Create strategy instance"""
        strategy_class = self.registry.get(strategy_name)
        if not strategy_class:
            raise ValueError(f"Unknown strategy: {strategy_name}")

        return strategy_class(config)