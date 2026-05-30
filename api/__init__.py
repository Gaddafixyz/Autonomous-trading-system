"""
API Layer for Binance Futures.

Provides REST client, WebSocket manager, rate limiter, and market data feed.
All modules are fully async.
"""

from api.binance_client import BinanceClient
from api.websocket_manager import WebSocketManager, StreamType
from api.rate_limiter import RateLimiter
from api.market_data_feed import MarketDataFeed

__all__ = [
    "BinanceClient",
    "WebSocketManager",
    "StreamType",
    "RateLimiter",
    "MarketDataFeed",
]
