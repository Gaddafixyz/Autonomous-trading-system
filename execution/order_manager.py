"""
Order state machine: tracks orders from creation to final state.
"""

from typing import Optional
from enum import Enum
from typing import Dict, Optional
from datetime import datetime

from core.types import Order, OrderStatus, OrderSide
from core.logger import Logger


class OrderState(Enum):
    """Internal order state (more granular than OrderStatus)."""
    PENDING = "PENDING"           # Created locally, not yet sent
    SUBMITTED = "SUBMITTED"       # Sent to exchange
    PARTIAL = "PARTIAL"           # Partially filled
    FILLED = "FILLED"             # Fully filled
    CANCELLING = "CANCELLING"     # Cancel requested
    CANCELLED = "CANCELLED"       # Cancel confirmed
    REJECTED = "REJECTED"         # Rejected by exchange
    EXPIRED = "EXPIRED"           # Timeout


class OrderManager:
    """Manage order lifecycle and state transitions."""

    def __init__(self):
        self.orders: Dict[str, Order] = {}  # order_id -> Order
        self.logger = Logger.get_logger("OrderManager")

    def create_order(self, symbol: str, side: OrderSide, quantity: float,
                     price: float, order_id: Optional[str] = None) -> Order:
        """Create a new order in PENDING state."""
        order = Order(
            order_id=order_id or f"local_{int(datetime.now().timestamp()*1000)}",
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            status=OrderStatus.PENDING,
        )
        self.orders[order.order_id] = order
        self.logger.info(f"Created order {order.order_id}: {side.value} {quantity} {symbol} @ {price}")
        return order

    def update_order(self, order_id: str, new_status: OrderStatus,
                     filled_qty: float = None, avg_price: float = None) -> Optional[Order]:
        """Update order status and fill information."""
        order = self.orders.get(order_id)
        if not order:
            self.logger.warning(f"Order {order_id} not found")
            return None

        order.status = new_status
        if filled_qty is not None:
            order.filled_quantity = filled_qty
        if avg_price is not None:
            order.average_fill_price = avg_price
        order.updated_time = int(datetime.now().timestamp() * 1000)

        self.logger.debug(f"Order {order_id} status -> {new_status.value}, filled {order.filled_quantity}/{order.quantity}")
        return order

    def get_order(self, order_id: str) -> Optional[Order]:
        return self.orders.get(order_id)

    def get_open_orders(self) -> list:
        """Return orders that are not yet filled, cancelled, or rejected."""
        open_statuses = {OrderStatus.PENDING, OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED}
        return [o for o in self.orders.values() if o.status in open_statuses]
