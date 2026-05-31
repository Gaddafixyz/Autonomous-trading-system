"""
Mathematical utilities for trading:
- Position sizing (Kelly Criterion)
- Performance metrics (Sharpe, Sortino, drawdown)
- Technical indicators (SMA, EMA, BB, ATR, RSI, ADX)

Fixes applied:
1. ADX calculation: added guard against atr[i] == 0 to prevent division by zero
   (rare on real price data, but can occur on synthetic/test data)
"""

import math
from typing import List, Tuple, Optional
import numpy as np


# ---------- Position Sizing ----------
def calculate_kelly_fraction(
    win_rate: float,
    avg_win: float,
    avg_loss: float,
    kelly_fraction: float = 0.25,
) -> float:
    """
    Calculate conservative Kelly fraction.

    Args:
        win_rate: Probability of winning (0.0 to 1.0)
        avg_win: Average profit on winning trades
        avg_loss: Average loss on losing trades (positive value)
        kelly_fraction: Fraction of full Kelly to use (0.0 to 1.0)

    Returns:
        Fraction of capital to risk (clamped between 0.01 and 0.25)
    """
    if avg_loss <= 0:
        return 0.01
    payoff_ratio = avg_win / avg_loss
    if payoff_ratio <= 0:
        return 0.01
    # Full Kelly formula: f* = (p * b - q) / b
    q = 1.0 - win_rate
    f_star = (win_rate * payoff_ratio - q) / payoff_ratio
    # Apply conservative fraction
    f = f_star * kelly_fraction
    # Clamp to reasonable bounds: min 0.01%, max 25% of capital per trade
    return max(0.0001, min(0.25, f))


def calculate_position_size(
    equity: float,
    entry_price: float,
    stop_loss_price: float,
    risk_fraction: float,
    leverage: float,
    min_quantity: float = 1.0,
    max_quantity: float = 1000.0,
) -> float:
    """
    Calculate position size in base asset (e.g., SOL).

    Args:
        equity: Total account equity in USDT
        entry_price: Entry price per unit
        stop_loss_price: Stop loss price
        risk_fraction: Fraction of equity to risk (from Kelly)
        leverage: Leverage multiplier
        min_quantity: Minimum trade size
        max_quantity: Maximum trade size

    Returns:
        Quantity of base asset to buy/sell
    """
    # Risk amount in USDT
    risk_amount = equity * risk_fraction
    # Stop loss distance in price units
    sl_distance = abs(entry_price - stop_loss_price)
    if sl_distance == 0:
        return min_quantity
    # Position size (without leverage)
    position_size = risk_amount / sl_distance
    # Apply leverage (notional value = position_size * entry_price * leverage)
    # But we return base quantity, not notional.
    # Actually, the formula: position_size = risk_amount / (sl_distance * leverage)
    # Because leveraged position multiplies the PnL.
    position_size = risk_amount / (sl_distance * leverage)
    # Apply min/max
    return max(min_quantity, min(max_quantity, position_size))


