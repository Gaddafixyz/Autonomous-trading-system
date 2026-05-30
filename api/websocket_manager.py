"""
WebSocket manager for real-time Binance streams.
Handles connection, reconnection, and message routing.
"""

import asyncio
import json
from enum import Enum
from typing import Callable, Dict, Optional, Any
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

    def __init__(self, testnet: bool = True):
        self.testnet = testnet
        self.base_url = "wss://stream.binancefuture.com" if not testnet else "wss://stream.binancefuture.com"  # same for testnet
        self.logger = Logger.get_logger("WebSocketManager")
        self.connections: Dict[str, websockets.WebSocketClientProtocol] = {}
        self.handlers: Dict[str, Callable] = {}
        self.tasks: Dict[str, asyncio.Task] = {}
        self._stop_event = asyncio.Event()
        self.listen_key: Optional[str] = None

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

    async def start_user_data_stream(self, listen_key: str, callback: Callable):
        """User data stream (order updates, account balance)."""
        self.listen_key = listen_key
        stream_name = f"{listen_key}"
        # For user data, the URL is different
        user_url = "wss://fstream.binance.com/ws" if not self.testnet else "wss://stream.binancefuture.com/ws"
        await self._subscribe(stream_name, callback, custom_url=user_url)

    async def _subscribe(self, stream_name: str, callback: Callable, custom_url: Optional[str] = None):
        """Internal: subscribe to a stream."""
        self.handlers[stream_name] = callback
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
                await asyncio.sleep(5)
            except Exception as e:
                self.logger.error(f"WebSocket error for {stream_name}: {e}")
                await asyncio.sleep(10)

    async def _handle_message(self, stream_name: str, data: dict):
        """Route message to the registered callback."""
        callback = self.handlers.get(stream_name)
        if callback:
            try:
                await callback(data)
            except Exception as e:
                self.logger.error(f"Callback error for {stream_name}: {e}")

    async def stop(self):
        """Gracefully stop all WebSocket connections."""
        self._stop_event.set()
        for task in self.tasks.values():
            task.cancel()
        for ws in self.connections.values():
            await ws.close()
        self.logger.info("All WebSocket connections closed")
