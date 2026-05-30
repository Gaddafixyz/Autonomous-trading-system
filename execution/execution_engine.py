"""
Main execution engine: places orders, monitors fills, handles timeouts and fallbacks.
"""

import asyncio
from typing import Optional, Callable, Awaitable

from core.types import OrderSide, Order, OrderStatus
from core.config import Config
from core.logger import Logger, trade_logger
from api.binance_client import BinanceClient
from execution.order_manager import OrderManager
from execution.fill_monitor import FillMonitor
from execution.trade_persistence import TradePersistence
from risk_management.position_manager import PositionManager


class ExecutionEngine:
    """
    High-level execution: place limit order, monitor fill, fallback to market.
    """

    def __init__(self, client: BinanceClient, position_mgr: PositionManager):
        self.client = client
        self.position_mgr = position_mgr
        self.order_mgr = OrderManager()
        self.fill_monitor = FillMonitor(self.client, self.order_mgr)
        self.persistence = TradePersistence()
        self.config = Config().trading
        self.logger = Logger.get_logger("ExecutionEngine")

    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        price: float,
        order_type: str = "LIMIT",
        timeout_seconds: int = 30,
        on_filled: Optional[Callable[[Order], Awaitable[None]]] = None,
    ) -> Optional[Order]:
        """
        Place a limit order, wait for fill (or timeout), optionally fallback to market.
        Returns filled order or None if failed.
        """
        # Create local order
        order = self.order_mgr.create_order(symbol, side, quantity, price)

        # Submit to exchange
        try:
            exchange_order = await self.client.place_order(
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price,
                order_type=order_type,
            )
            # Update local order with exchange order ID and status
            order.order_id = exchange_order.order_id
            self.order_mgr.update_order(order.order_id, exchange_order.status,
                                        exchange_order.filled_quantity,
                                        exchange_order.average_fill_price)
        except Exception as e:
            self.logger.error(f"Failed to place order: {e}")
            self.order_mgr.update_order(order.order_id, OrderStatus.REJECTED)
            return None

        # Monitor fill
        filled_order = await self.fill_monitor.monitor_order(
            order.order_id, timeout_seconds=timeout_seconds
        )

        if filled_order and filled_order.status == OrderStatus.FILLED:
            self.logger.info(f"Order {filled_order.order_id} filled at avg {filled_order.average_fill_price}")
            if on_filled:
                await on_filled(filled_order)
            trade_logger.log_entry(
                symbol=symbol,
                side=side.value,
                entry_price=filled_order.average_fill_price or price,
                quantity=filled_order.filled_quantity,
                stop_loss=0.0,
                take_profit=0.0,
                strategy="ExecutionEngine",
                reason="Order filled"
            )
            return filled_order
        else:
            # Timeout or partial: cancel and fallback to market order
            self.logger.warning(f"Order {order.order_id} not filled within {timeout_seconds}s, cancelling...")
            cancelled = await self.client.cancel_order(symbol, order.order_id)
            if cancelled:
                self.order_mgr.update_order(order.order_id, OrderStatus.CANCELLED)
                remaining = quantity - (filled_order.filled_quantity if filled_order else 0)
                if remaining > 0:
                    self.logger.info(f"Placing market order for remaining {remaining}")
                    # Use corrected async method
                    market_price = await self.client.get_ticker(symbol)
                    market_order = await self.client.place_order(
                        symbol=symbol,
                        side=side,
                        quantity=remaining,
                        price=market_price['price'],
                        order_type="MARKET"
                    )
                    if market_order and market_order.status == OrderStatus.FILLED:
                        return market_order
            return None

    async def close_position(self, symbol: str, exit_price: float) -> bool:
        """Close an existing position by placing opposite order."""
        pos = self.position_mgr.positions.get(symbol)
        if not pos:
            self.logger.warning(f"No open position for {symbol}")
            return False

        side = OrderSide.SHORT if pos.side == OrderSide.LONG else OrderSide.LONG
        # If exit_price is 0, use market order via current price
        if exit_price == 0:
            ticker = await self.client.get_ticker(symbol)
            exit_price = ticker['price']

        order = await self.place_order(
            symbol=symbol,
            side=side,
            quantity=pos.quantity,
            price=exit_price,
            timeout_seconds=30,
        )
        if order and order.status == OrderStatus.FILLED:
            trade = self.position_mgr.close_position(symbol, order.average_fill_price or exit_price)
            if trade:
                self.persistence.save_trade(trade)
            return True
        return False
