"""
Live trading on Binance mainnet.
Only use after extensive paper trading and with small capital.
"""

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
        # Override risk limits to be stricter for live
        self.config.trading.max_daily_loss_pct = max_daily_loss_pct
        self.config.trading.max_drawdown_pct = max_drawdown_pct
        # Force testnet = False
        self.config.binance.testnet = False
        self.config.binance.base_url = "https://fapi.binance.com"
        # Recreate client with mainnet
        from api import BinanceClient
        self.client = BinanceClient(self.config.binance, public=False)
        self.logger.warning("LIVE TRADING MODE ACTIVE – REAL MONEY")

    async def start(self):
        """Override start to add extra confirmation."""
        self.logger.critical("STARTING LIVE TRADING WITH REAL FUNDS")
        self.logger.critical(f"Daily loss limit: {self.config.trading.max_daily_loss_pct:.2%}")
        self.logger.critical(f"Max drawdown limit: {self.config.trading.max_drawdown_pct:.2%}")
        # Wait for manual confirmation (optional)
        # For automated daemon, remove this wait
        await asyncio.sleep(5)
        await super().start()
