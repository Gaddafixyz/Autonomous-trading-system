"""
Stop-loss and take-profit calculations based on ATR or Bollinger Bands.
"""

from typing import Tuple
import math
from core.types import Candle, OrderSide
from core.utils import calculate_atr, calculate_bollinger_bands
from core.config import Config


class StopLossCalculator:
    """Compute SL/TP levels for different strategy types."""

    def __init__(self):
        self.config = Config().strategy

    def compute_mr_levels(self, candles: list, side: OrderSide,
                          entry_price: float) -> Tuple[float, float]:
        """
        Mean reversion SL/TP.
        - LONG:  SL below lower band (or 2% below entry), TP at middle band.
        - SHORT: SL above upper band (or 2% above entry), TP at middle band.
        """
        closes = [c.close for c in candles]
        _, upper, lower = calculate_bollinger_bands(
            closes, period=self.config.bb_period, num_std=self.config.bb_std_dev
        )
        current_lower = lower[-1] if lower and not math.isnan(lower[-1]) else None
        current_upper = upper[-1] if upper and not math.isnan(upper[-1]) else None
        current_mid = sum(closes[-self.config.bb_period:]) / self.config.bb_period

        if side == OrderSide.LONG:
            # SL: must be below entry. Use lower band if it's below entry, else fixed 2%
            if current_lower and current_lower < entry_price:
                sl = current_lower * 0.99
            else:
                sl = entry_price * 0.98
            # TP: middle band if it's above entry, else 5% profit
            tp = current_mid if current_mid > entry_price else entry_price * 1.05
        else:  # SHORT
            if current_upper and current_upper > entry_price:
                sl = current_upper * 1.01
            else:
                sl = entry_price * 1.02
            tp = current_mid if current_mid < entry_price else entry_price * 0.95

        return max(sl, 0.01), max(tp, 0.01)

    def compute_momentum_levels(self, candles: list, side: OrderSide,
                                entry_price: float) -> Tuple[float, float]:
        """Momentum SL/TP based on ATR (2x ATR for SL, 3x ATR for TP)."""
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        closes = [c.close for c in candles]
        atr_values = calculate_atr(highs, lows, closes, period=14)
        current_atr = atr_values[-1] if atr_values and not math.isnan(atr_values[-1]) else entry_price * 0.02

        if side == OrderSide.LONG:
            sl = entry_price - (current_atr * 2)
            tp = entry_price + (current_atr * 3)
        else:
            sl = entry_price + (current_atr * 2)
            tp = entry_price - (current_atr * 3)

        return max(sl, 0.01), max(tp, 0.01)

    def compute_hybrid_levels(self, candles: list, side: OrderSide,
                              entry_price: float, mr_confidence: float) -> Tuple[float, float]:
        """Use MR levels if MR confidence > 0.6, else momentum levels."""
        if mr_confidence > 0.6:
            return self.compute_mr_levels(candles, side, entry_price)
        else:
            return self.compute_momentum_levels(candles, side, entry_price)
