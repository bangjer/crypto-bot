"""Shared test fixtures and helpers."""

import pandas as pd
import pytest


def make_bars(prices: list[float], start_ms: int = 0, bar_ms: int = 60_000) -> pd.DataFrame:
    """Build a synthetic kline DataFrame from a list of prices.

    Each bar opens and closes at the same price (flat within the bar), which
    makes fee/slippage arithmetic exact in tests.

    Args:
        prices: One price per bar.
        start_ms: open_time of the first bar in milliseconds.
        bar_ms: Bar duration in milliseconds.

    Returns:
        DataFrame with the same columns the datafeed produces.
    """
    return pd.DataFrame(
        {
            "open_time": [start_ms + i * bar_ms for i in range(len(prices))],
            "open": prices,
            "high": prices,
            "low": prices,
            "close": prices,
            "volume": [1.0] * len(prices),
        }
    )


@pytest.fixture
def flat_bars() -> pd.DataFrame:
    """500 bars at a constant price of 100.0 — isolates fee/slippage effects."""
    return make_bars([100.0] * 500)