# ---------- Performance Metrics ----------
def calculate_sharpe_ratio(
    returns: List[float],
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    """
    Calculate annualized Sharpe ratio.
    """
    if len(returns) < 2:
        return 0.0
    excess_returns = [r - risk_free_rate for r in returns]
    mean_return = np.mean(excess_returns)
    std_return = np.std(excess_returns)
    if std_return == 0:
        return 0.0
    return (mean_return / std_return) * math.sqrt(periods_per_year)


def calculate_sortino_ratio(
    returns: List[float],
    target_return: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    """
    Calculate Sortino ratio (downside risk only).
    """
    if len(returns) < 2:
        return 0.0
    downside_returns = [min(0, r - target_return) for r in returns]
    downside_std = np.std(downside_returns)
    if downside_std == 0:
        return 0.0
    mean_return = np.mean(returns) - target_return
    return (mean_return / downside_std) * math.sqrt(periods_per_year)


def calculate_max_drawdown(equity_curve: List[float]) -> Tuple[float, int, int]:
    """
    Calculate maximum drawdown and its start/end indices.

    Returns:
        (drawdown_pct, start_index, end_index)
    """
    if len(equity_curve) < 2:
        return 0.0, 0, 0
    peak = equity_curve[0]
    max_dd = 0.0
    start_idx = 0
    end_idx = 0
    temp_start = 0
    for i, value in enumerate(equity_curve):
        if value > peak:
            peak = value
            temp_start = i
        dd = (peak - value) / peak if peak != 0 else 0
        if dd > max_dd:
            max_dd = dd
            start_idx = temp_start
            end_idx = i
    return max_dd, start_idx, end_idx


def calculate_win_rate(wins: int, total: int) -> float:
    """Win rate as a fraction."""
    if total == 0:
        return 0.0
    return wins / total


def calculate_profit_factor(sum_wins: float, sum_losses: float) -> float:
    """Profit factor = total wins / total losses (absolute)."""
    if sum_losses == 0:
        return float('inf') if sum_wins > 0 else 0.0
    return abs(sum_wins / sum_losses)


# ---------- Technical Indicators ----------
def calculate_sma(prices: List[float], period: int) -> List[float]:
    """Simple Moving Average."""
    if len(prices) < period:
        return []
    sma = []
    for i in range(period - 1, len(prices)):
        sma.append(sum(prices[i - period + 1:i + 1]) / period)
    return sma


def calculate_ema(prices: List[float], period: int) -> List[float]:
    """Exponential Moving Average (using smoothing factor 2/(period+1))."""
    if len(prices) < period:
        return []
    multiplier = 2.0 / (period + 1)
    ema = [prices[0]]  # initialize with first price
    for price in prices[1:]:
        ema.append((price - ema[-1]) * multiplier + ema[-1])
    # Return only the values after we have enough history (period)
    return ema[period - 1:]


def calculate_ema_full(prices: List[float], period: int) -> List[float]:
    """
    Return EMA values for all indices (with NaN for insufficient data).
    
    Note: Early EMA values (< period) are biased due to initialization with prices[0].
    These early values should be treated with caution; some traders discard the first
    period*2 values to ensure sufficient warm-up time.
    """
    if len(prices) < period:
        return [float('nan')] * len(prices)
    multiplier = 2.0 / (period + 1)
    ema = [prices[0]]
    for price in prices[1:]:
        ema.append((price - ema[-1]) * multiplier + ema[-1])
    # Pad with NaNs for first (period-1) values
    return [float('nan')] * (period - 1) + ema[period - 1:]


def calculate_bollinger_bands(
    prices: List[float], period: int = 20, num_std: float = 2.0
) -> Tuple[List[float], List[float], List[float]]:
    """
    Calculate Bollinger Bands: middle (SMA), upper, lower.
    Returns three lists of equal length (same as input prices, NaN for insufficient data).
    """
    n = len(prices)
    middle = [float('nan')] * n
    upper = [float('nan')] * n
    lower = [float('nan')] * n
    if n < period:
        return middle, upper, lower

    for i in range(period - 1, n):
        window = prices[i - period + 1:i + 1]
        sma = sum(window) / period
        variance = sum((x - sma) ** 2 for x in window) / period
        std = math.sqrt(variance)
        middle[i] = sma
        upper[i] = sma + num_std * std
        lower[i] = sma - num_std * std
    return middle, upper, lower


def calculate_atr(
    high: List[float], low: List[float], close: List[float], period: int = 14
) -> List[float]:
    """
    Average True Range.
    Returns list of ATR values (same length as input, NaN for insufficient data).
    """
    n = len(high)
    if n < period:
        return [float('nan')] * n
    tr = [0.0] * n
    for i in range(1, n):
        hl = high[i] - low[i]
        hc = abs(high[i] - close[i-1])
        lc = abs(low[i] - close[i-1])
        tr[i] = max(hl, hc, lc)
    # First ATR is simple average of first 'period' TRs
    atr = [float('nan')] * n
    atr[period-1] = sum(tr[1:period]) / period  # exclude first zero
    for i in range(period, n):
        atr[i] = (atr[i-1] * (period-1) + tr[i]) / period
    return atr


def calculate_rsi(prices: List[float], period: int = 14) -> List[float]:
    """
    Relative Strength Index.
    Returns list of RSI values (0-100, NaN for insufficient data).
    """
    n = len(prices)
    if n < period + 1:
        return [float('nan')] * n
    rsi = [float('nan')] * n
    gains = [0.0] * n
    losses = [0.0] * n
    for i in range(1, n):
        diff = prices[i] - prices[i-1]
        if diff > 0:
            gains[i] = diff
        else:
            losses[i] = -diff
    avg_gain = sum(gains[1:period+1]) / period
    avg_loss = sum(losses[1:period+1]) / period
    for i in range(period, n):
        if avg_loss == 0:
            rsi[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i] = 100 - (100 / (1 + rs))
        # Update averages
        avg_gain = (avg_gain * (period-1) + gains[i+1]) / period if i+1 < n else avg_gain
        avg_loss = (avg_loss * (period-1) + losses[i+1]) / period if i+1 < n else avg_loss
    return rsi


def calculate_adx(
    high: List[float], low: List[float], close: List[float], period: int = 14
) -> List[float]:
    """
    Average Directional Index (ADX).
    Returns list of ADX values (0-100, NaN for insufficient data).
    
    FIX: Added guard against atr[i] == 0 to prevent division by zero
    (rare on real price data, but possible on synthetic/test data).
    """
    n = len(high)
    if n < 2 * period:
        return [float('nan')] * n

    # True Range
    tr = [0.0] * n
    for i in range(1, n):
        hl = high[i] - low[i]
        hc = abs(high[i] - close[i-1])
        lc = abs(low[i] - close[i-1])
        tr[i] = max(hl, hc, lc)

    # Directional movements
    plus_dm = [0.0] * n
    minus_dm = [0.0] * n
    for i in range(1, n):
        up = high[i] - high[i-1]
        down = low[i-1] - low[i]
        if up > down and up > 0:
            plus_dm[i] = up
        else:
            plus_dm[i] = 0
        if down > up and down > 0:
            minus_dm[i] = down
        else:
            minus_dm[i] = 0

    # Smoothed averages
    atr = [0.0] * n
    plus_di = [0.0] * n
    minus_di = [0.0] * n

    # First values: simple average
    atr[period] = sum(tr[1:period+1]) / period
    
    # FIX: Guard against zero ATR
    if atr[period] > 0:
        plus_di[period] = 100 * (sum(plus_dm[1:period+1]) / period) / atr[period]
        minus_di[period] = 100 * (sum(minus_dm[1:period+1]) / period) / atr[period]
    else:
        plus_di[period] = 0.0
        minus_di[period] = 0.0

    for i in range(period+1, n):
        atr[i] = (atr[i-1] * (period-1) + tr[i]) / period
        
        # FIX: Guard against zero ATR division
        if atr[i] > 1e-10:  # Use small epsilon instead of exact zero
            plus_di[i] = 100 * ((plus_di[i-1] * (period-1) + plus_dm[i]) / period) / atr[i]
            minus_di[i] = 100 * ((minus_di[i-1] * (period-1) + minus_dm[i]) / period) / atr[i]
        else:
            plus_di[i] = plus_di[i-1]
            minus_di[i] = minus_di[i-1]

    # DX and ADX
    dx = [0.0] * n
    for i in range(period, n):
        di_sum = plus_di[i] + minus_di[i]
        if di_sum == 0:
            dx[i] = 0
        else:
            dx[i] = 100 * abs(plus_di[i] - minus_di[i]) / di_sum

    adx = [float('nan')] * n
    # First ADX is simple average of first 'period' DX values
    if n >= 2*period:
        adx[2*period-1] = sum(dx[period:2*period]) / period
        for i in range(2*period, n):
            adx[i] = (adx[i-1] * (period-1) + dx[i]) / period

    return adx