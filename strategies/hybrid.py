"""
Hybrid strategy combining Mean Reversion and Momentum signals.
Uses weighted voting: 60% MR, 40% Momentum.
Only generates signal if combined confidence >= min_confidence (0.3).
"""

from typing import List, Optional

from core.types import Candle, Signal, SignalType, StrategyType
from core.config import Config
from strategies.base import BaseStrategy
from strategies.mean_reversion import MeanReversionStrategy
from strategies.momentum import MomentumStrategy


class HybridStrategy(BaseStrategy):
    """Combines mean reversion and momentum signals."""

    def __init__(self, symbol: str, timeframe):
        super().__init__(symbol, timeframe)
        self.strategy_type = StrategyType.HYBRID
        cfg = Config()
        self.mr_weight = cfg.strategy.mr_weight
        self.momentum_weight = cfg.strategy.momentum_weight
        self.min_confidence = cfg.strategy.min_signal_confidence

        # Instantiate child strategies
        self.mr_strategy = MeanReversionStrategy(symbol, timeframe)
        self.momentum_strategy = MomentumStrategy(symbol, timeframe)

    async def calculate_signal(self, candles: List[Candle]) -> Optional[Signal]:
        """
        Get signals from both strategies, combine using weighted voting.
        Returns BUY if net confidence >= threshold, SELL if net negative, else HOLD.
        """
        # Get individual signals (may be None if no signal)
        mr_signal = await self.mr_strategy.calculate_signal(candles)
        mom_signal = await self.momentum_strategy.calculate_signal(candles)

        # Convert to numeric scores: +1 for BUY, -1 for SELL, 0 for HOLD/None
        mr_score = 0
        mr_conf = 0
        mom_score = 0
        mom_conf = 0

        if mr_signal:
            mr_score = 1 if mr_signal.signal_type == SignalType.BUY else -1
            mr_conf = mr_signal.confidence
        if mom_signal:
            mom_score = 1 if mom_signal.signal_type == SignalType.BUY else -1
            mom_conf = mom_signal.confidence

        # Weighted combined score
        total_score = (mr_score * mr_conf * self.mr_weight +
                       mom_score * mom_conf * self.momentum_weight)
        total_confidence = (mr_conf * self.mr_weight + mom_conf * self.momentum_weight)

        # Determine signal direction
        if total_score > 0 and total_confidence >= self.min_confidence:
            signal_type = SignalType.BUY
            reason = f"Hybrid: MR({mr_score},{mr_conf:.2f}) + Mom({mom_score},{mom_conf:.2f}) => BUY"
        elif total_score < 0 and total_confidence >= self.min_confidence:
            signal_type = SignalType.SELL
            reason = f"Hybrid: MR({mr_score},{mr_conf:.2f}) + Mom({mom_score},{mom_conf:.2f}) => SELL"
        else:
            return None  # HOLD

        # Use the better entry price from whichever signal is present
        entry_price = candles[-1].close
        # For SL/TP, we'll let risk management decide later
        return Signal(
            timestamp=candles[-1].timestamp,
            strategy=self.strategy_type,
            symbol=self.symbol,
            signal_type=signal_type,
            confidence=total_confidence,
            entry_price=entry_price,
            reason=reason
        )
