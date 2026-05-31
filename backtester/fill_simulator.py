"""
Simulate order fills with slippage and commission during backtest.

Fix applied: The previous version always filled at candle.high (long entry) or
candle.low (short entry) regardless of the requested limit price, making every
entry maximally pessimistic.  The fix behaves like a real limit order:

  - Long entry:  fill at requested_price + slippage IF candle.low <= requested_price
                 (the candle traded at or below our limit); otherwise fill at
                 candle.open + slippage (simulates a market/aggressive order).
  - Short entry: fill at requested_price - slippage IF candle.high >= requested_price;
                 otherwise at candle.open - slippage.

Exit fill logic is unchanged (uses candle.low / candle.high with slippage because
exits trigger at SL/TP which the candle must have touched).
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
        Calculate actual fill price for entry respecting limit-order semantics.

        For LONG:
          - If candle.low <= requested_price: limit order would fill → fill at
            requested_price * (1 + slippage).
          - Otherwise treat as market order → fill at candle.open * (1 + slippage).

        For SHORT:
          - If candle.high >= requested_price: limit sell would fill → fill at
            requested_price * (1 - slippage).
          - Otherwise market order → fill at candle.open * (1 - slippage).
        """
        if side == OrderSide.LONG:
            # Three cases for a buy-limit order at requested_price:
            #   1. requested_price >= candle.open  → opened at/below limit, fill at open
            #   2. candle.low <= requested_price   → limit was touched during the candle
            #   3. candle.low > requested_price    → never touched, treat as market (open)
            if requested_price >= candle.open:
                fill_price = candle.open * (1 + self.slippage_entry_pct)
            elif candle.low <= requested_price:
                fill_price = requested_price * (1 + self.slippage_entry_pct)
            else:
                fill_price = candle.open * (1 + self.slippage_entry_pct)
        else:  # SHORT sell-limit order
            # 1. requested_price <= candle.open → opened at/above limit, fill at open
            # 2. candle.high >= requested_price → limit touched during candle
            # 3. candle.high < requested_price  → never touched, market fill at open
            if requested_price <= candle.open:
                fill_price = candle.open * (1 - self.slippage_entry_pct)
            elif candle.high >= requested_price:
                fill_price = requested_price * (1 - self.slippage_entry_pct)
            else:
                fill_price = candle.open * (1 - self.slippage_entry_pct)
        return fill_price

    def simulate_exit(self, candle: Candle, side: OrderSide, requested_price: float) -> float:
        """
        Calculate actual fill price for exit.
        SL/TP exits are triggered because the candle touched requested_price,
        so we use the requested price ± slippage (not the candle extreme).

        For long exit (sell):  fill at requested_price * (1 - slippage).
        For short exit (cover): fill at requested_price * (1 + slippage).
        """
        if side == OrderSide.LONG:
            fill_price = requested_price * (1 - self.slippage_exit_pct)
        else:
            fill_price = requested_price * (1 + self.slippage_exit_pct)
        return fill_price

    def apply_commission(self, notional: float) -> float:
        """Calculate commission on a trade (notional value = price * quantity)."""
        return notional * self.commission_pct
