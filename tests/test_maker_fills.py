"""Maker/limit fill-model tests (Stage 3).

The maker_optimistic model rests a limit order at the signal bar's close and
fills it when the next bar touches that price — maker fee, no slippage. These
tests pin down the touch rules, the exact-limit fill price, the fee analogue
of the Stage 1 proof, and that taker mode is untouched.
"""

import pandas as pd
import pytest

from backtest.engine import BacktestEngine
from config.settings import BacktestConfig, FeeConfig, FillMode
from core.models import Signal
from risk.risk_manager import RiskLimits, RiskManager
from strategies.base import Strategy
from tests.conftest import make_bars

MAKER_FEE = 0.001
TAKER_FEE = 0.002  # deliberately different so a misapplied rate fails loudly


class ScriptedStrategy(Strategy):
    """Plays back a fixed sequence of signals, then holds forever."""

    def __init__(self, signals: list[Signal]) -> None:
        self._signals = list(signals)

    def on_bar(self, bars: pd.DataFrame) -> Signal:
        return self._signals.pop(0) if self._signals else Signal.HOLD


def make_ohlc_bars(
    opens: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float],
    start_ms: int = 0,
    bar_ms: int = 60_000,
) -> pd.DataFrame:
    """Build a kline DataFrame with explicit per-bar OHLC values.

    Unlike conftest.make_bars (flat bars), this lets highs and lows differ
    from the close, which is what limit-touch tests need.

    Args:
        opens: Open price per bar.
        highs: High price per bar.
        lows: Low price per bar.
        closes: Close price per bar.
        start_ms: open_time of the first bar in milliseconds.
        bar_ms: Bar duration in milliseconds.

    Returns:
        DataFrame with the same columns the datafeed produces.
    """
    return pd.DataFrame(
        {
            "open_time": [start_ms + i * bar_ms for i in range(len(opens))],
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [1.0] * len(opens),
        }
    )


def maker_engine(strategy: Strategy, slippage_bps: float = 0.0) -> BacktestEngine:
    """Maker-mode engine with generous risk limits so fill arithmetic is unobstructed.

    Args:
        strategy: The scripted strategy under test.
        slippage_bps: Configured slippage — maker fills must ignore it.

    Returns:
        A BacktestEngine in MAKER_OPTIMISTIC fill mode.
    """
    return BacktestEngine(
        strategy,
        RiskManager(RiskLimits(max_position_quote=5_000.0, max_position_pct=0.9)),
        FeeConfig(maker_fee=MAKER_FEE, taker_fee=TAKER_FEE),
        BacktestConfig(
            slippage_bps=slippage_bps,
            initial_cash=10_000.0,
            position_size_quote=1_000.0,
            fill_mode=FillMode.MAKER_OPTIMISTIC,
        ),
    )


def test_limit_never_touched_never_fills() -> None:
    """A BUY limit at the signal close must not fill when no bar's low reaches it.

    The strategy keeps re-emitting BUY (cancel-and-replace at each new close),
    but every subsequent bar's low stays above the resting limit price.
    """
    bars = make_ohlc_bars(
        opens=[100.0, 101.0, 102.0, 103.0],
        highs=[100.0, 102.0, 103.0, 104.0],
        lows=[100.0, 100.5, 101.75, 102.75],  # always above the prior close
        closes=[100.0, 101.5, 102.5, 103.5],
    )
    result = maker_engine(ScriptedStrategy([Signal.BUY] * 4)).run(bars)
    assert len(result.fills) == 0
    assert result.fees_total == 0.0
    assert float(result.equity_curve.iloc[-1]) == pytest.approx(10_000.0)


