"""
Load and cache historical kline data from Binance.

Fix applied: The previous pagination loop used insert(0, k) inside the inner
for-loop, which individually reversed each batch before inserting, producing
out-of-order candles.  The fix collects all raw dicts in a flat list, then
sorts by timestamp and deduplicates before converting to Candle objects.
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

        # FIX: collect raw klines in a plain list; sort and dedup at the end.
        # Previously, insert(0, k) inside the inner for-loop reversed each
        # batch individually before inserting, producing scrambled ordering.
        all_raw: List[dict] = []
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

            all_raw.extend(klines)
            earliest_ts = klines[0]['timestamp']
            current_end = earliest_ts  # walk backwards

            if len(klines) < limit:
                break  # reached the start of available data
            await asyncio.sleep(0.1)  # stay within rate limits

        # Filter to requested window, sort chronologically, then deduplicate
        all_raw = [k for k in all_raw if start_ts <= k['timestamp'] < end_ts]
        all_raw.sort(key=lambda k: k['timestamp'])
        seen: set = set()
        deduped: List[dict] = []
        for k in all_raw:
            if k['timestamp'] not in seen:
                seen.add(k['timestamp'])
                deduped.append(k)

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
            for k in deduped
        ]

        # Persist cache using dict representation (TimeFrame enum → string via default=str)
        with open(cache_file, "w") as f:
            json.dump(
                [{**c.__dict__, "interval": c.interval.value} for c in candles],
                f,
            )
        self.logger.info(f"Cached {len(candles)} candles to {cache_file}")
        return candles
