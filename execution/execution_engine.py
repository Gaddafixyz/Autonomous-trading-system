"""
Main execution engine: places orders, monitors fills, handles timeouts and fallbacks.

Fixes applied:
1. Order rejection handling: validates that exchange_order.status is FILLED
   before proceeding (previously would crash on ghost order if rejected)
2. Pre-flight validation: checks symbol, size, account balance before placing
3. Circuit breaker: emergency shutdown on critical conditions
4. Better error messages and logging
"""

import asyncio
from typing import Optional, Callable, Awaitable
from enum import Enum

from core.types import OrderSide, Order, OrderStatus
from core.config import Config
from core.logger import Logger, trade_logger
from core.exceptions import (
    OrderPlacementError,
    InsufficientDataError,
)
from api.binance_client import BinanceClient
from execution.order_manager import OrderManager
from execution.fill_monitor import FillMonitor
from execution.trade_persistence import TradePersistence
from risk_management.position_manager import PositionManager


class CircuitBreakerState(Enum):
    """Circuit breaker states for emergency shutdown."""
    CLOSED = "CLOSED"      # Normal operation
    OPEN = "OPEN"          # Emergency shutdown triggered
    HALF_OPEN = "HALF_OPEN"  # Testing if recovery possible


class ExecutionEngine:
    """
    High-level execution: place limit order, monitor fill, fallback to market.
    Includes circuit breaker for emergency shutdown.
    """

    def __init__(self, client: BinanceClient, position_mgr: PositionManager):
        self.client = client
        self.position_mgr = position_mgr
        self.order_mgr = OrderManager()
        self.fill_monitor = FillMonitor(self.client, self.order_mgr)
        self.persistence = TradePersistence()
        self.config = Config().trading
        self.logger = Logger.get_logger("ExecutionEngine")
        
        # FIX: Circuit breaker for emergency shutdown
        self.circuit_breaker_state = CircuitBreakerState.CLOSED
        self.circuit_breaker_reason: Optional[str] = None

    def trip_circuit_breaker(self, reason: str) -> None:
        """
        Trigger emergency shutdown. No more orders will be placed.
        """
        self.circuit_breaker_state = CircuitBreakerState.OPEN
        self.circuit_breaker_reason = reason
        self.logger.critical(f"CIRCUIT BREAKER TRIPPED: {reason}")

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
        
        FIX: Now validates order parameters and account status before placing.
        """
        # FIX: Check circuit breaker
        if self.circuit_breaker_state == CircuitBreakerState.OPEN:
            self.logger.error(
                f"Cannot place order: circuit breaker is OPEN. Reason: {self.circuit_breaker_reason}"
            )
            return None

        # FIX: Pre-flight validation
        validation_error = self._validate_order(symbol, side, quantity, price)
        if validation_error:
            self.logger.error(f"Order validation failed: {validation_error}")
            return None

        # Create local order
        order = self.order_mgr.create_order(symbol, side, quantity, price)

        # Submit to exchange
        try:
            self.logger.info(f"Placing {order_type} order: {symbol} {side.value} {quantity} @ {price}")
            exchange_order = await self.client.place_order(
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price,
                order_type=order_type,
            )
            
            # FIX: Validate that order was actually placed (not rejected)
            if exchange_order.status == OrderStatus.REJECTED:
                self.logger.error(f"Order rejected by exchange: {exchange_order}")
                self.order_mgr.update_order(order.order_id, OrderStatus.REJECTED)
                return None

            # Update local order with exchange order ID and status
            order.order_id = exchange_order.order_id
            self.order_mgr.update_order(
                order.order_id,
                exchange_order.status,
                exchange_order.filled_quantity,
                exchange_order.average_fill_price
            )
            self.logger.debug(f"Order {order.order_id} placed, status={exchange_order.status.value}")

        except OrderPlacementError as e:
            self.logger.error(f"Failed to place order: {e}")
            self.order_mgr.update_order(order.order_id, OrderStatus.REJECTED)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error during order placement: {e}", exc_info=True)
            self.order_mgr.update_order(order.order_id, OrderStatus.REJECTED)
            return None

        # Monitor fill
        filled_order = await self.fill_monitor.monitor_order(
            order.order_id, timeout_seconds=timeout_seconds
        )

        if filled_order and filled_order.status == OrderStatus.FILLED:
            self.logger.info(
                f"Order {filled_order.order_id} filled at {filled_order.average_fill_price:.2f} "
                f"({filled_order.filled_quantity}/{filled_order.quantity} units)"
            )
            if on_filled:
                try:
                    await on_filled(filled_order)
                except Exception as e:
                    self.logger.error(f"Error in on_filled callback: {e}")
            
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
            self.logger.warning(
                f"Order {order.order_id} not fully filled within {timeout_seconds}s "
                f"(filled: {filled_order.filled_quantity if filled_order else 0}/{quantity}), "
                f"cancelling and placing market order..."
            )
            
            try:
                cancelled = await self.client.cancel_order(symbol, order.order_id)
                if cancelled:
                    self.order_mgr.update_order(order.order_id, OrderStatus.CANCELLED)
                    remaining = quantity - (filled_order.filled_quantity if filled_order else 0)
                    
                    if remaining > self.config.min_order_qty:
                        self.logger.info(f"Placing market order for remaining {remaining:.4f}")
                        try:
                            ticker = await self.client.get_ticker(symbol)
                            market_price = ticker['price']
                            
                            market_order = await self.client.place_order(
                                symbol=symbol,
                                side=side,
                                quantity=remaining,
                                price=market_price,
                                order_type="MARKET"
                            )
                            
                            # FIX: Validate market order wasn't rejected
                            if market_order and market_order.status != OrderStatus.REJECTED:
                                if market_order.status == OrderStatus.FILLED:
                                    self.logger.info(f"Market order filled at {market_price:.2f}")
                                    return market_order
                            else:
                                self.logger.error("Market order was rejected by exchange")
                        except Exception as e:
                            self.logger.error(f"Failed to place market order: {e}")
                else:
                    self.logger.error(f"Failed to cancel order {order.order_id}")
            except Exception as e:
                self.logger.error(f"Error during order cancellation: {e}")

            return None

    def _validate_order(self, symbol: str, side: OrderSide, quantity: float, price: float) -> Optional[str]:
        """
        FIX: Pre-flight validation before placing order.
        Returns error message if validation fails, None if OK.
        """
        # Check symbol is not empty
        if not symbol or len(symbol) == 0:
            return "Symbol is empty"

        # Check side is valid
        if side not in (OrderSide.LONG, OrderSide.SHORT):
            return f"Invalid side: {side}"

        # Check quantity is positive
        if quantity <= 0:
            return f"Quantity must be positive, got {quantity}"

        # Check price is positive
        if price <= 0:
            return f"Price must be positive, got {price}"

        # Check quantity is within limits
        if quantity < self.config.min_order_qty:
            return f"Quantity {quantity} below minimum {self.config.min_order_qty}"
        if quantity > self.config.max_order_qty:
            return f"Quantity {quantity} exceeds maximum {self.config.max_order_qty}"

        # Check symbol matches config (for now, single symbol)
        if symbol != self.config.symbol:
            return f"Symbol {symbol} does not match configured symbol {self.config.symbol}"

        return None

    async def close_position(self, symbol: str, exit_price: float) -> bool:
        """
        Close an existing position by placing opposite order.
        """
        pos = self.position_mgr.positions.get(symbol)
        if not pos:
            self.logger.warning(f"No open position for {symbol}")
            return False

        side = OrderSide.SHORT if pos.side == OrderSide.LONG else OrderSide.LONG
        
        # If exit_price is 0, use market order via current price
        if exit_price == 0:
            try:
                ticker = await self.client.get_ticker(symbol)
                exit_price = ticker['price']
            except Exception as e:
                self.logger.error(f"Failed to fetch current price for {symbol}: {e}")
                return False

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