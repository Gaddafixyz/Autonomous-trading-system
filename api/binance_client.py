"""
Binance REST API client for USD-M Futures.
Wraps the official binance-connector with async support.
"""

import asyncio
from typing import List, Dict, Any, Optional
from binance.um_futures import UMFutures
from binance.error import ClientError

from core.config import BinanceConfig
from core.exceptions import (
    ConnectionError,
    RateLimitError,
    AuthenticationError,
)
from core.logger import Logger
from core.types import OrderSide, OrderStatus, Order, Position, Account
import time


class BinanceClient:
    """Async wrapper for Binance USD-M Futures REST API."""

    def __init__(self, config: BinanceConfig, public: bool = False):
        self.config = config
        self.logger = Logger.get_logger("BinanceClient")
        self.public = public
        if public:
            # Public client (no API keys needed) for historical data
            self.client = UMFutures(base_url="https://fapi.binance.com")
        else:
            self.client = UMFutures(
                key=config.api_key,
                secret=config.api_secret,
                base_url=config.base_url,
            )
        self._last_request_time = 0

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
        except ClientError as e:
            self.logger.error(f"Binance API error: {e}")
            if e.status_code == 429:
                raise RateLimitError(f"Rate limit exceeded: {e}")
            elif e.status_code in (400, 401):
                raise AuthenticationError(f"Authentication error: {e}")
            elif e.status_code >= 500:
                raise ConnectionError(f"Server error: {e}")
            raise ConnectionError(f"API error: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")
            raise ConnectionError(f"Request failed: {e}")

    async def get_account_balance(self) -> Account:
        """Get account balance (USDT only)."""
        resp = await self._request(self.client.account)
        assets = {item['asset']: float(item['walletBalance']) for item in resp['assets']}
        total_equity = assets.get('USDT', 0.0)
        return Account(
            total_equity=total_equity,
            available_balance=total_equity,
            used_margin=0.0,
            unrealized_pnl=0.0,
            daily_pnl=0.0,
            peak_equity=total_equity,
        )

    async def get_position(self, symbol: str) -> Optional[Position]:
        """Get current position for a symbol."""
        resp = await self._request(self.client.get_position_risk, symbol=symbol)
        for pos in resp:
            if pos['symbol'] == symbol and float(pos['positionAmt']) != 0:
                side = OrderSide.LONG if float(pos['positionAmt']) > 0 else OrderSide.SHORT
                return Position(
                    symbol=symbol,
                    side=side,
                    entry_price=float(pos['entryPrice']),
                    quantity=abs(float(pos['positionAmt'])),
                    leverage=float(pos['leverage']),
                    entry_time=int(pos['updateTime']),
                )
        return None

    async def get_ticker(self, symbol: str) -> Dict:
        """Get current ticker price (async)."""
        resp = await self._request(self.client.ticker_price, symbol=symbol)
        return {"price": float(resp['price'])}

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
        binance_side = "BUY" if side == OrderSide.LONG else "SELL"
        resp = await self._request(
            self.client.new_order,
            symbol=symbol,
            side=binance_side,
            type=order_type,
            quantity=quantity,
            price=price,
            timeInForce=time_in_force,
        )
        return Order(
            order_id=str(resp['orderId']),
            symbol=symbol,
            side=side,
            quantity=float(resp['origQty']),
            price=float(resp['price']),
            status=self._map_order_status(resp['status']),
            filled_quantity=float(resp['executedQty']),
            average_fill_price=float(resp.get('avgPrice', 0)),
            created_time=resp['updateTime'],
        )

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """Cancel an order."""
        try:
            await self._request(self.client.cancel_order, symbol=symbol, orderId=int(order_id))
            return True
        except ClientError:
            return False

    async def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 500,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> List[Dict]:
        """Get kline/candlestick data with optional time range."""
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time

        resp = await self._request(self.client.klines, **params)
        klines = []
        for k in resp:
            klines.append({
                "timestamp": k[0],
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
                "quote_asset_volume": float(k[6]),
            })
        return klines

    async def set_leverage(self, symbol: str, leverage: int) -> None:
        """Set leverage for a symbol."""
        await self._request(self.client.change_leverage, symbol=symbol, leverage=leverage)

    @staticmethod
    def _map_order_status(status: str) -> OrderStatus:
        mapping = {
            "NEW": OrderStatus.SUBMITTED,
            "PARTIALLY_FILLED": OrderStatus.PARTIALLY_FILLED,
            "FILLED": OrderStatus.FILLED,
            "CANCELED": OrderStatus.CANCELLED,
            "REJECTED": OrderStatus.REJECTED,
            "EXPIRED": OrderStatus.EXPIRED,
        }
        return mapping.get(status, OrderStatus.PENDING)
