"""
Systemd daemon wrapper for running the trading bot continuously.
"""

import asyncio
import signal
import sys
from typing import Optional

from core.logger import Logger
from live.paper_trader import PaperTrader
from live.live_trader import LiveTrader


class TradingDaemon:
    """Main entry point for systemd service."""

    def __init__(self, mode: str = "paper", simulate_fills: bool = True):
        self.mode = mode
        self.simulate_fills = simulate_fills
        self.logger = Logger.get_logger("TradingDaemon")
        self.trader: Optional[PaperTrader] = None

    async def run(self):
        """Start the trading bot."""
        self.logger.info(f"Starting trading daemon in {self.mode} mode")
        if self.mode == "paper":
            self.trader = PaperTrader(simulate_fills=self.simulate_fills)
        elif self.mode == "live":
            self.trader = LiveTrader()
        else:
            self.logger.error(f"Unknown mode: {self.mode}")
            return

        # Setup signal handlers for graceful shutdown
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.shutdown()))

        await self.trader.start()

    async def shutdown(self):
        """Graceful shutdown."""
        self.logger.info("Shutdown signal received, stopping trader...")
        if self.trader:
            await self.trader.stop()
        self.logger.info("Trading daemon stopped")
        sys.exit(0)


def main():
    """Entry point for command line."""
    import argparse
    parser = argparse.ArgumentParser(description="Trading Bot Daemon")
    parser.add_argument("--mode", choices=["paper", "live"], default="paper", help="Trading mode")
    parser.add_argument("--simulate", action="store_true", help="Simulate fills (paper mode only)")
    args = parser.parse_args()

    daemon = TradingDaemon(mode=args.mode, simulate_fills=args.simulate)
    asyncio.run(daemon.run())


if __name__ == "__main__":
    main()
