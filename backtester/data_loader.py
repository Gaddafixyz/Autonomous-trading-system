"""
Load and cache historical kline data from Binance.
"""

import os
import json
import asyncio
from typing import List
from datetime import datetime

from core.types import Candle, TimeFrame
from api.binance_client import BinanceClient
from core.logger import Logger


class DataLoader:
    """Fetch historical klines and cache locally."""

    def __init__(self, client: BinanceClient, cache_dir: str = "data/historical"):
        self.client = client
        self.cache_dir = cache_dir
        self.logger = Logger.get_logger("DataLoader")
        os.makedirs(cache_dir, exist_ok=True)

    async def load_candles(
        self,
        symbol: str,
        interval: TimeFrame,
        start_date: str,
        end_date: str,
        use_cache: bool = True,
    ) -> List[Candle]:
        cache_file = os.path.join(
            self.cache_dir,
            f"{symbol}_{interval.value}_{start_date}_{end_date}.json"
        )
        if use_cache and os.path.exists(cache_file):
            self.logger.info(f"Loading cached data from {cache_file}")
            with open(cache_file, "r") as f:
                data = json.load(f)
            return [Candle(**c) for c in data]

        start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
        end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)

        all_klines = []
        limit = 1000
        current_end = end_ts

        while current_end > start_ts:
            klines = await self.client.get_klines(
                symbol,
                interval.value,
                limit=limit,
                end_time=current_end,
            )
            if not klines:
                break
            for k in klines:
                if k['timestamp'] >= start_ts and k['timestamp'] < end_ts:
                    all_klines.insert(0, k)  # keep chronological order
            # Move current_end to the earliest timestamp we just fetched
            current_end = klines[0]['timestamp']
            if len(klines) < limit:
                break
            await asyncio.sleep(0.1)

        candles = [
            Candle(
                timestamp=k['timestamp'],
                open=k['open'],
                high=k['high'],
                low=k['low'],
                close=k['close'],
                volume=k['volume'],
                quote_asset_volume=k['quote_asset_volume'],
                interval=interval,
            )
            for k in all_klines
        ]

        with open(cache_file, "w") as f:
            json.dump([c.__dict__ for c in candles], f, default=str)
        self.logger.info(f"Cached {len(candles)} candles to {cache_file}")
        return candles
