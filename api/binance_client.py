"""
Binance REST API client for USDS-M Futures.
Uses the official binance-sdk-derivatives-trading-usds-futures SDK.

Key changes from binance-connector:
1. Different initialization and configuration structure
2. Different exception types (uses binance-common exceptions)
3. Response objects are wrapped in response envelopes with .data() method
4. SDK-agnostic adapter: keeps the same BinanceClient interface for rest of system
"""

import asyncio
from typing import List, Dict, Any, Optional
from binance_common.configuration import ConfigurationRestAPI
from binance_common.constants import DERIVATIVES_TRADING_USDS_FUTURES_REST_API_PROD_URL, DERIVATIVES_TRADING_USDS_FUTURES_REST_API_TESTNET_URL
from binance_common.exceptions import (
    ClientError,
    UnauthorizedError,
    ForbiddenError,
    TooManyRequestsError,
    BadRequestError,
    ServerError,
    NetworkError,
)
from binance_sdk_derivatives_trading_usds_futures.derivatives_trading_usds_futures import DerivativesTradingUsdsFutures

from core.config import BinanceConfig
from core.exceptions import (
    ConnectionError as TradingConnectionError,
    RateLimitError,
    AuthenticationError,
)
from core.logger import Logger
from core.types import OrderSide, OrderStatus, Order, Position, Account, TimeFrame
import time