def test_touched_buy_fills_at_limit_with_maker_fee_no_slippage() -> None:
    """A touched BUY limit fills at exactly the limit price with the maker fee.

    Slippage is configured nonzero to prove maker fills ignore it: a taker
    fill on bar 1 would land at 101 * (1 + slip), not exactly 100.0.
    """
    bars = make_ohlc_bars(
        opens=[100.0, 101.0, 100.5],
        highs=[100.0, 102.0, 101.0],
        lows=[100.0, 99.0, 100.0],  # bar 1 low 99 <= limit 100 -> fill
        closes=[100.0, 100.5, 100.5],
    )
    result = maker_engine(ScriptedStrategy([Signal.BUY]), slippage_bps=50.0).run(bars)
    assert len(result.fills) == 1
    fill = result.fills[0]
    assert fill.price == 100.0  # exactly the limit, no slippage
    assert fill.fee == fill.quantity * 100.0 * MAKER_FEE
    assert result.fees_total == fill.fee


def test_sell_limit_fills_only_when_high_touches() -> None:
    """A SELL limit fills only on a bar whose high >= the limit, at exactly the limit."""
    bars = make_ohlc_bars(
        opens=[100.0, 100.0, 104.0, 104.0, 104.0],
        highs=[100.0, 106.0, 104.5, 105.0, 104.5],
        lows=[100.0, 99.0, 103.0, 103.5, 103.5],
        closes=[100.0, 105.0, 104.0, 104.0, 104.0],
    )
    # BUY limit 100 fills on bar 1 (low 99). SELL limit 105 from bar 1 is NOT
    # touched on bar 2 (high 104.5) and is replaced at bar 2's close of 104,
    # which bar 3 touches (high 105).
    strategy = ScriptedStrategy([Signal.BUY, Signal.SELL, Signal.SELL])
    result = maker_engine(strategy).run(bars)
    assert len(result.fills) == 2
    sell = result.fills[1]
    assert sell.side.value == "sell"
    assert sell.price == 104.0  # exactly the replaced limit
    assert sell.timestamp == int(bars.iloc[3]["open_time"])  # bar 3, not bar 2
    assert sell.fee == sell.quantity * 104.0 * MAKER_FEE


def test_round_trip_costs_exactly_two_maker_fees() -> None:
    """In a flat market, a maker round trip must lose exactly its two maker fees.

    This is the maker analogue of the Stage 1 fee proof: zero price movement
    means zero gross PnL, so every cent lost is a maker fee.
    """
    bars = make_bars([100.0] * 4)  # flat bars touch a limit at 100 on both sides
    result = maker_engine(ScriptedStrategy([Signal.BUY, Signal.SELL])).run(bars)
    assert len(result.trades) == 1
    entry, exit_fill = result.fills
    assert entry.price == 100.0 and exit_fill.price == 100.0
    expected_fees = entry.quantity * 100.0 * MAKER_FEE * 2
    assert result.fees_total == pytest.approx(expected_fees)
    assert result.trades[0].pnl == pytest.approx(-expected_fees)
    final_equity = float(result.equity_curve.iloc[-1])
    assert final_equity == pytest.approx(10_000.0 - result.fees_total)
    assert result.metrics["gross_pnl"] == pytest.approx(0.0, abs=1e-9)


def test_taker_mode_default_and_behavior_unchanged() -> None:
    """Taker stays the default and still fills at open +/- slippage with the taker fee."""
    assert BacktestConfig().fill_mode is FillMode.TAKER
    engine = BacktestEngine(
        ScriptedStrategy([Signal.BUY, Signal.SELL]),
        RiskManager(RiskLimits(max_position_quote=5_000.0, max_position_pct=0.9)),
        FeeConfig(maker_fee=MAKER_FEE, taker_fee=TAKER_FEE),
        BacktestConfig(slippage_bps=10.0, initial_cash=10_000.0, position_size_quote=1_000.0),
    )
    result = engine.run(make_bars([100.0] * 4))
    assert len(result.fills) == 2
    buy, sell = result.fills
    slip = 10.0 / 10_000.0
    assert buy.price == pytest.approx(100.0 * (1 + slip))  # open + slippage
    assert sell.price == pytest.approx(100.0 * (1 - slip))  # open - slippage
    assert buy.fee == pytest.approx(buy.quantity * buy.price * TAKER_FEE)
    assert sell.fee == pytest.approx(sell.quantity * sell.price * TAKER_FEE)
