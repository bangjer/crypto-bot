"""Mean-reversion strategy tests: signal logic, validation, and an
end-to-end backtest over a synthetic oscillating series."""

import pytest

from backtest.engine import BacktestEngine
from config.settings import BacktestConfig, FeeConfig
from core.models import Signal
from risk.risk_manager import RiskLimits, RiskManager
from strategies.base import Strategy
from strategies.mean_reversion import MeanReversionStrategy
from tests.conftest import make_bars


def default_engine(strategy: Strategy, slippage_bps: float = 0.0) -> BacktestEngine:
    """Engine with generous risk limits so signal logic is unobstructed."""
    return BacktestEngine(
        strategy,
        RiskManager(RiskLimits(max_position_quote=5_000.0, max_position_pct=0.9)),
        FeeConfig(taker_fee=0.001),
        BacktestConfig(
            slippage_bps=slippage_bps, initial_cash=10_000.0, position_size_quote=1_000.0
        ),
    )


def test_holds_when_window_not_full() -> None:
    """Fewer bars than the SMA window must always yield HOLD."""
    strategy = MeanReversionStrategy(window=20)
    bars = make_bars([100.0] * 10)
    assert strategy.on_bar(bars) == Signal.HOLD


def test_buys_on_dip_below_entry_band() -> None:
    """A close more than entry_band below the SMA must yield BUY."""
    strategy = MeanReversionStrategy(window=20, entry_band=0.002)
    # 19 flat bars then a 1% dip: SMA = 99.95, deviation ~ -0.95% <= -0.2%.
    bars = make_bars([100.0] * 19 + [99.0])
    assert strategy.on_bar(bars) == Signal.BUY


def test_sells_when_price_reverts_to_sma() -> None:
    """A close at/above the SMA (deviation >= exit_band=0) must yield SELL."""
    strategy = MeanReversionStrategy(window=5, entry_band=0.002, exit_band=0.0)
    # A dip drags the SMA to 98, so the final close of 100 sits above it.
    bars = make_bars([100.0, 100.0, 95.0, 95.0, 100.0])
    assert strategy.on_bar(bars) == Signal.SELL


def test_holds_inside_the_band() -> None:
    """A dip smaller than entry_band (but below the SMA) must yield HOLD."""
    strategy = MeanReversionStrategy(window=5, entry_band=0.002, exit_band=0.0)
    # SMA = 99.99, deviation ~ -0.04%: below the SMA but inside the 0.2% band.
    bars = make_bars([100.0] * 4 + [99.95])
    assert strategy.on_bar(bars) == Signal.HOLD


def test_uses_only_last_window_closes() -> None:
    """Bars older than the window must not influence the SMA."""
    strategy = MeanReversionStrategy(window=5, entry_band=0.002)
    # Old crash bars would drag the SMA far down; the last 5 bars are flat,
    # so deviation is 0 and the strategy must SELL (revert), not BUY.
    bars = make_bars([50.0] * 10 + [100.0] * 5)
    assert strategy.on_bar(bars) == Signal.SELL


@pytest.mark.parametrize("window", [1, 0, -3])
def test_rejects_window_below_two(window: int) -> None:
    """window < 2 makes no sense for an average — must raise ValueError."""
    with pytest.raises(ValueError):
        MeanReversionStrategy(window=window)


@pytest.mark.parametrize("entry_band", [0.0, -0.002])
def test_rejects_non_positive_entry_band(entry_band: float) -> None:
    """entry_band <= 0 would buy at/above the SMA — must raise ValueError."""
    with pytest.raises(ValueError):
        MeanReversionStrategy(entry_band=entry_band)


def test_backtest_round_trip_on_oscillating_prices() -> None:
    """End to end: repeated dips below a flat base must produce profitable
    round trips (buy the dip, sell the reversion) with zero slippage."""
    strategy = MeanReversionStrategy(window=5, entry_band=0.002, exit_band=0.0)
    # Flat base at 100 with sharp 5% dips: the BUY signal fires on the 95
    # close and fills at the next bar's open (96); the SELL fires once price
    # reverts to 100 and fills at the following 100 open.
    prices = [100.0] * 5 + [95.0, 96.0, 100.0, 100.0, 100.0] * 3
    result = default_engine(strategy, slippage_bps=0.0).run(make_bars(prices))

    assert result.metrics["num_trades"] >= 1, "expected at least one completed round trip"
    assert result.metrics["gross_pnl"] > 0, "buying dips on this pattern must be profitable"
    buys = [f.price for f in result.fills if f.side.value == "buy"]
    sells = [f.price for f in result.fills if f.side.value == "sell"]
    assert buys and sells
    assert max(buys) < min(sells), "every buy must have filled below every sell"
