# fetch_test.py
import asyncio
from datetime import datetime, timedelta
from core import Config, TimeFrame
from api import BinanceClient

async def main():
    cfg = Config()
    # Use a public client (no keys needed) or your existing one
    client = BinanceClient(cfg.binance, public=True)  # or public=False if you have keys
    end_ts = int(datetime.now().timestamp() * 1000)
    start_ts = end_ts - 7 * 24 * 3600 * 1000  # 7 days ago
    klines = await client.get_klines("SOLUSDT", "5m", limit=500, start_time=start_ts, end_time=end_ts)
    print(f"Fetched {len(klines)} klines for the last 7 days")
    if klines:
        print("First candle:", klines[0])
        print("Last candle:", klines[-1])

asyncio.run(main())
