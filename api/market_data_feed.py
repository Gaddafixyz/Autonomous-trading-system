"""
Market data feed: aggregates real-time klines and provides rolling windows.
"""

import asyncio
from collections import deque
from typing import List, Dict, Optional, Callable

from core.types import Candle, TimeFrame
from core.logger import Logger
from api.binance_client import BinanceClient
from api.websocket_manager import WebSocketManager


class MarketDataFeed:
    """
    Maintains real-time candlestick data for multiple symbols and timeframes.
    Uses WebSocket for live updates and falls back to REST for historical.
    """

    def __init__(self, client: BinanceClient, ws_manager: WebSocketManager):
        self.client = client
        self.ws = ws_manager
        self.logger = Logger.get_logger("MarketDataFeed")
        # Store candles in memory: symbol -> timeframe -> deque of Candle
        self.candles: Dict[str, Dict[str, deque]] = {}
        self.max_candles = 1000  # Keep last 1000 candles per timeframe

    async def initialize(
        self,
        symbol: str,
        timeframes: List[TimeFrame],
        historical_limit: int = 500
    ):
        """
        Load historical candles via REST, then subscribe to live kline streams.
        """
        self.symbol = symbol
        self.timeframes = timeframes
        # Initialize storage
        if symbol not in self.candles:
            self.candles[symbol] = {}
        for tf in timeframes:
            self.candles[symbol][tf.value] = deque(maxlen=self.max_candles)
            # Load historical data
            klines = await self.client.get_klines(symbol, tf.value, historical_limit)
            for k in klines:
                candle = Candle(
                    timestamp=k['timestamp'],
                    open=k['open'],
                    high=k['high'],
                    low=k['low'],
                    close=k['close'],
                    volume=k['volume'],
                    quote_asset_volume=k['quote_asset_volume'],
                    interval=tf,
                )
                self.candles[symbol][tf.value].append(candle)
            self.logger.info(f"Loaded {len(klines)} historical {tf.value} candles for {symbol}")

        # Subscribe to live kline updates
        for tf in timeframes:
            await self.ws.subscribe_kline(symbol, tf.value, self._handle_kline)

    async def _handle_kline(self, data: dict):
        """Callback for live kline updates."""
        k = data['k']
        symbol = data['s']
        interval = k['i']
        candle = Candle(
            timestamp=k['t'],
            open=float(k['o']),
            high=float(k['h']),
            low=float(k['l']),
            close=float(k['c']),
            volume=float(k['v']),
            quote_asset_volume=float(k['q']),
            interval=TimeFrame(interval),
        )
        # Replace or append
        tf_key = interval
        if symbol in self.candles and tf_key in self.candles[symbol]:
            # Check if last candle has same timestamp (update)
            deq = self.candles[symbol][tf_key]
            if deq and deq[-1].timestamp == candle.timestamp:
                deq.pop()  # remove last, then append updated
            deq.append(candle)
            self.logger.debug(f"Updated {symbol} {interval} candle at {candle.timestamp}")

    def get_candles(self, symbol: str, timeframe: TimeFrame, count: int = 100) -> List[Candle]:
        """Get last N candles for a symbol and timeframe."""
        if symbol not in self.candles:
            return []
        deq = self.candles[symbol].get(timeframe.value)
        if not deq:
            return []
        return list(deq)[-count:]

    def get_latest_candle(self, symbol: str, timeframe: TimeFrame) -> Optional[Candle]:
        """Get the most recent candle."""
        candles = self.get_candles(symbol, timeframe, 1)
        return candles[0] if candles else None
