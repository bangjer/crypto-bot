"""Performance statistics for backtest results.

Definitions used here:
    * Total return: net change in equity as a % of starting cash, after fees.
    * Win rate: fraction of completed round trips with positive net PnL.
    * Max drawdown: largest peak-to-trough equity decline, as a % of the peak.
    * Sharpe-like ratio: mean per-bar equity return / std of per-bar returns,
      annualized by sqrt(bars per year). "Like" because it ignores the
      risk-free rate and 1-minute crypto returns are far from normal — use it
      to compare strategies, not as an absolute quality score.
    * Fee drag: total fees as a % of gross PnL (PnL before fees). When gross
      PnL is ~0 this ratio explodes, so fees are also reported as a % of
      starting capital, which is always well-defined.
"""

import math

import pandas as pd

from core.models import Trade

# 1-minute bars in a 365-day year; crypto trades around the clock.
BARS_PER_YEAR_1M = 365 * 24 * 60


def max_drawdown(equity: pd.Series) -> float:
    """Largest peak-to-trough decline as a fraction of the peak.

    Args:
        equity: Equity curve ordered by time.

    Returns:
        Max drawdown as a positive fraction (0.10 == 10%), 0.0 if no decline.
    """
    if len(equity) < 2:
        return 0.0
    running_max = equity.cummax()
    drawdowns = (equity - running_max) / running_max
    return float(-drawdowns.min())


def sharpe_like(equity: pd.Series, bars_per_year: int = BARS_PER_YEAR_1M) -> float:
    """Annualized mean/std of per-bar returns (risk-free rate ignored).

    Args:
        equity: Equity curve ordered by time.
        bars_per_year: Annualization factor; defaults to 1-minute bars.

    Returns:
        The Sharpe-like ratio, or 0.0 when returns have no variance.
    """
    returns = equity.pct_change().dropna()
    if len(returns) < 2:
        return 0.0
    std = float(returns.std())
    if std == 0.0:
        return 0.0
    return float(returns.mean()) / std * math.sqrt(bars_per_year)


def compute_metrics(
    equity: pd.Series,
    trades: list[Trade],
    fees_total: float,
    initial_cash: float,
    bars_per_year: int = BARS_PER_YEAR_1M,
) -> dict[str, float]:
    """Assemble the summary statistics for a backtest run.

    Args:
        equity: Per-bar equity curve.
        trades: Completed round trips.
        fees_total: Total fees paid in quote currency.
        initial_cash: Starting quote balance.
        bars_per_year: Annualization factor for the Sharpe-like ratio.

    Returns:
        Dict of metric name to value. fee_drag_pct_of_gross is NaN when gross
        PnL is too close to zero to divide by.
    """
    net_pnl = float(equity.iloc[-1]) - initial_cash
    gross_pnl = net_pnl + fees_total
    wins = sum(1 for trade in trades if trade.pnl > 0)
    return {
        "total_return_pct": net_pnl / initial_cash * 100,
        "net_pnl": net_pnl,
        "gross_pnl": gross_pnl,
        "num_trades": float(len(trades)),
        "win_rate_pct": wins / len(trades) * 100 if trades else float("nan"),
        "max_drawdown_pct": max_drawdown(equity) * 100,
        "sharpe_like": sharpe_like(equity, bars_per_year),
        "fees_total": fees_total,
        "fee_drag_pct_of_gross": (
            fees_total / abs(gross_pnl) * 100 if abs(gross_pnl) > 1e-9 else float("nan")
        ),
        "fees_pct_of_capital": fees_total / initial_cash * 100,
    }
