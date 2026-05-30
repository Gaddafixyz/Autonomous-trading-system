"""
Momentum Strategy using EMA crossover (50/400) and ADX (>25).
Requires volume confirmation (>1.2x average).
"""

from typing import List, Optional

from core.types import Candle, Signal, SignalType, StrategyType
from core.utils import calculate_ema_full, calculate_adx, calculate_sma
from core.config import Config
from strategies.base import BaseStrategy


class MomentumStrategy(BaseStrategy):
    """EMA crossover + ADX momentum."""

    def __init__(self, symbol: str, timeframe):
        super().__init__(symbol, timeframe)
        self.strategy_type = StrategyType.MOMENTUM
        cfg = Config()
        self.ema_fast = cfg.strategy.ema_fast_period
        self.ema_slow = cfg.strategy.ema_slow_period
        self.adx_period = cfg.strategy.adx_period
        self.adx_threshold = cfg.strategy.adx_threshold
        self.volume_multiplier = cfg.strategy.volume_multiplier

    async def calculate_signal(self, candles: List[Candle]) -> Optional[Signal]:
        """
        Generates BUY when:
          - EMA_fast > EMA_slow
          - ADX > threshold
          - Current volume > volume_multiplier * average volume (last 20)

        Generates SELL when EMA_fast < EMA_slow (trend reversal).
        """
        min_candles = max(self.ema_slow, self.adx_period * 2, 20)
        if not self._validate_candles(candles, min_candles):
            return None

        closes = [c.close for c in candles]
        volumes = [c.volume for c in candles]

        # Calculate EMAs (full length with NaNs)
        ema_fast = calculate_ema_full(closes, self.ema_fast)
        ema_slow = calculate_ema_full(closes, self.ema_slow)
        # Calculate ADX
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        adx = calculate_adx(highs, lows, closes, self.adx_period)
        # Volume average (last 20)
        vol_avg = calculate_sma(volumes, 20) if len(volumes) >= 20 else []

        current_ema_fast = ema_fast[-1]
        current_ema_slow = ema_slow[-1]
        current_adx = adx[-1]
        current_volume = volumes[-1]
        avg_volume = vol_avg[-1] if vol_avg else 0

        # Check for NaN
        if any(x != x for x in [current_ema_fast, current_ema_slow, current_adx]):
            return None

        # BUY condition
        if (current_ema_fast > current_ema_slow and
            current_adx > self.adx_threshold and
            avg_volume > 0 and
            current_volume > avg_volume * self.volume_multiplier):
            # Confidence based on ADX strength (0-1)
            confidence = min(1.0, (current_adx - self.adx_threshold) / 50.0)
            return Signal(
                timestamp=candles[-1].timestamp,
                strategy=self.strategy_type,
                symbol=self.symbol,
                signal_type=SignalType.BUY,
                confidence=confidence,
                entry_price=closes[-1],
                stop_loss_price=closes[-1] * 0.98,  # 2% stop (will be refined in risk mgmt)
                take_profit_price=closes[-1] * 1.03,  # 3% profit target
                reason=f"EMA({self.ema_fast}) > EMA({self.ema_slow}), ADX={current_adx:.1f}, volume surge"
            )

        # SELL condition (trend reversal)
        elif current_ema_fast < current_ema_slow:
            return Signal(
                timestamp=candles[-1].timestamp,
                strategy=self.strategy_type,
                symbol=self.symbol,
                signal_type=SignalType.SELL,
                confidence=0.7,
                reason=f"EMA({self.ema_fast}) crossed below EMA({self.ema_slow})"
            )

        return None
