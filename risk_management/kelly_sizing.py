"""
Dynamic position sizing using Kelly Criterion.
Tracks historical win rate and payoff ratio from closed trades.

Fix applied: calculate_position_size previously hardcoded min_quantity=1.0 and
max_quantity=1000.0, which is only correct for SOL.  Values are now read from
TradingConfig (min_order_qty / max_order_qty) so they adapt to any symbol.
"""

from typing import List
from core.types import Trade
from core.utils import calculate_kelly_fraction, calculate_position_size
from core.config import Config
from core.logger import Logger


class KellySizing:
    """Compute position size based on Kelly Criterion."""

    def __init__(self):
        self.config = Config().trading
        self.logger = Logger.get_logger("KellySizing")
        self.trades: List[Trade] = []

    def update_trades(self, trades: List[Trade]):
        """Update internal trade history (call whenever trades close)."""
        self.trades.extend(trades)

    def compute_kelly_fraction(self) -> float:
        """
        Calculate current Kelly fraction based on recent trade history.
        Returns fraction of capital to risk (clamped between 0.0001 and 0.25).
        Falls back to a conservative 2% when fewer than 10 trades are available.
        """
        if len(self.trades) < 10:
            return 0.02

        wins = [t for t in self.trades if t.realized_pnl > 0]
        losses = [t for t in self.trades if t.realized_pnl <= 0]

        win_rate = len(wins) / len(self.trades)
        avg_win = sum(t.realized_pnl for t in wins) / len(wins) if wins else 0.0
        avg_loss = abs(sum(t.realized_pnl for t in losses) / len(losses)) if losses else 1.0

        if avg_loss == 0:
            return 0.02

        f = calculate_kelly_fraction(
            win_rate, avg_win, avg_loss, self.config.kelly_fraction
        )
        self.logger.debug(f"Kelly fraction: {f:.4f} (win_rate={win_rate:.2f})")
        return f

    def calculate_position_size(
        self, equity: float, entry_price: float, stop_loss_price: float
    ) -> float:
        """
        Calculate position size in base asset using Kelly.

        FIX: min and max quantities come from config instead of being hardcoded
        to 1.0 / 1000.0 (which was SOL-specific and unsafe for other symbols).
        """
        risk_fraction = self.compute_kelly_fraction()
        size = calculate_position_size(
            equity=equity,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            risk_fraction=risk_fraction,
            leverage=self.config.leverage,
            min_quantity=self.config.min_order_qty,   # FIX
            max_quantity=self.config.max_order_qty,   # FIX
        )
        self.logger.info(
            f"Position size: {size:.4f} units (risk {risk_fraction:.2%} of equity)"
        )
        return size