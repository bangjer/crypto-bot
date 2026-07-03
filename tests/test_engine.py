"""Backtest engine tests, including the Stage 1 acceptance check:
a null/random strategy must lose money to fees alone."""

import pandas as pd
import pytest

from backtest.engine import BacktestEngine
from config.settings import BacktestConfig, FeeConfig
from core.models import Signal
from risk.risk_manager import RiskLimits, RiskManager
from strategies.base import Strategy
from strategies.random_strategy import RandomStrategy
from tests.conftest import make_bars


class AlternatingStrategy(Strategy):
    """Buys and sells on alternating bars — maximum churn, zero edge."""

    def __init__(self) -> None:
        self._next_is_buy = True

    def on_bar(self, bars: pd.DataFrame) -> Signal:
        signal = Signal.BUY if self._next_is_buy else Signal.SELL
        self._next_is_buy = not self._next_is_buy
        return signal


def default_engine(strategy: Strategy, slippage_bps: float = 0.0) -> BacktestEngine:
    """Engine with generous risk limits so fee arithmetic is unobstructed."""
    return BacktestEngine(
        strategy,
        RiskManager(RiskLimits(max_position_quote=5_000.0, max_position_pct=0.9)),
        FeeConfig(taker_fee=0.001),
        BacktestConfig(
            slippage_bps=slippage_bps, initial_cash=10_000.0, position_size_quote=1_000.0
        ),
    )


def test_flat_market_losses_equal_fees_exactly(flat_bars: pd.DataFrame) -> None:
    """With flat prices and zero slippage, net loss must equal total fees.

    This is the core proof that the fee model works: no price movement means
    zero gross PnL, so every cent lost is a fee.
    """
    result = default_engine(AlternatingStrategy(), slippage_bps=0.0).run(flat_bars)
    final_equity = float(result.equity_curve.iloc[-1])
    assert result.fees_total > 0
    assert final_equity == pytest.approx(10_000.0 - result.fees_total)
    assert result.metrics["gross_pnl"] == pytest.approx(0.0, abs=1e-6)
    # Every completed round trip lost exactly its two fees.
    assert result.metrics["win_rate_pct"] == 0.0


def test_random_strategy_loses_to_fees(flat_bars: pd.DataFrame) -> None:
    """Acceptance check from the spec: the null strategy must lose money."""
    result = default_engine(RandomStrategy(seed=42), slippage_bps=1.0).run(flat_bars)
    assert result.metrics["num_trades"] > 0, "random strategy should have traded"
    assert result.metrics["net_pnl"] < 0, "a zero-edge strategy must lose to fees"
    # In a flat market the entire loss is fees + slippage; fees alone should
    # account for most of it.
    assert result.fees_total > 0


def test_no_lookahead_fills_use_next_bar_open() -> None:
    """A signal on bar i must fill at bar i+1's open, not bar i's close."""

    class BuyOnceStrategy(Strategy):
        def __init__(self) -> None:
            self._fired = False

        def on_bar(self, bars: pd.DataFrame) -> Signal:
            if not self._fired:
                self._fired = True
                return Signal.BUY
            return Signal.HOLD

    # Bar 0 price 100, bar 1 price 110: signal generated on bar 0 must fill
    # at 110 (bar 1's open), not 100.
    bars = make_bars([100.0, 110.0, 110.0])
    result = default_engine(BuyOnceStrategy(), slippage_bps=0.0).run(bars)
    assert len(result.fills) == 1
    assert result.fills[0].price == pytest.approx(110.0)


def test_risk_manager_blocks_oversized_orders(flat_bars: pd.DataFrame) -> None:
    """Orders above the risk limit must never fill — no mode bypasses risk."""
    engine = BacktestEngine(
        AlternatingStrategy(),
        RiskManager(RiskLimits(max_position_quote=500.0)),  # cap below order size
        FeeConfig(),
        BacktestConfig(slippage_bps=0.0, initial_cash=10_000.0, position_size_quote=1_000.0),
    )
    result = engine.run(flat_bars)
    assert len(result.fills) == 0
    assert result.fees_total == 0.0
    assert float(result.equity_curve.iloc[-1]) == pytest.approx(10_000.0)


def test_slippage_hurts_both_sides(flat_bars: pd.DataFrame) -> None:
    """Buys must fill above and sells below the bar open."""
    result = default_engine(AlternatingStrategy(), slippage_bps=10.0).run(flat_bars)
    buys = [f for f in result.fills if f.side.value == "buy"]
    sells = [f for f in result.fills if f.side.value == "sell"]
    assert all(f.price > 100.0 for f in buys)
    assert all(f.price < 100.0 for f in sells)


def test_rejects_too_few_bars() -> None:
    """The engine requires at least two bars."""
    with pytest.raises(ValueError):
        default_engine(AlternatingStrategy()).run(make_bars([100.0]))
