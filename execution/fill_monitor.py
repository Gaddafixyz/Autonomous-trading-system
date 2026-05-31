"""
Monitors order fill status with timeout and exchange polling.

Fix applied: The previous implementation only checked the *local* OrderManager
state, which was never updated after submission (it stayed SUBMITTED forever).
Now monitor_order polls the exchange via client.get_order_status() every
check_interval seconds so real fill/cancel/reject events are detected.
"""

import asyncio
from typing import Optional

from api.binance_client import BinanceClient
from execution.order_manager import OrderManager
from core.types import Order, OrderStatus
from core.logger import Logger

# Terminal states — stop polling once reached
_TERMINAL = {OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED, OrderStatus.EXPIRED}


class FillMonitor:
    """Periodically query the exchange until order reaches a terminal state or times out."""

    def __init__(self, client: BinanceClient, order_mgr: OrderManager):
        self.client = client
        self.order_mgr = order_mgr
        self.logger = Logger.get_logger("FillMonitor")
        self.check_interval = 2  # seconds between exchange polls

    async def monitor_order(self, order_id: str, timeout_seconds: int = 30) -> Optional[Order]:
        """
        Poll exchange until the order is filled, cancelled, rejected, or timeout.

        Returns the updated Order if filled, None otherwise.
        """
        local_order = self.order_mgr.get_order(order_id)
        if not local_order:
            self.logger.warning(f"Order {order_id} not found in local manager")
            return None

        symbol = local_order.symbol
        start = asyncio.get_event_loop().time()

        while True:
            elapsed = asyncio.get_event_loop().time() - start
            if elapsed > timeout_seconds:
                self.logger.warning(f"Order {order_id} timed out after {timeout_seconds}s")
                return self.order_mgr.get_order(order_id)

            # FIX: query the exchange for real status
            exchange_order = await self.client.get_order_status(symbol, order_id)
            if exchange_order:
                updated = self.order_mgr.update_order(
                    order_id,
                    exchange_order.status,
                    filled_qty=exchange_order.filled_quantity,
                    avg_price=exchange_order.average_fill_price,
                )
                if updated and updated.status in _TERMINAL:
                    if updated.status == OrderStatus.FILLED:
                        self.logger.info(f"Order {order_id} filled @ {updated.average_fill_price}")
                        return updated
                    else:
                        self.logger.warning(f"Order {order_id} terminal state: {updated.status}")
                        return None

            await asyncio.sleep(self.check_interval)

    async def simulate_fill(self, order_id: str, delay_seconds: float = 1.0) -> Optional[Order]:
        """For paper trading: simulate an immediate fill after `delay_seconds`."""
        await asyncio.sleep(delay_seconds)
        order = self.order_mgr.get_order(order_id)
        if order and order.status == OrderStatus.SUBMITTED:
            self.order_mgr.update_order(
                order_id,
                OrderStatus.FILLED,
                filled_qty=order.quantity,
                avg_price=order.price,
            )
            return self.order_mgr.get_order(order_id)
        return None
