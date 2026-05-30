"""
Paper trading on Binance testnet.
Uses real WebSocket data, but can either:
- Place real small orders on testnet (requires API keys)
- Simulate fills locally for risk-free testing
"""

import asyncio
from typing import Optional

from core.config import Config
from core.logger import Logger, trade_logger
from core.types import TimeFrame, SignalType, OrderSide
from core.exceptions import DailyLossExceededError, MaxDrawdownExceededError

from api import BinanceClient, WebSocketManager, MarketDataFeed
from strategies import HybridStrategy
from risk_management import PositionManager, KellySizing, PortfolioRisk
from execution import ExecutionEngine


class PaperTrader:
    """
    Paper trading bot that runs on Binance testnet.
    Uses real WebSocket data and executes orders (or simulates fills).
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
        self._last_signal_time = 0  # prevent duplicate signals

    async def start(self):
        """Start paper trading."""
        self.logger.info("Starting paper trader on Binance testnet")

        account = await self.client.get_account_balance()
        self.portfolio_risk = PortfolioRisk(initial_equity=account.total_equity)
        self.last_equity = account.total_equity
        self.logger.info(f"Initial equity: {account.total_equity:.2f} USDT")

        await self.feed.initialize(
            self.config.trading.symbol,
            [TimeFrame.ONE_MINUTE, TimeFrame.FIVE_MINUTE],
            historical_limit=500
        )

        await self.ws.subscribe_kline(
            self.config.trading.symbol,
            TimeFrame.FIVE_MINUTE.value,
            self._on_kline
        )

        self.running = True
        while self.running:
            await asyncio.sleep(1)
            await self._check_risk()

    async def _on_kline(self, data: dict):
        """Callback when a 5-minute candle is updated or closed."""
        if not self.running:
            return

        # Only process when candle is closed (x == True)
        k = data.get('k', {})
        if not k.get('x', False):
            return

        # Deduplicate: same candle close time
        close_time = k.get('t')
        if close_time == self._last_signal_time:
            return
        self._last_signal_time = close_time

        candles = self.feed.get_candles(
            self.config.trading.symbol,
            TimeFrame.FIVE_MINUTE,
            count=500
        )
        if len(candles) < 200:
            self.logger.warning("Not enough candles for strategy")
            return

        signal = await self.strategy.calculate_signal(candles)
        if not signal or signal.signal_type == SignalType.HOLD:
            return

        self.logger.info(f"Signal: {signal.signal_type.value} with conf {signal.confidence:.2f}")

        try:
            account = await self.client.get_account_balance()
            self.portfolio_risk.update_equity(account.total_equity, account.total_equity - self.last_equity)
            self.last_equity = account.total_equity
            self.portfolio_risk.check_daily_loss()
            self.portfolio_risk.check_drawdown(account.total_equity)

            ticker = await self.client.get_ticker(self.config.trading.symbol)
            price = ticker['price']

            if signal.signal_type == SignalType.BUY:
                sl = price * 0.98
                tp = price * 1.03
            else:
                sl = price * 1.02
                tp = price * 0.97

            quantity = self.kelly.calculate_position_size(
                account.total_equity, price, sl
            )
            if quantity < 0.1:
                self.logger.warning("Position size too small, skipping")
                return

            if self.simulate_fills:
                side = OrderSide.LONG if signal.signal_type == SignalType.BUY else OrderSide.SHORT
                self.position_mgr.open_position(
                    symbol=self.config.trading.symbol,
                    side=side,
                    entry_price=price,
                    quantity=quantity,
                    leverage=self.config.trading.leverage,
                    stop_loss=sl,
                    take_profit=tp,
                    current_equity=account.total_equity
                )
                trade_logger.log_entry(
                    symbol=self.config.trading.symbol,
                    side=side.value,
                    entry_price=price,
                    quantity=quantity,
                    stop_loss=sl,
                    take_profit=tp,
                    strategy="Hybrid",
                    reason=signal.reason
                )
                self.logger.info(f"Simulated {side.value} order: {quantity:.2f} SOL @ {price:.2f}")
            else:
                order = await self.execution.place_order(
                    symbol=self.config.trading.symbol,
                    side=OrderSide.LONG if signal.signal_type == SignalType.BUY else OrderSide.SHORT,
                    quantity=quantity,
                    price=price,
                    timeout_seconds=30
                )
                if order:
                    self.logger.info(f"Order placed: {order.order_id}")

        except (DailyLossExceededError, MaxDrawdownExceededError) as e:
            self.logger.critical(f"Risk limit reached: {e}")
            await self.stop()
        except Exception as e:
            self.logger.error(f"Error processing signal: {e}", exc_info=True)

    async def _check_risk(self):
        try:
            account = await self.client.get_account_balance()
            self.portfolio_risk.update_equity(account.total_equity, account.total_equity - self.last_equity)
            self.last_equity = account.total_equity
            self.portfolio_risk.check_daily_loss()
            self.portfolio_risk.check_drawdown(account.total_equity)
        except (DailyLossExceededError, MaxDrawdownExceededError) as e:
            self.logger.critical(f"Risk limit reached: {e}")
            await self.stop()
        except Exception as e:
            self.logger.error(f"Risk check error: {e}")

    async def stop(self):
        self.logger.info("Stopping paper trader")
        self.running = False
        await self.ws.stop()
        for symbol in list(self.position_mgr.positions.keys()):
            await self.execution.close_position(symbol, 0)
        self.logger.info("Paper trader stopped")
