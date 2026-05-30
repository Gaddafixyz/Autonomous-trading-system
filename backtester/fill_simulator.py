"""
Simulate order fills with slippage and commission during backtest.
"""

from core.types import OrderSide, Candle
from core.config import Config


class FillSimulator:
    """Apply slippage and commission to simulated trades."""

    def __init__(self):
        cfg = Config().backtest
        self.slippage_entry_pct = cfg.slippage_entry_pct
        self.slippage_exit_pct = cfg.slippage_exit_pct
        self.commission_pct = cfg.commission_pct

    def simulate_entry(self, candle: Candle, side: OrderSide, requested_price: float) -> float:
        """
        Calculate actual fill price for entry.
        For long: fill price = ask + slippage
        For short: fill price = bid - slippage
        Uses candle high/low as proxy for bid/ask.
        """
        if side == OrderSide.LONG:
            fill_price = candle.high * (1 + self.slippage_entry_pct)
        else:
            fill_price = candle.low * (1 - self.slippage_entry_pct)
        return fill_price

    def simulate_exit(self, candle: Candle, side: OrderSide, requested_price: float) -> float:
        """
        Calculate actual fill price for exit.
        For long exit (sell): fill price = bid - slippage
        For short exit (buy to cover): fill price = ask + slippage
        """
        if side == OrderSide.LONG:
            fill_price = candle.low * (1 - self.slippage_exit_pct)
        else:
            fill_price = candle.high * (1 + self.slippage_exit_pct)
        return fill_price

    def apply_commission(self, amount: float) -> float:
        """Calculate commission on a trade (notional value)."""
        return amount * self.commission_pct
