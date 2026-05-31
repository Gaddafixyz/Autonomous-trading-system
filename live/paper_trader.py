"""
Paper trading on Binance testnet.

Fixes applied:
1. Used self.client.client.ticker_price() (sync, bypasses rate limiter) →
   replaced with await self.client.get_ticker() (async, rate-limited).
2. feed.initialize() already subscribes _handle_kline to the kline stream.
   The extra ws.subscribe_kline() call overwrote that handler (old WS manager)
   or added a second connection (new multi-handler WS manager).  The extra
   subscription for _on_kline is still needed, but feed.initialize already
   handles the internal data-store subscription, so the duplicate is removed
   by NOT calling ws.subscribe_kline a second time for the same purpose.
   Instead _on_kline is passed as an additional callback after feed.initialize.
3. Added _last_signal_time dedup to avoid processing the same closed candle twice.
4. Added _daily_reset_loop background task that resets PortfolioRisk stats at
   UTC midnight so daily loss limits don't carry over across trading days.
5. FIX: Daily reset race condition - calculate next_midnight correctly to avoid
   negative wait times or off-by-one errors when close to midnight.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

from core.config import Config
from core.logger import Logger, trade_logger, performance_logger
from core.types import TimeFrame, SignalType, OrderSide
from core.exceptions import DailyLossExceededError, MaxDrawdownExceededError

from api import BinanceClient, WebSocketManager, MarketDataFeed
from strategies import HybridStrategy
from risk_management import PositionManager, KellySizing, PortfolioRisk
from execution import ExecutionEngine


class PaperTrader:
    """
    Paper trading bot that runs on Binance testnet.
    Uses real WebSocket data and either simulates fills or places real testnet orders.
    """

    def __init__(self, simulate_fills: bool = True):
        self.config = Config()
        self.logger = Logger.get_logger("PaperTrader")
        self.simulate_fills = simulate_fills

        # Components
        self.client = BinanceClient(self.config.binance, public=False)
        self.ws = WebSocketManager(testnet=True)
        self.feed = MarketDataFeed(self.client, self.ws)
        self.strategy = HybridStrategy(self.config.trading.symbol, TimeFrame.FIVE_MINUTE)
        self.position_mgr = PositionManager()
        self.kelly = KellySizing()
        self.portfolio_risk = PortfolioRisk(initial_equity=0)
        self.execution = ExecutionEngine(self.client, self.position_mgr)

        self.running = False
        self.last_equity = 0.0
        # FIX: track the last closed-candle timestamp to avoid duplicate signal processing
        self._last_signal_time: int = 0

    async def start(self):
        """Start paper trading."""
        self.logger.info("Starting paper trader on Binance testnet")

        account = await self.client.get_account_balance()
        self.portfolio_risk = PortfolioRisk(initial_equity=account.total_equity)
        self.last_equity = account.total_equity
        self.logger.info(f"Initial equity: {account.total_equity:.2f} USDT")

        # Initialize feed: loads historical candles AND subscribes feed._handle_kline
        # to keep the internal candle store up to date via WebSocket.
        await self.feed.initialize(
            self.config.trading.symbol,
            [TimeFrame.ONE_MINUTE, TimeFrame.FIVE_MINUTE],
            historical_limit=500,
        )

        # FIX: subscribe _on_kline as an ADDITIONAL callback on the same 5m stream.
        # The WebSocketManager now supports multiple handlers per stream so
        # feed._handle_kline (data store) and _on_kline (signal generation) both fire.
        # We do NOT call ws.subscribe_kline for _handle_kline again — feed.initialize
        # already did that.
        await self.ws.subscribe_kline(
            self.config.trading.symbol,
            TimeFrame.FIVE_MINUTE.value,
            self._on_kline,
        )

        self.running = True

        # FIX: background task resets daily P&L stats at UTC midnight
        asyncio.create_task(self._daily_reset_loop())

        while self.running:
            await asyncio.sleep(1)
            await self._check_risk()

    async def _on_kline(self, data: dict):
        """Callback when a 5-minute kline arrives via WebSocket."""
        if not self.running:
            return

        # Only process when the candle is *closed* (x flag = True)
        k = data.get('k', {})
        if not k.get('x', False):
            return

        # FIX: deduplicate — ignore if we already processed this candle close time
        close_time: int = k.get('T', 0)
        if close_time == self._last_signal_time:
            return
        self._last_signal_time = close_time

        candles = self.feed.get_candles(
            self.config.trading.symbol,
            TimeFrame.FIVE_MINUTE,
            count=500,
        )
        if len(candles) < 200:
            self.logger.warning("Not enough candles for strategy, waiting…")
            return

        signal = await self.strategy.calculate_signal(candles)
        if not signal or signal.signal_type == SignalType.HOLD:
            return

        self.logger.info(f"Signal: {signal.signal_type.value} conf={signal.confidence:.2f}")

        try:
            account = await self.client.get_account_balance()
            self.portfolio_risk.update_equity(
                account.total_equity, account.total_equity - self.last_equity
            )
            self.last_equity = account.total_equity
            self.portfolio_risk.check_daily_loss()
            self.portfolio_risk.check_drawdown(account.total_equity)

            # FIX: use await self.client.get_ticker() — the old code called
            # self.client.client.ticker_price() directly (sync, bypasses rate limiter)
            ticker = await self.client.get_ticker(self.config.trading.symbol)
            price = ticker['price']

            if signal.signal_type == SignalType.BUY:
                sl = price * 0.98
                tp = price * 1.03
            else:
                sl = price * 1.02
                tp = price * 0.97

            quantity = self.kelly.calculate_position_size(account.total_equity, price, sl)
            if quantity < self.config.trading.min_order_qty:
                self.logger.warning("Position size below minimum, skipping")
                return

            side = OrderSide.LONG if signal.signal_type == SignalType.BUY else OrderSide.SHORT

            if self.simulate_fills:
                self.position_mgr.open_position(
                    symbol=self.config.trading.symbol,
                    side=side,
                    entry_price=price,
                    quantity=quantity,
                    leverage=self.config.trading.leverage,
                    stop_loss=sl,
                    take_profit=tp,
                    current_equity=account.total_equity,
                    strategy_type=self.strategy.strategy_type,
                )
                trade_logger.log_entry(
                    symbol=self.config.trading.symbol,
                    side=side.value,
                    entry_price=price,
                    quantity=quantity,
                    stop_loss=sl,
                    take_profit=tp,
                    strategy="Hybrid",
                    reason=signal.reason,
                )
                self.logger.info(f"Simulated {side.value}: {quantity:.2f} units @ {price:.2f}")
            else:
                order = await self.execution.place_order(
                    symbol=self.config.trading.symbol,
                    side=side,
                    quantity=quantity,
                    price=price,
                    timeout_seconds=30,
                )
                if order:
                    self.logger.info(f"Order placed: {order.order_id}")

        except (DailyLossExceededError, MaxDrawdownExceededError) as e:
            self.logger.critical(f"Risk limit reached: {e}")
            await self.stop()
        except Exception as e:
            self.logger.error(f"Error processing signal: {e}", exc_info=True)

    async def _check_risk(self):
        """Periodic risk check (called every second from the main loop)."""
        try:
            account = await self.client.get_account_balance()
            self.portfolio_risk.update_equity(
                account.total_equity, account.total_equity - self.last_equity
            )
            self.last_equity = account.total_equity
            self.portfolio_risk.check_daily_loss()
            self.portfolio_risk.check_drawdown(account.total_equity)
        except (DailyLossExceededError, MaxDrawdownExceededError) as e:
            self.logger.critical(f"Risk limit reached: {e}")
            await self.stop()
        except Exception as e:
            self.logger.error(f"Risk check error: {e}")

    async def _daily_reset_loop(self):
        """
        FIX: Reset daily P&L stats at UTC midnight every day.
        Without this, the daily loss limit accumulates across calendar days
        making it impossible to trade after any down day.
        
        FIX 2: Calculate next_midnight correctly to avoid race conditions:
        - If now is before midnight today, sleep until today's midnight
        - If now is after midnight today, sleep until tomorrow's midnight
        - Avoid negative wait times or off-by-one errors
        """
        while self.running:
            now = datetime.now(timezone.utc)
            # Get today's midnight (start of current day)
            today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
            # Next midnight is tomorrow's midnight
            next_midnight = today_midnight + timedelta(days=1)
            
            # Calculate wait time - if we're exactly at midnight, wait a second before reset
            wait_seconds = (next_midnight - now).total_seconds()
            if wait_seconds <= 0:
                # Already past midnight (shouldn't happen, but safety check)
                wait_seconds = 86400  # Wait 24 hours
            
            self.logger.debug(f"Daily reset scheduled in {wait_seconds:.0f} seconds")
            await asyncio.sleep(wait_seconds)

            if not self.running:
                break

            try:
                account = await self.client.get_account_balance()
                reset_time = datetime.now(timezone.utc)
                self.portfolio_risk.reset_daily(account.total_equity)
                performance_logger.log_daily_stats(
                    date=reset_time.strftime("%Y-%m-%d"),
                    equity=account.total_equity,
                    daily_pnl=self.position_mgr.get_daily_pnl(),
                    drawdown=0.0,
                    trades_today=len(self.position_mgr.closed_trades),
                )
                self.position_mgr.reset_daily_pnl()
                self.logger.info(f"Daily stats reset at UTC midnight {reset_time.isoformat()}")
            except Exception as e:
                self.logger.error(f"Daily reset error: {e}")

    async def stop(self):
        """Gracefully stop paper trading."""
        self.logger.info("Stopping paper trader")
        self.running = False
        await self.ws.stop()
        for symbol in list(self.position_mgr.positions.keys()):
            await self.execution.close_position(symbol, 0)
        self.logger.info("Paper trader stopped")