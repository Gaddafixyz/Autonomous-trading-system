"""
Mean Reversion Strategy using Bollinger Bands (20, 2σ).

Fix applied: The entry condition was:
    current_price < current_lower * (1 - self.entry_threshold)
With bb_entry_threshold = 0.5 this required price to be 50% BELOW the lower
band — an event that essentially never occurs on liquid markets.

The config comment says "Entry when price within 0.5σ of lower band", meaning
we enter when price is approaching the lower band (within half a standard
deviation above it, or anywhere below it).  The corrected condition is:

    current_price <= current_lower + entry_threshold * band_std

where band_std = (upper - lower) / (2 * bb_std_dev) recovers the per-period
standard deviation from the band width.
"""

import math
from typing import List, Optional

from core.types import Candle, Signal, SignalType, StrategyType
from core.utils import calculate_bollinger_bands
from core.config import Config
from strategies.base import BaseStrategy


class MeanReversionStrategy(BaseStrategy):
    """Bollinger Bands mean reversion."""

    def __init__(self, symbol: str, timeframe):
        super().__init__(symbol, timeframe)
        self.strategy_type = StrategyType.MEAN_REVERSION
        cfg = Config()
        self.bb_period = cfg.strategy.bb_period
        self.bb_std_dev = cfg.strategy.bb_std_dev
        # Fraction of one std-dev: enter when price is within this distance
        # of (or below) the lower band.  0.5 means half a standard deviation.
        self.entry_threshold = cfg.strategy.bb_entry_threshold

    async def calculate_signal(self, candles: List[Candle]) -> Optional[Signal]:
        """
        BUY  when price is within entry_threshold * σ of the lower Bollinger Band.
        SELL when price rises back above the middle band (SMA).
        HOLD otherwise.
        """
        if not self._validate_candles(candles, self.bb_period):
            return None

        closes = [c.close for c in candles]
        current_price = closes[-1]

        middle, upper, lower = calculate_bollinger_bands(
            closes, period=self.bb_period, num_std=self.bb_std_dev
        )
        current_middle = middle[-1]
        current_lower = lower[-1]
        current_upper = upper[-1]

        # Guard against NaN (not enough data for the rolling window)
        if any(math.isnan(v) for v in (current_middle, current_lower, current_upper)):
            return None

        # Recover the per-period standard deviation from the band width:
        #   upper = middle + num_std * std  →  std = (upper - lower) / (2 * num_std)
        band_std = (current_upper - current_lower) / (2 * self.bb_std_dev)
        if band_std <= 0:
            return None

        # FIX: entry trigger = lower band + entry_threshold * std
        # (price must be at or approaching the lower band, not 50% below it)
        entry_level = current_lower + self.entry_threshold * band_std

        if current_price <= entry_level:
            # Confidence scales with how far into (or past) the trigger price is
            distance = entry_level - current_price  # positive = price below trigger
            confidence = min(1.0, 0.4 + distance / band_std)
            return Signal(
                timestamp=candles[-1].timestamp,
                strategy=self.strategy_type,
                symbol=self.symbol,
                signal_type=SignalType.BUY,
                confidence=confidence,
                entry_price=current_price,
                stop_loss_price=current_lower * 0.98,
                take_profit_price=current_middle,
                reason=(
                    f"Price {current_price:.4f} within {self.entry_threshold}σ "
                    f"of lower band {current_lower:.4f}"
                ),
            )

        # Exit / short signal: price has reverted back above the middle band
        if current_price > current_middle:
            return Signal(
                timestamp=candles[-1].timestamp,
                strategy=self.strategy_type,
                symbol=self.symbol,
                signal_type=SignalType.SELL,
                confidence=0.8,
                reason=f"Price {current_price:.4f} above SMA {current_middle:.4f}",
            )

        return None
