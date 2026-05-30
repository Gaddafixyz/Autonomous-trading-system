"""
Professional logging system with multiple logger types.

Provides console (colorized) and file logging with rotation.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional, Dict
import json
from datetime import datetime
from pathlib import Path

# Create logs directory if it doesn't exist
Path("logs").mkdir(exist_ok=True)


class ColoredFormatter(logging.Formatter):
    """Add color to console output based on log level."""
    COLORS = {
        logging.DEBUG: "\033[36m",      # Cyan
        logging.INFO: "\033[32m",       # Green
        logging.WARNING: "\033[33m",    # Yellow
        logging.ERROR: "\033[31m",      # Red
        logging.CRITICAL: "\033[41m",   # Red background
    }
    RESET = "\033[0m"

    def format(self, record):
        log_message = super().format(record)
        color = self.COLORS.get(record.levelno, self.RESET)
        return f"{color}{log_message}{self.RESET}"


class JsonFormatter(logging.Formatter):
    """JSON formatter for structured logging to files."""
    def format(self, record):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "funcName": record.funcName,
            "lineno": record.lineno,
        }
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


def setup_logger(
    name: str,
    level: int = logging.INFO,
    log_file: Optional[str] = None,
    console: bool = True,
) -> logging.Logger:
    """
    Create a logger with optional file and console handlers.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    # Clear existing handlers to avoid duplicates
    if logger.handlers:
        logger.handlers.clear()

    # Console handler (colored)
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_formatter = ColoredFormatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

    # File handler (JSON, rotating)
    if log_file:
        file_handler = RotatingFileHandler(
            log_file, maxBytes=100 * 1024 * 1024, backupCount=10
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(JsonFormatter())
        logger.addHandler(file_handler)

    return logger


# Singleton loggers for different concerns
class Logger:
    """Main application logger."""
    _instance: Optional[logging.Logger] = None

    @classmethod
    def get_logger(cls, name: str) -> logging.Logger:
        """Get a named logger (for modules)."""
        return setup_logger(name, log_file="logs/app.log")

    @classmethod
    def get_main_logger(cls) -> logging.Logger:
        if cls._instance is None:
            cls._instance = setup_logger(
                "trading_system", level=logging.INFO, log_file="logs/app.log"
            )
        return cls._instance


class TradeLogger:
    """Logger for trade events (entry, exit, partial fills)."""
    _logger: Optional[logging.Logger] = None

    @classmethod
    def _get_logger(cls) -> logging.Logger:
        if cls._logger is None:
            cls._logger = setup_logger(
                "trades", level=logging.INFO, log_file="logs/trades.log", console=False
            )
        return cls._logger

    @classmethod
    def log_entry(cls, symbol: str, side: str, entry_price: float,
                  quantity: float, stop_loss: float, take_profit: float,
                  strategy: str, reason: str) -> None:
        logger = cls._get_logger()
        logger.info(json.dumps({
            "event": "ENTRY",
            "symbol": symbol,
            "side": side,
            "entry_price": entry_price,
            "quantity": quantity,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "strategy": strategy,
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat(),
        }))

    @classmethod
    def log_exit(cls, symbol: str, side: str, exit_price: float,
                 quantity: float, pnl: float, pnl_pct: float,
                 reason: str) -> None:
        logger = cls._get_logger()
        logger.info(json.dumps({
            "event": "EXIT",
            "symbol": symbol,
            "side": side,
            "exit_price": exit_price,
            "quantity": quantity,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat(),
        }))


class PerformanceLogger:
    """Logger for periodic performance snapshots."""
    _logger: Optional[logging.Logger] = None

    @classmethod
    def _get_logger(cls) -> logging.Logger:
        if cls._logger is None:
            cls._logger = setup_logger(
                "performance", level=logging.INFO, log_file="logs/performance.log", console=False
            )
        return cls._logger

    @classmethod
    def log_daily_stats(cls, date: str, equity: float, daily_pnl: float,
                        drawdown: float, trades_today: int) -> None:
        logger = cls._get_logger()
        logger.info(json.dumps({
            "period": "daily",
            "date": date,
            "equity": equity,
            "daily_pnl": daily_pnl,
            "drawdown": drawdown,
            "trades": trades_today,
        }))


class StrategyLogger:
    """Logger for strategy signals."""
    _logger: Optional[logging.Logger] = None

    @classmethod
    def _get_logger(cls) -> logging.Logger:
        if cls._logger is None:
            cls._logger = setup_logger(
                "strategy", level=logging.INFO, log_file="logs/strategy.log", console=False
            )
        return cls._logger

    @classmethod
    def log_signal(cls, symbol: str, strategy: str, signal_type: str,
                   confidence: float, reason: str) -> None:
        logger = cls._get_logger()
        logger.info(json.dumps({
            "event": "SIGNAL",
            "symbol": symbol,
            "strategy": strategy,
            "signal": signal_type,
            "confidence": confidence,
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat(),
        }))


class RiskLogger:
    """Logger for risk management events."""
    _logger: Optional[logging.Logger] = None

    @classmethod
    def _get_logger(cls) -> logging.Logger:
        if cls._logger is None:
            cls._logger = setup_logger(
                "risk", level=logging.INFO, log_file="logs/risk.log", console=False
            )
        return cls._logger

    @classmethod
    def log_rejection(cls, reason: str, details: Dict) -> None:
        logger = cls._get_logger()
        logger.info(json.dumps({
            "event": "REJECTION",
            "reason": reason,
            "details": details,
            "timestamp": datetime.utcnow().isoformat(),
        }))


# Convenience singletons
trade_logger = TradeLogger()
performance_logger = PerformanceLogger()
strategy_logger = StrategyLogger()
risk_logger = RiskLogger()
