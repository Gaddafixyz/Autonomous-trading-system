"""
Portfolio-level risk monitoring:
- Daily loss limit
- Max drawdown limit
- Emergency shutdown
"""

from core.config import Config
from core.logger import Logger, risk_logger
from core.exceptions import DailyLossExceededError, MaxDrawdownExceededError


class PortfolioRisk:
    """Monitor overall portfolio risk."""

    def __init__(self, initial_equity: float):
        self.config = Config().trading
        self.logger = Logger.get_logger("PortfolioRisk")
        self.initial_equity = initial_equity
        self.peak_equity = initial_equity
        self.daily_start_equity = initial_equity
        self.today_realized_pnl = 0.0

    def update_equity(self, current_equity: float, daily_pnl_change: float):
        """Update equity and track drawdown."""
        self.today_realized_pnl += daily_pnl_change
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity

    def check_daily_loss(self) -> None:
        """Raise exception if daily loss exceeds limit."""
        daily_loss_pct = -self.today_realized_pnl / self.daily_start_equity if self.daily_start_equity > 0 else 0
        if daily_loss_pct > self.config.max_daily_loss_pct:
            risk_logger.log_rejection(
                "Daily loss limit exceeded",
                {"loss_pct": daily_loss_pct, "limit": self.config.max_daily_loss_pct}
            )
            raise DailyLossExceededError(f"Daily loss {daily_loss_pct:.2%} > {self.config.max_daily_loss_pct:.2%}")

    def check_drawdown(self, current_equity: float) -> None:
        """Raise exception if drawdown exceeds limit."""
        if self.peak_equity == 0:
            return
        drawdown = (self.peak_equity - current_equity) / self.peak_equity
        if drawdown > self.config.max_drawdown_pct:
            risk_logger.log_rejection(
                "Max drawdown exceeded",
                {"drawdown": drawdown, "limit": self.config.max_drawdown_pct}
            )
            raise MaxDrawdownExceededError(f"Drawdown {drawdown:.2%} > {self.config.max_drawdown_pct:.2%}")

    def reset_daily(self, new_equity: float):
        """Call at start of new trading day."""
        self.daily_start_equity = new_equity
        self.today_realized_pnl = 0.0
