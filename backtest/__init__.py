"""Backtesting engine: bar-by-bar replay with fee and slippage simulation."""

from backtest.engine import BacktestEngine, BacktestResult
from backtest.metrics import compute_metrics

__all__ = ["BacktestEngine", "BacktestResult", "compute_metrics"]
