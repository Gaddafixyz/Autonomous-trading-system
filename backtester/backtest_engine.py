"""
Main backtest engine: replay candles, generate signals, simulate fills, track equity.
"""

import asyncio
from typing import List, Optional

from core.types import (
    Candle, Signal, OrderSide, BacktestMetrics,
    TimeFrame, SignalType, StrategyType, Trade
)
from core.config import Config
from core.logger import Logger
from core.exceptions import PositionRejectedError
from core.utils import calculate_sharpe_ratio, calculate_max_drawdown

from strategies.hybrid import HybridStrategy
from risk_management.position_manager import PositionManager
from risk_management.kelly_sizing import KellySizing
from risk_management.stop_loss import StopLossCalculator
from backtester.fill_simulator import FillSimulator


class BacktestEngine:
    """Event-driven backtest simulation."""

    def __init__(self, initial_equity: float = 10000.0):
        self.config = Config().trading
        self.backtest_config = Config().backtest
        self.logger = Logger.get_logger("BacktestEngine")

        self.initial_equity = initial_equity
        self.equity_curve: List[float] = [initial_equity]
        self.equity_timestamps: List[int] = []
        self._running_equity = initial_equity

        # Components
        self.strategy = None
        self.position_mgr = PositionManager()
        self.kelly = KellySizing()
        self.sl_calc = StopLossCalculator()
        self.fill_sim = FillSimulator()

        # Metrics tracking
        self.total_trades = 0
        self.winning_trades = 0
        self.sum_wins = 0.0
        self.sum_losses = 0.0

    def get_trades(self) -> List[Trade]:
        """Expose completed trades for Reporter and external analysis."""
        return list(self.position_mgr.closed_trades)

    async def run(
        self,
        candles: List[Candle],
        symbol: str,
        timeframe: TimeFrame
    ) -> BacktestMetrics:
        self.logger.info(f"Starting backtest on {len(candles)} {timeframe.value} candles")
        self.strategy = HybridStrategy(symbol, timeframe)

        for idx, candle in enumerate(candles):
            current_window = candles[:idx + 1]
            signal = await self.strategy.calculate_signal(current_window)

            await self._update_account(candle)

            if signal and signal.signal_type != SignalType.HOLD:
                await self._process_signal(signal, candle, current_window)

            await self._check_exits(candle, current_window)

        # Force-close any remaining open positions at the last price
        open_positions = self.position_mgr.get_open_positions()
        if open_positions:
            last_candle = candles[-1]
            self.logger.info(
                f"Closing {len(open_positions)} open position(s) at last price {last_candle.close}"
            )
            for pos in open_positions:
                trade = self.position_mgr.close_position(pos.symbol, last_candle.close)
                if trade:
                    self._running_equity += trade.realized_pnl
                    self.total_trades += 1
                    if trade.realized_pnl > 0:
                        self.winning_trades += 1
                        self.sum_wins += trade.realized_pnl
                    else:
                        self.sum_losses += abs(trade.realized_pnl)
                    self.kelly.update_trades([trade])
            await self._update_account(last_candle)

        return self._compute_metrics()

    async def _update_account(self, candle: Candle):
        """Update current equity based on closed and unrealized PnL."""
        total_closed_pnl = sum(t.realized_pnl for t in self.position_mgr.closed_trades)
        total_unrealized = sum(
            pos.unrealized_pnl(candle.close) for pos in self.position_mgr.get_open_positions()
        )
        self._running_equity = self.initial_equity + total_closed_pnl + total_unrealized
        self.equity_curve.append(self._running_equity)
        self.equity_timestamps.append(candle.timestamp)

    async def _process_signal(self, signal: Signal, candle: Candle, window: List[Candle]):
        """Process a trading signal: check if we can open a position."""
        if signal.signal_type not in (SignalType.BUY, SignalType.SELL):
            return

        # Do not open a new position if already holding one for this symbol
        if signal.symbol in self.position_mgr.positions:
            self.logger.debug(f"Already have open position for {signal.symbol}, skipping")
            return

        side = OrderSide.LONG if signal.signal_type == SignalType.BUY else OrderSide.SHORT
        equity = self._running_equity

        kelly_fraction = self.kelly.compute_kelly_fraction()
        sl_distance = candle.close * 0.02
        quantity = self.kelly.calculate_position_size(
            equity, candle.close, candle.close - sl_distance
        )
        if quantity < self.config.min_order_qty:
            return

        mr_confidence = 0.6
        sl, tp = self.sl_calc.compute_hybrid_levels(window, side, candle.close, mr_confidence)

        fill_price = self.fill_sim.simulate_entry(
            candle, side, signal.entry_price or candle.close
        )
        commission = self.fill_sim.apply_commission(fill_price * quantity)

        try:
            # FIX: pass strategy_type so the closed Trade records the correct StrategyType
            self.position_mgr.open_position(
                symbol=signal.symbol,
                side=side,
                entry_price=fill_price,
                quantity=quantity,
                leverage=self.config.leverage,
                stop_loss=sl,
                take_profit=tp,
                current_equity=equity,
                strategy_type=StrategyType.HYBRID,
            )
            self._running_equity -= commission
        except PositionRejectedError as e:
            self.logger.warning(f"Position rejected: {e}")

    async def _check_exits(self, candle: Candle, window: List[Candle]):
        """Check for stop-loss or take-profit triggers."""
        for symbol, pos in list(self.position_mgr.positions.items()):
            if pos.status.value != "OPEN":
                continue
            should_exit = False
            exit_price = None
            if pos.side == OrderSide.LONG:
                if candle.low <= pos.stop_loss_price:
                    should_exit = True
                    exit_price = pos.stop_loss_price
                elif candle.high >= pos.take_profit_price:
                    should_exit = True
                    exit_price = pos.take_profit_price
            else:  # SHORT
                if candle.high >= pos.stop_loss_price:
                    should_exit = True
                    exit_price = pos.stop_loss_price
                elif candle.low <= pos.take_profit_price:
                    should_exit = True
                    exit_price = pos.take_profit_price

            if should_exit:
                fill_price = self.fill_sim.simulate_exit(candle, pos.side, exit_price)
                commission = self.fill_sim.apply_commission(fill_price * pos.quantity)
                trade = self.position_mgr.close_position(symbol, fill_price)
                if trade:
                    self._running_equity -= commission
                    self._running_equity += trade.realized_pnl
                    self.total_trades += 1
                    if trade.realized_pnl > 0:
                        self.winning_trades += 1
                        self.sum_wins += trade.realized_pnl
                    else:
                        self.sum_losses += abs(trade.realized_pnl)
                    self.kelly.update_trades([trade])

    def _compute_metrics(self) -> BacktestMetrics:
        """Calculate final performance metrics from equity curve and trades."""
        total_return = (self._running_equity - self.initial_equity) / self.initial_equity
        returns = []
        for i in range(1, len(self.equity_curve)):
            if self.equity_curve[i - 1] != 0:
                ret = (self.equity_curve[i] - self.equity_curve[i - 1]) / self.equity_curve[i - 1]
                returns.append(ret)
        sharpe = calculate_sharpe_ratio(returns) if returns else 0.0
        max_dd, _, _ = calculate_max_drawdown(self.equity_curve)
        win_rate = self.winning_trades / self.total_trades if self.total_trades > 0 else 0.0
        profit_factor = self.sum_wins / self.sum_losses if self.sum_losses > 0 else float('inf')
        avg_win = self.sum_wins / self.winning_trades if self.winning_trades else 0
        losing = self.total_trades - self.winning_trades
        avg_loss = self.sum_losses / losing if losing > 0 else 0

        return BacktestMetrics(
            total_return=total_return,
            sharpe_ratio=sharpe,
            max_drawdown=max_dd,
            win_rate=win_rate,
            profit_factor=profit_factor,
            total_trades=self.total_trades,
            winning_trades=self.winning_trades,
            losing_trades=losing,
            avg_win=avg_win,
            avg_loss=avg_loss,
            avg_trade_duration_seconds=0,
            final_equity=self._running_equity,
            initial_equity=self.initial_equity,
        )
