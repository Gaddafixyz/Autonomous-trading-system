#!/usr/bin/env python3
"""
Test script for Phase 4 Risk Management.
"""

import sys
sys.path.insert(0, '.')

from risk_management import PositionManager, KellySizing, StopLossCalculator, PortfolioRisk, RiskMetrics
from core.types import OrderSide, Trade
from core.exceptions import PositionRejectedError, DailyLossExceededError


def test_position_manager():
    print("Testing PositionManager...")
    pm = PositionManager()
    # Open a position
    pos = pm.open_position(
        symbol="SOLUSDT",
        side=OrderSide.LONG,
        entry_price=100.0,
        quantity=10.0,
        leverage=5.0,
        stop_loss=95.0,
        take_profit=110.0,
        current_equity=10000.0
    )
    assert pos.symbol == "SOLUSDT"
    # Try to open another same symbol (should be rejected)
    try:
        pm.open_position("SOLUSDT", OrderSide.LONG, 101, 5, 5, 96, 111, 10000)
        assert False, "Should reject duplicate symbol"
    except PositionRejectedError:
        pass
    # Close position
    trade = pm.close_position("SOLUSDT", 110.0)
    assert trade.realized_pnl > 0
    print("✓ PositionManager passed")


def test_kelly_sizing():
    print("Testing KellySizing...")
    ks = KellySizing()
    # Simulate 20 trades: 12 wins (avg +100), 8 losses (avg -50)
    trades = []
    for _ in range(12):
        trades.append(Trade(0, "SOLUSDT", None, OrderSide.LONG, 100, 110, 10, 100, 10, 0, "", ""))
    for _ in range(8):
        trades.append(Trade(0, "SOLUSDT", None, OrderSide.LONG, 100, 95, 10, -50, -5, 0, "", ""))
    ks.update_trades(trades)
    frac = ks.compute_kelly_fraction()
    assert 0.01 <= frac <= 0.25
    size = ks.calculate_position_size(10000, 100, 95)
    assert size > 0
    print("✓ KellySizing passed")


def test_stop_loss():
    print("Testing StopLossCalculator...")
    # Create dummy candles
    from core.types import Candle, TimeFrame
    candles = [Candle(0, 100 + i, 102 + i, 98 + i, 101 + i, 1000, 101000, TimeFrame.FIVE_MINUTE) for i in range(50)]
    sl_calc = StopLossCalculator()
    sl, tp = sl_calc.compute_mr_levels(candles, OrderSide.LONG, 100.0)
    assert sl < 100 < tp
    sl, tp = sl_calc.compute_momentum_levels(candles, OrderSide.SHORT, 100.0)
    assert sl > 100 > tp
    print("✓ StopLossCalculator passed")


def test_portfolio_risk():
    print("Testing PortfolioRisk...")
    pr = PortfolioRisk(initial_equity=10000)
    pr.update_equity(9500, -500)
    try:
        pr.check_daily_loss()  # daily loss 5%? 500/10000=0.05, exactly at limit? Should not raise
        pr.check_drawdown(9500)  # drawdown 5% <10%
    except Exception as e:
        assert False, f"Unexpected exception: {e}"
    pr.update_equity(9000, -500)
    try:
        pr.check_daily_loss()  # now loss 1000/10000=10% >5%
        assert False, "Should raise DailyLossExceededError"
    except DailyLossExceededError:
        pass
    print("✓ PortfolioRisk passed")


def test_risk_metrics():
    print("Testing RiskMetrics...")
    rm = RiskMetrics()
    for i in range(100):
        rm.add_equity_point(10000 + i * 10)
    for _ in range(10):
        rm.add_trade(Trade(0, "SOLUSDT", None, OrderSide.LONG, 100, 110, 1, 100, 10, 0, "", ""))
    sharpe = rm.get_sharpe([0.01] * 100)
    assert sharpe > 0
    dd = rm.get_max_drawdown()
    assert dd >= 0
    print("✓ RiskMetrics passed")


if __name__ == "__main__":
    test_position_manager()
    test_kelly_sizing()
    test_stop_loss()
    test_portfolio_risk()
    test_risk_metrics()
    print("\n✅ All Phase 4 tests passed!")
