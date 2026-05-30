"""
Real-time monitoring dashboard (console-based).
"""

import asyncio
from typing import Optional
from datetime import datetime

from core.logger import Logger
from api import BinanceClient
from risk_management import PositionManager


class Monitor:
    """Console dashboard updating every second."""

    def __init__(self, client: BinanceClient, position_mgr: PositionManager):
        self.client = client
        self.position_mgr = position_mgr
        self.logger = Logger.get_logger("Monitor")
        self.running = False

    async def start(self):
        self.running = True
        self.logger.info("Dashboard started. Press Ctrl+C to stop.")
        while self.running:
            await self._refresh()
            await asyncio.sleep(1)

    async def _refresh(self):
        """Fetch latest data and print to console."""
        try:
            account = await self.client.get_account_balance()
            positions = self.position_mgr.get_open_positions()
            # Clear screen (optional)
            print("\033[2J\033[H", end="")
            print("=" * 50)
            print(f"TRADING DASHBOARD - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("=" * 50)
            print(f"Total Equity:    {account.total_equity:.2f} USDT")
            print(f"Available:       {account.available_balance:.2f} USDT")
            print(f"Unrealized PnL:  {account.unrealized_pnl:.2f} USDT")
            print(f"Daily PnL:       {account.daily_pnl:.2f} USDT")
            print(f"Open Positions:  {len(positions)}")
            for pos in positions:
                print(f"  {pos.symbol} {pos.side.value} | qty={pos.quantity:.2f} | entry={pos.entry_price:.2f}")
            print("=" * 50)
        except Exception as e:
            self.logger.error(f"Dashboard error: {e}")

    async def stop(self):
        self.running = False
