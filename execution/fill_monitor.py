"""
Monitors order fill status with timeout and retry logic.
"""

import asyncio
from typing import Optional

from api.binance_client import BinanceClient
from execution.order_manager import OrderManager
from core.types import Order, OrderStatus
from core.logger import Logger


class FillMonitor:
    """Periodically check order status until filled or timeout."""

    def __init__(self, client: BinanceClient, order_mgr: OrderManager):
        self.client = client
        self.order_mgr = order_mgr
        self.logger = Logger.get_logger("FillMonitor")
        self.check_interval = 2  # seconds

    async def monitor_order(self, order_id: str, timeout_seconds: int = 30) -> Optional[Order]:
        """
        Monitor order until filled, cancelled, or timeout.
        Returns updated order if filled, else None.
        """
        start_time = asyncio.get_event_loop().time()
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout_seconds:
                self.logger.warning(f"Order {order_id} timed out after {timeout_seconds}s")
                return None

            # Fetch latest order status from exchange
            order = self.order_mgr.get_order(order_id)
            if not order:
                return None

            try:
                # In a real implementation, you'd call client.get_order_status(order_id)
                # For paper trading simulation, we assume fill happens after a short delay.
                # Here we simulate by checking local order status if it came from exchange.
                if order.status == OrderStatus.FILLED:
                    self.logger.info(f"Order {order_id} filled")
                    return order
                elif order.status in (OrderStatus.CANCELLED, OrderStatus.REJECTED, OrderStatus.EXPIRED):
                    self.logger.warning(f"Order {order_id} terminal state: {order.status}")
                    return None
            except Exception as e:
                self.logger.error(f"Error checking order {order_id}: {e}")

            await asyncio.sleep(self.check_interval)

    async def simulate_fill(self, order_id: str, delay_seconds: float = 1.0) -> Optional[Order]:
        """For paper trading: simulate fill after delay."""
        await asyncio.sleep(delay_seconds)
        order = self.order_mgr.get_order(order_id)
        if order and order.status == OrderStatus.SUBMITTED:
            self.order_mgr.update_order(order_id, OrderStatus.FILLED,
                                        filled_qty=order.quantity,
                                        avg_price=order.price)
            return self.order_mgr.get_order(order_id)
        return None
