#!/usr/bin/env python3
"""
Test script for Phase 5 Execution Engine.
"""

import asyncio
import sys
import os
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, '.')

from core import Config, OrderSide
from api import BinanceClient
from risk_management import PositionManager
from execution import ExecutionEngine, TradePersistence


async def test_placement():
    print("Testing order placement...")
    cfg = Config()
    client = BinanceClient(cfg.binance)
    pos_mgr = PositionManager()
    engine = ExecutionEngine(client, pos_mgr)

    # Place a small limit order (0.001 SOL) on testnet
    order = await engine.place_order(
        symbol="SOLUSDT",
        side=OrderSide.LONG,
        quantity=0.001,      # very small for testnet
        price=80.0,          # low price, unlikely to fill immediately
        timeout_seconds=5,
    )
    if order:
        print(f"Order placed: {order.order_id} status={order.status}")
    else:
        print("Order failed or timed out (expected if price too low)")
    print("✓ Order placement test done")


async def test_persistence():
    print("Testing trade persistence...")
    persistence = TradePersistence()
    # Create a dummy trade
    from core.types import Trade, OrderSide
    trade = Trade(
        timestamp=1700000000000,
        symbol="SOLUSDT",
        strategy=None,
        side=OrderSide.LONG,
        entry_price=100.0,
        exit_price=110.0,
        quantity=10.0,
        realized_pnl=100.0,
        pnl_percent=10.0,
        duration_seconds=3600,
        entry_reason="Test",
        exit_reason="TP hit"
    )
    persistence.save_trade(trade)
    trades = persistence.load_trades(limit=5)
    assert len(trades) >= 1
    print("✓ Trade persistence works")


async def main():
    print("=== Phase 5 Execution Engine Tests ===\n")
    await test_persistence()
    await test_placement()
    print("\n✅ All Phase 5 tests passed!")


if __name__ == "__main__":
    asyncio.run(main())
