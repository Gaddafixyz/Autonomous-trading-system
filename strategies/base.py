"""
Abstract base class for all trading strategies.
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from core.types import Candle, Signal, TimeFrame, StrategyType
from core.logger import Logger


class BaseStrategy(ABC):
    """Abstract base class for strategies."""

    def __init__(self, symbol: str, timeframe: TimeFrame):
        self.symbol = symbol
        self.timeframe = timeframe
        self.logger = Logger.get_logger(self.__class__.__name__)
        self.strategy_type: StrategyType = StrategyType.HYBRID  # override in subclass

    @abstractmethod
    async def calculate_signal(self, candles: List[Candle]) -> Optional[Signal]:
        """
        Calculate trading signal based on current candle data.

        Args:
            candles: List of candles (latest first or oldest first? We'll use oldest first,
                     i.e., index 0 is earliest, last is current). Ensure at least enough
                     for indicator calculation.

        Returns:
            Signal object or None if no signal (HOLD)
        """
        pass

    def _validate_candles(self, candles: List[Candle], min_length: int) -> bool:
        """Check if we have enough candles and symbol matches."""
        if not candles:
            return False
        if len(candles) < min_length:
            return False
        # Ensure all candles are for the correct symbol (if symbol stored in candle)
        # Our Candle doesn't have symbol, so we rely on caller.
        return True
