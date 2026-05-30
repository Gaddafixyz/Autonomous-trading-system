"""
Backtesting engine: historical simulation with realistic fills and metrics.
"""

from backtester.data_loader import DataLoader
from backtester.backtest_engine import BacktestEngine
from backtester.fill_simulator import FillSimulator
from backtester.reporter import Reporter

__all__ = [
    "DataLoader",
    "BacktestEngine",
    "FillSimulator",
    "Reporter",
]
