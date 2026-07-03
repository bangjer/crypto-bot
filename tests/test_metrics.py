"""Tests for backtest performance metrics."""

import math

import pandas as pd
import pytest

from backtest.metrics import compute_metrics, max_drawdown, sharpe_like
from core.models import Fill, Side, Trade


def _trade(pnl: float) -> Trade:
    """Build a Trade with the given pnl and dummy fills."""
    fill = Fill("BTCUSDT", Side.BUY, 1.0, 100.0, 0.1, 0)
    return Trade(fill, fill, pnl)


def test_max_drawdown_known_series() -> None:
    """Drawdown of [100, 110, 99, 120] is (110-99)/110 = 10%."""
    equity = pd.Series([100.0, 110.0, 99.0, 120.0])
    assert max_drawdown(equity) == pytest.approx(0.1)


def test_max_drawdown_monotonic_rise_is_zero() -> None:
    """A curve that only rises has no drawdown."""
    assert max_drawdown(pd.Series([100.0, 101.0, 102.0])) == 0.0


def test_sharpe_like_zero_variance() -> None:
    """Constant equity has no variance and must not divide by zero."""
    assert sharpe_like(pd.Series([100.0] * 10)) == 0.0


def test_compute_metrics_basics() -> None:
    """Win rate, return, and fee reporting on a simple constructed case."""
    equity = pd.Series([10_000.0, 10_050.0, 10_100.0])
    trades = [_trade(60.0), _trade(50.0), _trade(-10.0)]
    metrics = compute_metrics(equity, trades, fees_total=25.0, initial_cash=10_000.0)
    assert metrics["net_pnl"] == pytest.approx(100.0)
    assert metrics["gross_pnl"] == pytest.approx(125.0)
    assert metrics["total_return_pct"] == pytest.approx(1.0)
    assert metrics["win_rate_pct"] == pytest.approx(200 / 3)
    assert metrics["fee_drag_pct_of_gross"] == pytest.approx(20.0)
    assert metrics["fees_pct_of_capital"] == pytest.approx(0.25)


def test_fee_drag_nan_when_gross_is_zero() -> None:
    """Fee drag is undefined (NaN) when gross PnL is ~0, not a crash or inf."""
    equity = pd.Series([10_000.0, 9_975.0])
    metrics = compute_metrics(equity, [], fees_total=25.0, initial_cash=10_000.0)
    assert math.isnan(metrics["fee_drag_pct_of_gross"])
    assert math.isnan(metrics["win_rate_pct"])
