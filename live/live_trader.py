"""
Live trading on Binance mainnet.
Only use after extensive paper trading and with small capital.
"""

import asyncio  # FIX: was missing, causing NameError on asyncio.sleep(5) in start()

from live.paper_trader import PaperTrader
from core.logger import Logger
from core.exceptions import DailyLossExceededError, MaxDrawdownExceededError


class LiveTrader(PaperTrader):
    """
    Live trading on mainnet.
    Overrides paper trader to enforce stricter limits and use mainnet API.
    """

    def __init__(self, max_daily_loss_pct: float = 0.03, max_drawdown_pct: float = 0.05):
        super().__init__(simulate_fills=False)
        self.logger = Logger.get_logger("LiveTrader")

        # FIX: direct attribute assignment works now that config dataclasses are
        # no longer frozen (removing frozen=True was required to allow these overrides
        # without raising FrozenInstanceError).
        self.config.trading.max_daily_loss_pct = max_daily_loss_pct
        self.config.trading.max_drawdown_pct = max_drawdown_pct

        # Switch to mainnet
        self.config.binance.testnet = False
        self.config.binance.base_url = "https://fapi.binance.com"

        # Recreate client with mainnet config
        from api import BinanceClient
        self.client = BinanceClient(self.config.binance, public=False)
        self.logger.warning("LIVE TRADING MODE ACTIVE – REAL MONEY")

    async def start(self):
        """Override start to add a 5-second countdown before going live."""
        self.logger.critical("STARTING LIVE TRADING WITH REAL FUNDS")
        self.logger.critical(f"Daily loss limit: {self.config.trading.max_daily_loss_pct:.2%}")
        self.logger.critical(f"Max drawdown limit: {self.config.trading.max_drawdown_pct:.2%}")
        # Short pause to allow operator to abort (Ctrl-C) before any orders
        await asyncio.sleep(5)
        await super().start()
