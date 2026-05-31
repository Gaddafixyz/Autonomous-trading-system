"""
WebSocket manager for real-time Binance streams.
Handles connection, reconnection, and message routing.

Fixes applied:
- Corrected testnet vs mainnet WS URLs
- Multiple callbacks per stream (so feed._handle_kline and PaperTrader._on_kline
  both receive the same kline stream without overwriting each other)
- Only one WS connection per stream name (no duplicate connects)
- Listen key keepalive: pings every 30 min to prevent user-data stream expiry
"""

import asyncio
import json
from collections import defaultdict
from enum import Enum
from typing import Callable, Dict, List, Optional, Any
import websockets
from websockets.exceptions import ConnectionClosed

from core.logger import Logger


class StreamType(Enum):
    KLINE = "kline"
    TRADE = "trade"
    BOOK_TICKER = "bookTicker"
    ORDER_UPDATE = "orderUpdate"  # user data stream (requires listenKey)


class WebSocketManager:
    """Manages multiple WebSocket streams with automatic reconnection."""

    # Testnet:  wss://stream.binancefuture.com
    # Mainnet:  wss://fstream.binance.com
    TESTNET_WS_URL = "wss://stream.binancefuture.com"
    MAINNET_WS_URL = "wss://fstream.binance.com"

    def __init__(self, testnet: bool = True):
        self.testnet = testnet
        self.base_url = self.TESTNET_WS_URL if testnet else self.MAINNET_WS_URL
        self.logger = Logger.get_logger("WebSocketManager")

        # FIX: list of callbacks per stream so multiple subscribers don't overwrite each other
        self.handlers: Dict[str, List[Callable]] = defaultdict(list)
        self.connections: Dict[str, websockets.WebSocketClientProtocol] = {}
        self._stop_event = asyncio.Event()
        self.listen_key: Optional[str] = None
        self._keepalive_task: Optional[asyncio.Task] = None

    async def subscribe_kline(self, symbol: str, interval: str, callback: Callable):
        """Subscribe to kline stream."""
        stream_name = f"{symbol.lower()}@kline_{interval}"
        await self._subscribe(stream_name, callback)

    async def subscribe_trade(self, symbol: str, callback: Callable):
        """Subscribe to trade stream."""
        stream_name = f"{symbol.lower()}@trade"
        await self._subscribe(stream_name, callback)

    async def subscribe_book_ticker(self, symbol: str, callback: Callable):
        """Subscribe to book ticker (best bid/ask)."""
        stream_name = f"{symbol.lower()}@bookTicker"
        await self._subscribe(stream_name, callback)

    async def start_user_data_stream(self, listen_key: str, callback: Callable,
                                     keepalive_fn: Optional[Callable] = None):
        """
        User data stream (order updates, account balance).
        keepalive_fn: async callable that pings the listen key every 30 min.
        """
        self.listen_key = listen_key
        stream_name = listen_key
        user_url = f"{self.base_url}/ws/{listen_key}"
        await self._subscribe(stream_name, callback, custom_url=user_url)

        # Start keepalive to prevent listen key expiry (expires after 60 min without ping)
        if keepalive_fn:
            self._keepalive_task = asyncio.create_task(
                self._listen_key_keepalive(keepalive_fn)
            )

    async def _listen_key_keepalive(self, keepalive_fn: Callable, interval: int = 1800):
        """Ping the listen key every `interval` seconds (default 30 min)."""
        while not self._stop_event.is_set():
            await asyncio.sleep(interval)
            try:
                await keepalive_fn()
                self.logger.debug("Listen key keepalive sent")
            except Exception as e:
                self.logger.warning(f"Listen key keepalive failed: {e}")

    async def _subscribe(self, stream_name: str, callback: Callable,
                         custom_url: Optional[str] = None):
        """
        Register callback for a stream. Only creates one WS connection per
        stream_name regardless of how many callbacks are registered.
        """
        self.handlers[stream_name].append(callback)

        # Only open one connection per stream
        if stream_name not in self.connections:
            url = custom_url or f"{self.base_url}/ws/{stream_name}"
            asyncio.create_task(self._run_websocket(stream_name, url))

    async def _run_websocket(self, stream_name: str, url: str):
        """Maintain WebSocket connection with auto-reconnect."""
        while not self._stop_event.is_set():
            try:
                async with websockets.connect(url) as ws:
                    self.connections[stream_name] = ws
                    self.logger.info(f"WebSocket connected: {stream_name}")
                    async for message in ws:
                        if self._stop_event.is_set():
                            break
                        data = json.loads(message)
                        await self._handle_message(stream_name, data)
            except ConnectionClosed:
                self.logger.warning(f"WebSocket disconnected: {stream_name}, reconnecting...")
                self.connections.pop(stream_name, None)
                await asyncio.sleep(5)
            except Exception as e:
                self.logger.error(f"WebSocket error for {stream_name}: {e}")
                self.connections.pop(stream_name, None)
                await asyncio.sleep(10)

    async def _handle_message(self, stream_name: str, data: dict):
        """Route message to ALL registered callbacks for this stream."""
        for callback in self.handlers.get(stream_name, []):
            try:
                await callback(data)
            except Exception as e:
                self.logger.error(f"Callback error for {stream_name}: {e}")

    async def stop(self):
        """Gracefully stop all WebSocket connections."""
        self._stop_event.set()
        if self._keepalive_task:
            self._keepalive_task.cancel()
        for ws in list(self.connections.values()):
            try:
                await ws.close()
            except Exception:
                pass
        self.connections.clear()
        self.logger.info("All WebSocket connections closed")