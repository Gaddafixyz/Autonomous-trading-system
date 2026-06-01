"""
WebSocket Manager for USDS-M Futures.

NOTE: The WebSocket functionality uses the same endpoints as before:
- Testnet: wss://stream.binancefuture.com
- Mainnet: wss://fstream.binance.com

The REST API client uses the new SDK, but WebSocket streams are handled
separately and don't require changes to the SDK.

This file is provided for reference and future enhancements.
Most functionality remains the same as the original websocket_manager.py
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
    """
    Manages multiple WebSocket streams with automatic reconnection.
    
    NOTE: This class is compatible with both USDT-M and USDS-M Futures.
    The streaming endpoints are the same for both.
    """

    # Testnet: same URL for both USDT-M and USDS-M
    TESTNET_WS_URL = "wss://stream.binancefuture.com"
    # Mainnet: same URL for both USDT-M and USDS-M
    MAINNET_WS_URL = "wss://fstream.binance.com"

    def __init__(self, testnet: bool = True):
        self.testnet = testnet
        self.base_url = self.TESTNET_WS_URL if testnet else self.MAINNET_WS_URL
        self.logger = Logger.get_logger("WebSocketManager")

        # Multiple callbacks per stream so they don't overwrite each other
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
        
        NOTE: For user data streams with the new SDK, you may need to:
        1. Get listenKey from REST API
        2. Periodically refresh it (every 30 minutes)
        
        The keepalive_fn should call the REST API to refresh the listen key.
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
        Register callback for a stream. Multiple callbacks can subscribe
        to the same stream without overwriting each other.
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


# ============================================================================
# HELPER FUNCTIONS FOR REST API LISTEN KEY MANAGEMENT
# ============================================================================

async def get_listen_key(client) -> str:
    """
    Get a fresh listen key from the REST API.
    
    Usage with new SDK:
        from binance_sdk_derivatives_trading_usds_futures.derivatives_trading_usds_futures import DerivativesTradingUsdsFutures
        config = ConfigurationRestAPI(api_key="...", api_secret="...")
        client = DerivativesTradingUsdsFutures(config_rest_api=config)
        listen_key = await get_listen_key(client)
    """
    try:
        response = await asyncio.to_thread(client.rest_api.listen_key)
        data = response.data()
        return data.listen_key
    except Exception as e:
        Logger.get_logger("WebSocketManager").error(f"Failed to get listen key: {e}")
        raise


async def refresh_listen_key(client, listen_key: str) -> str:
    """
    Refresh an existing listen key (extends validity to another 60 minutes).
    
    Usage:
        await refresh_listen_key(client, listen_key)
    """
    try:
        response = await asyncio.to_thread(
            client.rest_api.renew_listen_key,
            listen_key=listen_key
        )
        data = response.data()
        return data.listen_key
    except Exception as e:
        Logger.get_logger("WebSocketManager").error(f"Failed to refresh listen key: {e}")
        raise


async def close_listen_key(client, listen_key: str) -> bool:
    """
    Close a listen key (stop receiving user data stream updates).
    
    Usage:
        await close_listen_key(client, listen_key)
    """
    try:
        await asyncio.to_thread(
            client.rest_api.close_listen_key,
            listen_key=listen_key
        )
        return True
    except Exception as e:
        Logger.get_logger("WebSocketManager").warning(f"Failed to close listen key: {e}")
        return False


# ============================================================================
# COMPATIBILITY NOTE
# ============================================================================
"""
COMPATIBILITY WITH NEW SDK:

The WebSocket Manager doesn't directly interact with the REST SDK. It uses
raw WebSocket connections which are the same for both USDT-M and USDS-M.

However, if you use user data streams, you need to:

1. Get a listen key from the REST API:
   response = client.rest_api.listen_key()
   listen_key = response.data().listen_key

2. Pass it to WebSocket Manager:
   ws.start_user_data_stream(listen_key, on_user_data)

3. Refresh it every 30 minutes:
   client.rest_api.renew_listen_key(listen_key=listen_key)

The helper functions above make this easier.

Example integration:
    
    # Get listen key
    listen_key = await get_listen_key(client)
    
    # Start WebSocket with keepalive
    async def keepalive():
        await refresh_listen_key(client, listen_key)
    
    await ws.start_user_data_stream(listen_key, on_user_data, keepalive)
    
    # Later: cleanup
    await close_listen_key(client, listen_key)
    await ws.stop()
"""