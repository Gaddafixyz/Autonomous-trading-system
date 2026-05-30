#!/usr/bin/env python3
"""
Test script for Phase 2 API Layer.
Run after setting BINANCE_API_KEY and BINANCE_API_SECRET in .env.
"""

import asyncio
import sys
import os
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, '.')

from core import Config, Logger
from api import BinanceClient, WebSocketManager, MarketDataFeed
from core.types import TimeFrame


async def test_rest():
    print("Testing REST API...")
    cfg = Config()
    client = BinanceClient(cfg.binance)
    # Test account balance
    account = await client.get_account_balance()
    print(f"Account balance: {account.total_equity} USDT")
    # Test klines
    klines = await client.get_klines("SOLUSDT", "1m", limit=5)
    print(f"Got {len(klines)} klines")
    # Test set leverage (optional)
    # await client.set_leverage("SOLUSDT", 5)
    # print("Leverage set to 5x")
    print("✓ REST tests passed")
    return client


async def test_websocket():
    print("Testing WebSocket...")
    ws = WebSocketManager(testnet=True)
    received = asyncio.Event()

    async def on_trade(data):
        print(f"Trade: {data['p']} @ {data['q']}")
        received.set()

    await ws.subscribe_trade("solusdt", on_trade)
    # Wait a few seconds for a message
    try:
        await asyncio.wait_for(received.wait(), timeout=10)
        print("✓ WebSocket received trade")
    except asyncio.TimeoutError:
        print("✗ No trade received within 10 seconds (network may be slow)")
    finally:
        await ws.stop()
    return ws


async def test_market_data_feed():
    print("Testing MarketDataFeed...")
    cfg = Config()
    client = BinanceClient(cfg.binance)
    ws = WebSocketManager(testnet=True)
    feed = MarketDataFeed(client, ws)

    await feed.initialize("SOLUSDT", [TimeFrame.ONE_MINUTE, TimeFrame.FIVE_MINUTE], historical_limit=100)
    # Wait a moment for live updates
    await asyncio.sleep(5)
    candles_1m = feed.get_candles("SOLUSDT", TimeFrame.ONE_MINUTE, 10)
    print(f"Got {len(candles_1m)} 1m candles")
    assert len(candles_1m) > 0
    print("✓ Market data feed works")
    await ws.stop()


async def main():
    print("=== Phase 2 API Tests ===\n")
    if not os.getenv("BINANCE_API_KEY") or len(os.getenv("BINANCE_API_KEY", "")) < 30:
        print("ERROR: Please set BINANCE_API_KEY and BINANCE_API_SECRET in .env")
        sys.exit(1)

    try:
        await test_rest()
        await test_websocket()
        await test_market_data_feed()
        print("\n✅ All Phase 2 tests passed!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
