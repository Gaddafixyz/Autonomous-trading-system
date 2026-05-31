#!/usr/bin/env python3
"""Test script for the Backtesting Engine."""

import asyncio
import sys
import os
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, '.')

from core import Config, TimeFrame
from api import BinanceClient
from backtester import DataLoader, BacktestEngine, Reporter


async def main():
    print("=== Backtest Test ===\n")
    cfg = Config()
    client = BinanceClient(cfg.binance)
    loader = DataLoader(client)

    start = "2026-05-23"
    end = "2026-05-30"
    print(f"Loading data from {start} to {end}…")
    candles = await loader.load_candles("SOLUSDT", TimeFrame.FIVE_MINUTE, start, end)
    if not candles:
        print("No candles loaded (check API keys and date range).")
        return
    print(f"Loaded {len(candles)} candles\n")

    engine = BacktestEngine(initial_equity=10000.0)
    metrics = await engine.run(candles, "SOLUSDT", TimeFrame.FIVE_MINUTE)

    Reporter.print_summary(metrics)
    # FIX: get trades directly from engine instead of reaching into internals
    Reporter.save_json(metrics, engine.get_trades(), "data/backtest_results.json")

    print("✅ Backtest completed successfully")


if __name__ == "__main__":
    asyncio.run(main())
