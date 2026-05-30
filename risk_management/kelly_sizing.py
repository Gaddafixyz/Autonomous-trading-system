"""
Dynamic position sizing using Kelly Criterion.
Tracks historical win rate and payoff ratio from closed trades.
"""

from typing import List, Optional
from core.types import Trade
from core.utils import calculate_kelly_fraction
from core.config import Config
from core.logger import Logger


class KellySizing:
    """Compute position size based on Kelly Criterion."""

    def __init__(self):
        self.config = Config().trading
        self.logger = Logger.get_logger("KellySizing")
        self.trades: List[Trade] = []

    def update_trades(self, trades: List[Trade]):
        """Update internal trade history (call when trades close)."""
        self.trades.extend(trades)

    def compute_kelly_fraction(self) -> float:
        """
        Calculate current Kelly fraction based on recent trade history.
        Returns fraction of capital to risk (clamped between 0.01 and 0.25).
        """
        if len(self.trades) < 10:
            # Not enough data: use conservative default (2% risk)
            return 0.02

        wins = [t for t in self.trades if t.realized_pnl > 0]
        losses = [t for t in self.trades if t.realized_pnl <= 0]
        win_rate = len(wins) / len(self.trades)
        avg_win = sum(t.realized_pnl for t in wins) / len(wins) if wins else 0
        avg_loss = abs(sum(t.realized_pnl for t in losses) / len(losses)) if losses else 1

        if avg_loss == 0:
            return 0.02

        f = calculate_kelly_fraction(win_rate, avg_win, avg_loss, self.config.kelly_fraction)
        self.logger.debug(f"Kelly fraction: {f:.4f} (win_rate={win_rate:.2f})")
        return f

    def calculate_position_size(self, equity: float, entry_price: float,
                                stop_loss_price: float) -> float:
        """
        Calculate position size in base asset (SOL) using Kelly.
        """
        risk_fraction = self.compute_kelly_fraction()
        # Use utility function from Phase 1
        from core.utils import calculate_position_size
        size = calculate_position_size(
            equity=equity,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            risk_fraction=risk_fraction,
            leverage=self.config.leverage,
            min_quantity=1.0,
            max_quantity=1000.0
        )
        self.logger.info(f"Position size: {size:.2f} SOL (risk {risk_fraction:.2%} of equity)")
        return size
