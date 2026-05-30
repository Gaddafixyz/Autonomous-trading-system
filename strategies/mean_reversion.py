"""
Mean Reversion Strategy using Bollinger Bands (20, 2σ).
Generates BUY when price crosses below lower band, SELL when price crosses above SMA.
"""

from typing import List, Optional

from core.types import Candle, Signal, SignalType, StrategyType
from core.utils import calculate_bollinger_bands, calculate_sma
from core.config import Config
from strategies.base import BaseStrategy


class MeanReversionStrategy(BaseStrategy):
    """Bollinger Bands mean reversion."""

    def __init__(self, symbol: str, timeframe):
        super().__init__(symbol, timeframe)
        self.strategy_type = StrategyType.MEAN_REVERSION
        # Load parameters from config
        cfg = Config()
        self.bb_period = cfg.strategy.bb_period
        self.bb_std_dev = cfg.strategy.bb_std_dev
        self.entry_threshold = cfg.strategy.bb_entry_threshold

    async def calculate_signal(self, candles: List[Candle]) -> Optional[Signal]:
        """
        Generates signal based on Bollinger Bands.

        Logic:
        - Need at least bb_period candles.
        - Calculate middle (SMA), upper, lower bands.
        - If current close < lower band * (1 - threshold) → BUY (confidence scaled by distance)
        - If current close > middle band → SELL (close position)
        - Otherwise HOLD.
        """
        if not self._validate_candles(candles, self.bb_period):
            return None

        # Extract close prices (oldest to newest)
        closes = [c.close for c in candles]
        current_price = closes[-1]

        # Calculate Bollinger Bands (returns lists aligned with closes)
        middle, upper, lower = calculate_bollinger_bands(
            closes, period=self.bb_period, num_std=self.bb_std_dev
        )
        current_middle = middle[-1]
        current_lower = lower[-1]

        # Check for NaN (insufficient data)
        if any(x is None or (isinstance(x, float) and x != x) for x in [current_middle, current_lower]):
            return None

        # Entry condition: price below lower band (with threshold)
        if current_price < current_lower * (1 - self.entry_threshold):
            # Confidence based on how far below the band (capped at 1.0)
            distance = (current_lower - current_price) / current_lower
            confidence = min(1.0, distance / self.entry_threshold)
            return Signal(
                timestamp=candles[-1].timestamp,
                strategy=self.strategy_type,
                symbol=self.symbol,
                signal_type=SignalType.BUY,
                confidence=confidence,
                entry_price=current_price,
                stop_loss_price=current_lower * 0.98,  # rough SL: 2% below lower band
                take_profit_price=current_middle,      # TP at middle band
                reason=f"Price {current_price} below lower band {current_lower:.4f}"
            )

        # Exit condition: price above middle band (SMA)
        elif current_price > current_middle:
            return Signal(
                timestamp=candles[-1].timestamp,
                strategy=self.strategy_type,
                symbol=self.symbol,
                signal_type=SignalType.SELL,
                confidence=0.8,
                reason=f"Price {current_price} above SMA {current_middle:.4f}"
            )

        return None
