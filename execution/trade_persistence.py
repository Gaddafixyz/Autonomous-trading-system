"""
SQLite and JSON persistence for completed trades.
"""

import sqlite3
import json
from pathlib import Path
from typing import List
from datetime import datetime

from core.types import Trade
from core.logger import Logger


class TradePersistence:
    """Store trades in SQLite database and optional JSON backup."""

    def __init__(self, db_path: str = "data/trades.db"):
        self.db_path = db_path
        self.logger = Logger.get_logger("TradePersistence")
        Path("data").mkdir(exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Create trades table if not exists."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp INTEGER,
                    symbol TEXT,
                    side TEXT,
                    entry_price REAL,
                    exit_price REAL,
                    quantity REAL,
                    realized_pnl REAL,
                    pnl_percent REAL,
                    duration_seconds INTEGER,
                    entry_reason TEXT,
                    exit_reason TEXT,
                    created_at TEXT
                )
            """)

    def save_trade(self, trade: Trade):
        """Save a single trade to database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO trades (
                        timestamp, symbol, side, entry_price, exit_price,
                        quantity, realized_pnl, pnl_percent, duration_seconds,
                        entry_reason, exit_reason, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    trade.timestamp,
                    trade.symbol,
                    trade.side.value,
                    trade.entry_price,
                    trade.exit_price,
                    trade.quantity,
                    trade.realized_pnl,
                    trade.pnl_percent,
                    trade.duration_seconds,
                    trade.entry_reason,
                    trade.exit_reason,
                    datetime.utcnow().isoformat()
                ))
            self.logger.debug(f"Saved trade {trade.symbol} PnL={trade.realized_pnl:.2f}")
        except Exception as e:
            self.logger.error(f"Failed to save trade: {e}")

    def load_trades(self, limit: int = 1000) -> List[dict]:
        """Load recent trades as dicts."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def export_json(self, filepath: str = "data/trades_export.json"):
        """Export all trades to JSON file for backup."""
        trades = self.load_trades(limit=10000)
        with open(filepath, "w") as f:
            json.dump(trades, f, indent=2)
        self.logger.info(f"Exported {len(trades)} trades to {filepath}")
