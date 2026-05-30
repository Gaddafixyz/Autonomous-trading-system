#!/usr/bin/env python3
"""
Test script for Phase 7 Live Trading (paper mode).
Run with: python test_live.py
"""

import asyncio
import sys
import os
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, '.')

from core import Config
from live import PaperTrader


async def test_paper_trading():
    print("=== Phase 7 Paper Trading Test ===\n")
    cfg = Config()
    if not cfg.binance.api_key or len(cfg.binance.api_key) < 30:
        print("ERROR: Please set BINANCE_API_KEY and BINANCE_API_SECRET in .env")
        return

    trader = PaperTrader(simulate_fills=True)  # use simulated fills to avoid real orders
    print("Starting paper trader (will run for 30 seconds then stop)...")
    # Run for 30 seconds then cancel
    task = asyncio.create_task(trader.start())
    await asyncio.sleep(30)
    await trader.stop()
    task.cancel()
    print("\n✅ Paper trading test completed")


if __name__ == "__main__":
    asyncio.run(test_paper_trading())
