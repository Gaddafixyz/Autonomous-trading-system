"""
Configuration management for the trading system.

Loads settings from environment variables (via .env file) and provides
validated dataclasses for all configuration aspects.

All dataclasses are mutable (no frozen=True) so LiveTrader and tests
can override values without FrozenInstanceError.
"""

import os
from dataclasses import dataclass, field
from typing import Optional, Literal
from dotenv import load_dotenv

load_dotenv()


class ConfigError(Exception):
    """Raised when configuration is invalid."""
    pass


@dataclass
class BinanceConfig:
    """Binance API configuration."""
    api_key: str
    api_secret: str
    testnet: bool = True
    base_url: str = "https://testnet.binancefuture.com"

    def __post_init__(self):
        if not self.api_key or len(self.api_key) < 30:
            raise ConfigError("BINANCE_API_KEY must be at least 30 characters")
        if not self.api_secret or len(self.api_secret) < 30:
            raise ConfigError("BINANCE_API_SECRET must be at least 30 characters")
        # Auto-set mainnet URL when not on testnet
        if not self.testnet:
            self.base_url = "https://fapi.binance.com"


@dataclass
class TradingConfig:
    """Core trading parameters."""
    symbol: str = "SOLUSDT"
    leverage: float = 5.0
    margin_type: Literal["CROSS", "ISOLATED"] = "CROSS"
    max_open_positions: int = 5
    max_position_pct: float = 0.30   # Max 30% of account per position
    max_daily_loss_pct: float = 0.05  # 5% daily loss limit
    max_drawdown_pct: float = 0.10    # 10% max drawdown
    kelly_fraction: float = 0.25      # Conservative 25% Kelly
    min_order_qty: float = 0.1        # Minimum order quantity in base asset
    max_order_qty: float = 1000.0     # Maximum order quantity in base asset

    def __post_init__(self):
        if not 1.0 <= self.leverage <= 20.0:
            raise ConfigError("Leverage must be between 1 and 20")
        if self.max_open_positions < 1:
            raise ConfigError("max_open_positions must be >= 1")
        if not 0.0 < self.max_position_pct <= 1.0:
            raise ConfigError("max_position_pct must be between 0 and 1")
        if not 0.0 <= self.max_daily_loss_pct <= 1.0:
            raise ConfigError("max_daily_loss_pct must be between 0 and 1")
        if not 0.0 <= self.max_drawdown_pct <= 1.0:
            raise ConfigError("max_drawdown_pct must be between 0 and 1")
        if not 0.0 < self.kelly_fraction <= 1.0:
            raise ConfigError("kelly_fraction must be between 0 and 1")
        if self.min_order_qty <= 0:
            raise ConfigError("min_order_qty must be positive")
        if self.max_order_qty <= self.min_order_qty:
            raise ConfigError("max_order_qty must be greater than min_order_qty")


@dataclass
class StrategyConfig:
    """Strategy parameters for mean reversion and momentum."""
    # Mean Reversion (Bollinger Bands)
    bb_period: int = 20
    bb_std_dev: float = 2.0
    # Entry when price is within this many σ of the lower band (0.5 = half a std dev)
    bb_entry_threshold: float = 0.5

    # Momentum (EMA + ADX)
    ema_fast_period: int = 50
    ema_slow_period: int = 400
    adx_period: int = 14
    adx_threshold: float = 25.0
    volume_multiplier: float = 1.2     # Volume > 1.2x average

    # Hybrid combiner
    mr_weight: float = 0.6
    momentum_weight: float = 0.4
    min_signal_confidence: float = 0.3

    def __post_init__(self):
        if self.bb_period < 2:
            raise ConfigError("bb_period must be >= 2")
        if self.bb_std_dev <= 0:
            raise ConfigError("bb_std_dev must be positive")
        if self.ema_fast_period >= self.ema_slow_period:
            raise ConfigError("ema_fast_period must be < ema_slow_period")
        if self.adx_threshold <= 0:
            raise ConfigError("adx_threshold must be positive")
        if not 0.0 <= self.mr_weight <= 1.0:
            raise ConfigError("mr_weight must be between 0 and 1")
        if not 0.0 <= self.momentum_weight <= 1.0:
            raise ConfigError("momentum_weight must be between 0 and 1")
        if abs(self.mr_weight + self.momentum_weight - 1.0) > 1e-6:
            raise ConfigError("mr_weight + momentum_weight must equal 1.0")
        if not 0.0 <= self.min_signal_confidence <= 1.0:
            raise ConfigError("min_signal_confidence must be between 0 and 1")