class BinanceClient:
    """
    Binance REST API client for USDS-M Futures.
    Wraps the official binance-sdk-derivatives-trading-usds-futures SDK with async support.
    """

    def __init__(self, config: BinanceConfig, public: bool = False):
        self.config = config
        self.logger = Logger.get_logger("BinanceClient")
        self.public = public
        self._last_request_time = 0

        # Configure SDK
        base_url = (
            DERIVATIVES_TRADING_USDS_FUTURES_REST_API_TESTNET_URL
            if config.testnet
            else DERIVATIVES_TRADING_USDS_FUTURES_REST_API_PROD_URL
        )

        if public:
            # Public client (no authentication)
            self.sdk_config = ConfigurationRestAPI(base_path=base_url)
        else:
            # Authenticated client
            self.sdk_config = ConfigurationRestAPI(
                api_key=config.api_key,
                api_secret=config.api_secret,
                base_path=base_url,
            )

        # Initialize SDK client
        self.client = DerivativesTradingUsdsFutures(config_rest_api=self.sdk_config)
        self.logger.info(f"BinanceClient initialized ({'testnet' if config.testnet else 'mainnet'})")

    async def _request(self, func, *args, **kwargs) -> Any:
        """Execute a request with rate limit awareness (10 requests per second)."""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < 0.1:
            await asyncio.sleep(0.1 - elapsed)
        self._last_request_time = time.time()

        try:
            result = await asyncio.to_thread(func, *args, **kwargs)
            return result
        except TooManyRequestsError as e:
            self.logger.error(f"Rate limit exceeded: {e}")
            raise RateLimitError(f"Rate limit exceeded: {e}")
        except UnauthorizedError as e:
            self.logger.error(f"Authentication error: {e}")
            raise AuthenticationError(f"Authentication error: {e}")
        except (BadRequestError, ServerError, NetworkError) as e:
            self.logger.error(f"API error: {e}")
            raise TradingConnectionError(f"API error: {e}")
        except ClientError as e:
            self.logger.error(f"Client error: {e}")
            raise TradingConnectionError(f"Client error: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")
            raise TradingConnectionError(f"Request failed: {e}")

    async def get_account_balance(self) -> Account:
        """Get account balance (USDT only for futures)."""
        try:
            response = await self._request(self.client.rest_api.account)
            account_data = response.data()

            # Extract USDT balance from assets
            total_equity = float(account_data.total_wallet_balance)
            available = float(account_data.available_balance)
            used_margin = float(account_data.total_margin_level) if account_data.total_margin_level else 0.0

            return Account(
                total_equity=total_equity,
                available_balance=available,
                used_margin=used_margin,
                unrealized_pnl=0.0,  # Can be calculated from positions if needed
                daily_pnl=0.0,
                peak_equity=total_equity,
            )
        except Exception as e:
            self.logger.error(f"Failed to get account balance: {e}")
            raise TradingConnectionError(f"Failed to get account balance: {e}")

    async def get_position(self, symbol: str) -> Optional[Position]:
        """Get current position for a symbol."""
        try:
            response = await self._request(self.client.rest_api.account)
            account_data = response.data()

            # Find position for this symbol
            if hasattr(account_data, 'positions') and account_data.positions:
                for pos in account_data.positions:
                    if pos.symbol == symbol and float(pos.position_amt) != 0:
                        side = OrderSide.LONG if float(pos.position_amt) > 0 else OrderSide.SHORT
                        return Position(
                            symbol=symbol,
                            side=side,
                            entry_price=float(pos.entry_price),
                            quantity=abs(float(pos.position_amt)),
                            leverage=float(pos.leverage),
                            entry_time=int(pos.update_time) if pos.update_time else 0,
                        )
            return None
        except Exception as e:
            self.logger.warning(f"Failed to get position for {symbol}: {e}")
            return None

    async def get_ticker(self, symbol: str) -> Dict:
        """Get current ticker price."""
        try:
            response = await self._request(
                self.client.rest_api.mark_price,
                symbol=symbol,
            )
            ticker_data = response.data()
            return {"price": float(ticker_data.mark_price)}
        except Exception as e:
            self.logger.error(f"Failed to get ticker for {symbol}: {e}")
            raise TradingConnectionError(f"Failed to get ticker: {e}")

    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        price: float,
        order_type: str = "LIMIT",
        time_in_force: str = "GTC"
    ) -> Order:
        """Place an order."""
        try:
            binance_side = "BUY" if side == OrderSide.LONG else "SELL"
            params = {
                "symbol": symbol,
                "side": binance_side,
                "order_type": order_type,
                "quantity": quantity,
            }
            if order_type == "LIMIT":
                params["price"] = price
                params["time_in_force"] = time_in_force

            response = await self._request(self.client.rest_api.new_order, **params)
            order_data = response.data()

            return Order(
                order_id=str(order_data.order_id),
                symbol=symbol,
                side=side,
                quantity=float(order_data.orig_qty),
                price=float(order_data.price) if order_data.price else price,
                status=self._map_order_status(order_data.status),
                filled_quantity=float(order_data.executed_qty),
                average_fill_price=float(order_data.avg_price) if order_data.avg_price and float(order_data.avg_price) > 0 else None,
                created_time=int(order_data.time) if order_data.time else 0,
            )
        except Exception as e:
            self.logger.error(f"Failed to place order: {e}")
            raise TradingConnectionError(f"Failed to place order: {e}")

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """Cancel an order."""
        try:
            await self._request(
                self.client.rest_api.cancel_order,
                symbol=symbol,
                order_id=int(order_id),
            )
            return True
        except Exception as e:
            self.logger.warning(f"Failed to cancel order {order_id}: {e}")
            return False

    async def get_order_status(self, symbol: str, order_id: str) -> Optional[Order]:
        """Query the exchange for the latest status of a specific order."""
        try:
            response = await self._request(
                self.client.rest_api.query_order,
                symbol=symbol,
                order_id=int(order_id),
            )
            order_data = response.data()
            avg_price = float(order_data.avg_price) if order_data.avg_price else 0
            return Order(
                order_id=str(order_data.order_id),
                symbol=symbol,
                side=OrderSide.LONG if order_data.side == 'BUY' else OrderSide.SHORT,
                quantity=float(order_data.orig_qty),
                price=float(order_data.price) if order_data.price else 0,
                status=self._map_order_status(order_data.status),
                filled_quantity=float(order_data.executed_qty),
                average_fill_price=avg_price if avg_price > 0 else None,
                created_time=int(order_data.time) if order_data.time else 0,
                updated_time=int(order_data.update_time) if order_data.update_time else None,
            )
        except Exception as e:
            self.logger.warning(f"Could not fetch order status for {order_id}: {e}")
            return None

    async def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 500,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> List[Dict]:
        """Get kline/candlestick data with optional time range."""
        try:
            params = {
                "symbol": symbol,
                "interval": interval,
                "limit": limit,
            }
            if start_time:
                params["start_time"] = start_time
            if end_time:
                params["end_time"] = end_time

            response = await self._request(self.client.rest_api.klines, **params)
            klines_data = response.data()

            klines = []
            for k in klines_data:
                # klines are returned as lists: [time, open, high, low, close, volume, ...]
                klines.append({
                    "timestamp": int(k[0]),
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                    "quote_asset_volume": float(k[7]) if len(k) > 7 else 0.0,
                })
            return klines
        except Exception as e:
            self.logger.error(f"Failed to get klines for {symbol}: {e}")
            raise TradingConnectionError(f"Failed to get klines: {e}")

    async def set_leverage(self, symbol: str, leverage: int) -> None:
        """Set leverage for a symbol."""
        try:
            await self._request(
                self.client.rest_api.change_leverage,
                symbol=symbol,
                leverage=leverage,
            )
            self.logger.info(f"Set leverage for {symbol} to {leverage}x")
        except Exception as e:
            self.logger.error(f"Failed to set leverage for {symbol}: {e}")
            raise TradingConnectionError(f"Failed to set leverage: {e}")

    @staticmethod
    def _map_order_status(status: str) -> OrderStatus:
        """Map SDK order status to OrderStatus enum."""
        mapping = {
            "NEW": OrderStatus.SUBMITTED,
            "PARTIALLY_FILLED": OrderStatus.PARTIALLY_FILLED,
            "FILLED": OrderStatus.FILLED,
            "CANCELED": OrderStatus.CANCELLED,
            "REJECTED": OrderStatus.REJECTED,
            "EXPIRED": OrderStatus.EXPIRED,
        }
        return mapping.get(status, OrderStatus.PENDING)