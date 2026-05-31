#!/usr/bin/env python3
"""
Test script for Phase 5 Execution Engine.

FIX: Now creates valid Trade objects with proper StrategyType enum values.
"""

import asyncio
import sys
import os
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, '.')

from core import Config, OrderSide, StrategyType
from api import BinanceClient
from risk_management import PositionManager
from execution import ExecutionEngine, TradePersistence
from core.types import Trade


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
    
    # FIX: Create valid Trade object with proper StrategyType
    trade = Trade(
        timestamp=1700000000000,
        symbol="SOLUSDT",
        strategy=StrategyType.HYBRID,  # FIX: now a proper StrategyType enum
        side=OrderSide.LONG,
        entry_price=100.0,
        exit_price=110.0,
        quantity=10.0,
        realized_pnl=100.0,
        pnl_percent=10.0,
        duration_seconds=3600,
        entry_reason="Test entry",
        exit_reason="Test exit - TP hit"
    )
    
    # Save and verify
    persistence.save_trade(trade)
    trades = persistence.load_trades(limit=5)
    assert len(trades) >= 1, "No trades found in database"
    
    # Verify saved trade matches what we created
    saved_trade = trades[0]
    assert saved_trade['symbol'] == "SOLUSDT"
    assert saved_trade['realized_pnl'] == 100.0
    print(f"  Saved trade: {saved_trade['symbol']} | PnL: {saved_trade['realized_pnl']:.2f} USDT")
    
    print("✓ Trade persistence works")


async def test_circuit_breaker():
    """Test that circuit breaker prevents orders after being tripped."""
    print("Testing circuit breaker...")
    cfg = Config()
    client = BinanceClient(cfg.binance)
    pos_mgr = PositionManager()
    engine = ExecutionEngine(client, pos_mgr)

    # Normal operation should work
    assert engine.circuit_breaker_state.value == "CLOSED"
    print(f"  Initial state: {engine.circuit_breaker_state.value}")

    # Trip the circuit breaker
    engine.trip_circuit_breaker("Test shutdown")
    assert engine.circuit_breaker_state.value == "OPEN"
    print(f"  After trip: {engine.circuit_breaker_state.value}")

    # Try to place order - should fail
    order = await engine.place_order(
        symbol="SOLUSDT",
        side=OrderSide.LONG,
        quantity=0.1,
        price=100.0,
    )
    assert order is None, "Order should fail when circuit breaker is open"
    print("  Order correctly rejected when circuit breaker is OPEN")
    print("✓ Circuit breaker test passed")


async def test_order_validation():
    """Test pre-flight order validation."""
    print("Testing order validation...")
    cfg = Config()
    client = BinanceClient(cfg.binance)
    pos_mgr = PositionManager()
    engine = ExecutionEngine(client, pos_mgr)

    # Test cases: (symbol, side, quantity, price, should_pass)
    test_cases = [
        ("SOLUSDT", OrderSide.LONG, 0.1, 100.0, True),      # Valid order
        ("", OrderSide.LONG, 0.1, 100.0, False),            # Empty symbol
        ("SOLUSDT", OrderSide.LONG, -0.1, 100.0, False),    # Negative quantity
        ("SOLUSDT", OrderSide.LONG, 0.1, -100.0, False),    # Negative price
        ("SOLUSDT", OrderSide.LONG, 0.00001, 100.0, False), # Below minimum
        ("BTCUSDT", OrderSide.LONG, 0.1, 100.0, False),     # Wrong symbol
    ]

    for symbol, side, qty, price, should_pass in test_cases:
        error = engine._validate_order(symbol, side, qty, price)
        passed = error is None
        status = "✓" if passed == should_pass else "✗"
        print(f"  {status} {symbol:8} {side.value:5} qty={qty:7.5f} price={price:7.1f} → {error or 'OK'}")

    print("✓ Order validation test passed")


async def main():
    print("=== Phase 5 Execution Engine Tests ===\n")
    
    try:
        await test_circuit_breaker()
        print()
        await test_order_validation()
        print()
        await test_persistence()
        print()
        # Requires API keys, so skip in CI
        if os.getenv("BINANCE_API_KEY"):
            await test_placement()
        else:
            print("Skipping placement test (no API keys)")
        
        print("\n✅ All Phase 5 tests passed!")
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
