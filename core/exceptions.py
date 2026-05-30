"""
Custom exception hierarchy for the trading system.

All exceptions inherit from TradingException and are categorized
for proper handling (retry, shutdown, etc.).
"""

from typing import Tuple


class TradingException(Exception):
    """Base exception for all trading system errors."""
    pass


# Configuration errors
class ConfigurationError(TradingException):
    """Base for configuration-related errors."""
    pass

class InvalidConfigError(ConfigurationError):
    """Invalid configuration parameter."""
    pass

class MissingCredentialsError(ConfigurationError):
    """API credentials missing or invalid."""
    pass


# API and connectivity errors
class APIError(TradingException):
    """Base for API-related errors."""
    pass

class ConnectionError(APIError):
    """Network connection error."""
    pass

class RateLimitError(APIError):
    """Rate limit exceeded."""
    pass

class AuthenticationError(APIError):
    """API key/secret authentication failed."""
    pass


# Market data errors
class MarketDataError(TradingException):
    """Base for market data errors."""
    pass

class InsufficientDataError(MarketDataError):
    """Not enough historical data for calculation."""
    pass

class DataValidationError(MarketDataError):
    """Invalid OHLCV or other data values."""
    pass


# Strategy errors
class StrategyError(TradingException):
    """Base for strategy-related errors."""
    pass

class InvalidSignalError(StrategyError):
    """Generated signal violates constraints."""
    pass

class InsufficientStrategyDataError(StrategyError):
    """Strategy needs more data to compute indicators."""
    pass


# Risk management errors
class RiskManagementError(TradingException):
    """Base for risk management rejections."""
    pass

class PositionRejectedError(RiskManagementError):
    """Risk rules reject a new position."""
    pass

class MaxDrawdownExceededError(RiskManagementError):
    """Max drawdown limit hit."""
    pass

class DailyLossExceededError(RiskManagementError):
    """Daily loss limit hit."""
    pass


# Execution errors
class ExecutionError(TradingException):
    """Base for order execution errors."""
    pass

class OrderPlacementError(ExecutionError):
    """Failed to place order on exchange."""
    pass

class OrderTimeoutError(ExecutionError):
    """Order not filled within timeout."""
    pass


# Backtesting errors
class BacktestError(TradingException):
    """Base for backtesting errors."""
    pass

class DataLoadError(BacktestError):
    """Failed to load historical data."""
    pass

class LookAheadBiasError(BacktestError):
    """Detected lookahead bias in backtest."""
    pass


# Utility functions for error classification
def is_critical_error(error: Exception) -> bool:
    """
    Determine if an error is critical enough to trigger emergency shutdown.
    """
    critical_types = (
        AuthenticationError,
        MissingCredentialsError,
        MaxDrawdownExceededError,
        DailyLossExceededError,
        LookAheadBiasError,
    )
    return isinstance(error, critical_types)


def is_retryable_error(error: Exception) -> bool:
    """
    Determine if an error can be retried (e.g., rate limit, connection timeout).
    """
    retryable_types = (
        ConnectionError,
        RateLimitError,
        OrderTimeoutError,
    )
    return isinstance(error, retryable_types)
