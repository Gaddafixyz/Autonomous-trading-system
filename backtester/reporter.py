"""
Generate human-readable reports from backtest results.
"""

import json
from typing import List
from core.types import BacktestMetrics, Trade


class Reporter:
    """Format and save backtest results."""

    @staticmethod
    def print_summary(metrics: BacktestMetrics):
        """Print backtest results to console."""
        print("\n" + "="*50)
        print("BACKTEST RESULTS")
        print("="*50)
        print(f"Initial equity:  {metrics.initial_equity:.2f} USDT")
        print(f"Final equity:    {metrics.final_equity:.2f} USDT")
        print(f"Total return:    {metrics.total_return:.2%}")
        print(f"Sharpe ratio:    {metrics.sharpe_ratio:.2f}")
        print(f"Max drawdown:    {metrics.max_drawdown:.2%}")
        print(f"Total trades:    {metrics.total_trades}")
        print(f"Win rate:        {metrics.win_rate:.2%}")
        print(f"Profit factor:   {metrics.profit_factor:.2f}")
        print(f"Avg win:         {metrics.avg_win:.2f} USDT")
        print(f"Avg loss:        {metrics.avg_loss:.2f} USDT")
        print("="*50 + "\n")

    @staticmethod
    def save_json(metrics: BacktestMetrics, trades: List[Trade], filepath: str):
        """Export results to JSON."""
        data = {
            "metrics": {
                "total_return": metrics.total_return,
                "sharpe_ratio": metrics.sharpe_ratio,
                "max_drawdown": metrics.max_drawdown,
                "win_rate": metrics.win_rate,
                "profit_factor": metrics.profit_factor,
                "total_trades": metrics.total_trades,
                "final_equity": metrics.final_equity,
            },
            "trades": [
                {
                    "timestamp": t.timestamp,
                    "symbol": t.symbol,
                    "side": t.side.value,
                    "entry": t.entry_price,
                    "exit": t.exit_price,
                    "pnl": t.realized_pnl,
                }
                for t in trades
            ]
        }
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
