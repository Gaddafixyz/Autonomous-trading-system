#!/usr/bin/env python3
"""
Verification script for Phase 1.
Tests all core modules and key functionalities.
"""

import sys
sys.path.insert(0, '.')

def test_imports():
    print("Testing imports...")
    from core import Config, Candle, Signal, Position, Order, Account, Trade
    from core import calculate_kelly_fraction, calculate_sharpe_ratio
    from core import Logger, trade_logger, strategy_logger
    from core.exceptions import TradingException, is_critical_error
    print("✓ All imports successful")

def test_candle():
    print("Testing Candle validation...")
    from core import Candle, TimeFrame
    candle = Candle(
        timestamp=1700000000000,
        open=100.0,
        high=105.0,
        low=95.0,
        close=102.0,
        volume=1000.0,
        quote_asset_volume=102000.0,
        interval=TimeFrame.FIVE_MINUTE
    )
    assert candle.typical_price() == (105+95+102)/3
    print("✓ Candle validation passed")

def test_position_pnl():
    print("Testing Position PnL...")
    from core import Position, OrderSide
    pos = Position(
        symbol="SOLUSDT",
        side=OrderSide.LONG,
        entry_price=100.0,
        quantity=10.0,
        leverage=5.0,
        entry_time=1700000000000
    )
    unrealized = pos.unrealized_pnl(110.0)
    assert unrealized == (110-100)*10*5  # 500 USDT
    pos.close(110.0, 1700000000001)
    assert pos.realized_pnl == 500.0
    print("✓ Position PnL passed")

def test_config():
    print("Testing Configuration...")
    from core import Config
    # Use dummy env or rely on defaults
    cfg = Config.load_paper_trading()
    assert cfg.trading.leverage == 5.0
    assert cfg.trading.symbol == "SOLUSDT"
    assert cfg.live.mode == "paper"
    print("✓ Configuration loaded")

def test_logger():
    print("Testing Logger...")
    from core import Logger, trade_logger
    logger = Logger.get_logger("test")
    logger.info("Test log message")
    trade_logger.log_entry("SOLUSDT", "BUY", 100.0, 10.0, 95.0, 110.0, "TEST", "verification")
    print("✓ Logger works (check logs/ directory)")

def test_utils():
    print("Testing Utility functions...")
    from core import (
        calculate_kelly_fraction,
        calculate_sharpe_ratio,
        calculate_sma,
        calculate_ema,
        calculate_bollinger_bands,
        calculate_rsi
    )
    kelly = calculate_kelly_fraction(0.55, 100, 50, 0.25)
    assert 0.0 < kelly < 0.25
    returns = [0.01] * 100
    sharpe = calculate_sharpe_ratio(returns)
    assert sharpe > 0
    prices = [100, 101, 102, 103, 104, 105]
    sma = calculate_sma(prices, 3)
    assert len(sma) == 4
    ema = calculate_ema(prices, 3)
    assert len(ema) == 4
    bb_mid, bb_up, bb_low = calculate_bollinger_bands(prices, 3, 2)
    assert len(bb_mid) == len(prices)
    rsi = calculate_rsi(prices, 14)
    assert len(rsi) == len(prices)
    print("✓ All utility functions work")

def test_signal():
    print("Testing Signal creation...")
    from core import Signal, SignalType, StrategyType
    signal = Signal(
        timestamp=1700000000000,
        strategy=StrategyType.MEAN_REVERSION,
        symbol="SOLUSDT",
        signal_type=SignalType.BUY,
        confidence=0.75,
        entry_price=100.0,
        stop_loss_price=95.0,
        take_profit_price=105.0,
        reason="Test"
    )
    assert signal.confidence == 0.75
    print("✓ Signal validation passed")

def test_exceptions():
    print("Testing Exception hierarchy...")
    from core.exceptions import (
        TradingException,
        ConfigurationError,
        MissingCredentialsError,
        is_critical_error,
        is_retryable_error
    )
    err = MissingCredentialsError("test")
    assert isinstance(err, TradingException)
    assert is_critical_error(err) is True
    from core.exceptions import RateLimitError
    rate_err = RateLimitError("rate")
    assert is_retryable_error(rate_err) is True
    print("✓ Exception handling works")

if __name__ == "__main__":
    tests = [
        test_imports,
        test_candle,
        test_position_pnl,
        test_config,
        test_logger,
        test_utils,
        test_signal,
        test_exceptions,
    ]
    passed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__} failed: {e}")
    print(f"\n✅ {passed}/{len(tests)} tests passed")
    sys.exit(0 if passed == len(tests) else 1)
