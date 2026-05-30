"""
Real-time performance metrics.
"""

from typing import List
from core.types import Trade
from core.utils import calculate_sharpe_ratio, calculate_max_drawdown, calculate_win_rate


class RiskMetrics:
    """Compute live performance metrics from trades and equity curve."""

    def __init__(self):
        self.equity_curve: List[float] = []
        self.trades: List[Trade] = []

    def add_equity_point(self, equity: float):
        self.equity_curve.append(equity)

    def add_trade(self, trade: Trade):
        self.trades.append(trade)

    def get_sharpe(self, returns: List[float]) -> float:
        return calculate_sharpe_ratio(returns)

    def get_max_drawdown(self) -> float:
        if not self.equity_curve:
            return 0.0
        dd, _, _ = calculate_max_drawdown(self.equity_curve)
        return dd

    def get_win_rate(self) -> float:
        if not self.trades:
            return 0.0
        wins = sum(1 for t in self.trades if t.realized_pnl > 0)
        return calculate_win_rate(wins, len(self.trades))

    def get_profit_factor(self) -> float:
        total_wins = sum(t.realized_pnl for t in self.trades if t.realized_pnl > 0)
        total_losses = abs(sum(t.realized_pnl for t in self.trades if t.realized_pnl < 0))
        if total_losses == 0:
            return float('inf') if total_wins > 0 else 0.0
        return total_wins / total_losses