@dataclass
class BacktestConfig:
    """Backtesting configuration."""
    start_date: str  # ISO format, e.g., "2024-01-01"
    end_date: str    # ISO format
    initial_capital: float = 10000.0
    commission_pct: float = 0.0008   # 0.08% round-trip (0.04% each side)
    slippage_entry_pct: float = 0.002  # 0.2%
    slippage_exit_pct: float = 0.001   # 0.1%
    data_interval: Literal["1m", "5m", "15m"] = "1m"

    def __post_init__(self):
        if self.initial_capital <= 0:
            raise ConfigError("initial_capital must be positive")
        if not 0.0 <= self.commission_pct <= 0.01:
            raise ConfigError("commission_pct must be between 0 and 0.01")
        if self.slippage_entry_pct < 0:
            raise ConfigError("slippage_entry_pct must be non-negative")
        if self.slippage_exit_pct < 0:
            raise ConfigError("slippage_exit_pct must be non-negative")


@dataclass
class LiveTradingConfig:
    """Live trading configuration (paper or real)."""
    mode: Literal["paper", "live"] = "paper"
    emergency_shutdown_on_critical: bool = True
    max_order_timeout_seconds: int = 30
    health_check_interval_seconds: int = 10

    def __post_init__(self):
        if self.max_order_timeout_seconds <= 0:
            raise ConfigError("max_order_timeout_seconds must be positive")
        if self.health_check_interval_seconds <= 0:
            raise ConfigError("health_check_interval_seconds must be positive")


class Config:
    """
    Main configuration aggregator.
    Loads all sub-configurations from environment variables.
    """

    def __init__(self):
        self.binance = BinanceConfig(
            api_key=os.getenv("BINANCE_API_KEY", ""),
            api_secret=os.getenv("BINANCE_API_SECRET", ""),
            testnet=os.getenv("BINANCE_TESTNET", "true").lower() == "true",
        )
        self.trading = TradingConfig(
            symbol=os.getenv("TRADING_SYMBOL", "SOLUSDT"),
            leverage=float(os.getenv("TRADING_LEVERAGE", "5.0")),
            margin_type=os.getenv("TRADING_MARGIN_TYPE", "CROSS"),  # type: ignore
            max_open_positions=int(os.getenv("MAX_OPEN_POSITIONS", "5")),
            max_position_pct=float(os.getenv("MAX_POSITION_PCT", "0.30")),
            max_daily_loss_pct=float(os.getenv("MAX_DAILY_LOSS_PCT", "0.05")),
            max_drawdown_pct=float(os.getenv("MAX_DRAWDOWN_PCT", "0.10")),
            kelly_fraction=float(os.getenv("KELLY_FRACTION", "0.25")),
            min_order_qty=float(os.getenv("MIN_ORDER_QTY", "0.1")),
            max_order_qty=float(os.getenv("MAX_ORDER_QTY", "1000.0")),
        )
        self.strategy = StrategyConfig(
            bb_period=int(os.getenv("BB_PERIOD", "20")),
            bb_std_dev=float(os.getenv("BB_STD_DEV", "2.0")),
            ema_fast_period=int(os.getenv("EMA_FAST_PERIOD", "50")),
            ema_slow_period=int(os.getenv("EMA_SLOW_PERIOD", "400")),
            adx_period=int(os.getenv("ADX_PERIOD", "14")),
            adx_threshold=float(os.getenv("ADX_THRESHOLD", "25.0")),
            mr_weight=float(os.getenv("MR_WEIGHT", "0.6")),
            momentum_weight=float(os.getenv("MOMENTUM_WEIGHT", "0.4")),
            min_signal_confidence=float(os.getenv("MIN_SIGNAL_CONFIDENCE", "0.3")),
        )
        self.backtest = BacktestConfig(
            start_date=os.getenv("BACKTEST_START_DATE", "2024-01-01"),
            end_date=os.getenv("BACKTEST_END_DATE", "2024-06-01"),
            initial_capital=float(os.getenv("BACKTEST_INITIAL_CAPITAL", "10000")),
        )
        self.live = LiveTradingConfig(
            mode=os.getenv("LIVE_MODE", "paper"),  # type: ignore
        )

    @classmethod
    def load_paper_trading(cls) -> "Config":
        """Convenience method: force paper trading mode."""
        cfg = cls()
        cfg.live.mode = "paper"
        return cfg

    @classmethod
    def load_live_trading(cls) -> "Config":
        """Convenience method: force live mode (use with caution)."""
        cfg = cls()
        cfg.live.mode = "live"
        return cfg
