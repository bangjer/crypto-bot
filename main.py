"""Entry point: mode selector for backtest | paper | live.

Only backtest mode works in Stage 1. Paper and live modes exist so the mode
plumbing is in place, but they exit with a clear message; live mode is
additionally guarded by the LIVE_TRADING_ENABLED config flag.
"""

import argparse
import dataclasses
import logging
import sys
from datetime import datetime, timedelta, timezone

from backtest.engine import BacktestEngine, BacktestResult
from config.settings import AppConfig, FillMode, load_config
from datafeed.service import get_klines
from execution.live import LiveExecutor
from execution.paper import PaperExecutor
from risk.risk_manager import RiskLimits, RiskManager
from strategies import STRATEGIES

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Define and parse the command-line interface.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(description="Binance scalping bot (Stage 1: backtest only)")
    parser.add_argument(
        "--mode",
        choices=["backtest", "paper", "live"],
        default="backtest",
        help="Operating mode (only backtest is implemented in Stage 1)",
    )
    parser.add_argument("--symbol", default="BTCUSDT", help="Trading pair")
    parser.add_argument("--interval", default="1m", help="Kline interval")
    parser.add_argument(
        "--strategy",
        default="random",
        choices=sorted(STRATEGIES),
        help="Strategy to run (Stage 1 ships only the random fee sanity check)",
    )
    parser.add_argument(
        "--ma-window",
        type=int,
        default=20,
        help="mean_reversion only: SMA lookback in bars",
    )
    parser.add_argument(
        "--entry-band-bps",
        type=float,
        default=20.0,
        help="mean_reversion only: entry dip below the SMA in basis points (20 = 0.2%%)",
    )
    parser.add_argument(
        "--exit-band-bps",
        type=float,
        default=0.0,
        help="mean_reversion only: exit deviation above the SMA in basis points",
    )
    parser.add_argument(
        "--fill-mode",
        choices=["taker", "maker_optimistic"],
        default=None,
        help="Override FILL_MODE: taker (market orders at open, slippage + taker fee) or "
        "maker_optimistic (limit at signal close, maker fee — optimistic touch-fill model)",
    )
    parser.add_argument("--start", help="Backtest start date, YYYY-MM-DD (UTC)")
    parser.add_argument("--end", help="Backtest end date, YYYY-MM-DD (UTC, exclusive)")
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Backtest the most recent N days when --start/--end are omitted",
    )
    return parser.parse_args()


def resolve_range(args: argparse.Namespace) -> tuple[int, int]:
    """Turn CLI date arguments into a millisecond timestamp range.

    Args:
        args: Parsed CLI arguments.

    Returns:
        (start_ms, end_ms) tuple, end exclusive.
    """
    if args.start:
        start = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end = (
            datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if args.end
            else datetime.now(timezone.utc)
        )
    else:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=args.days)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def strategy_kwargs(args: argparse.Namespace) -> dict[str, int | float]:
    """Map CLI flags to constructor kwargs for the selected strategy.

    Strategies not listed here take no CLI parameters and are constructed
    with their defaults.

    Args:
        args: Parsed CLI arguments.

    Returns:
        Keyword arguments for the strategy constructor (bps converted to
        fractions where applicable).
    """
    if args.strategy == "mean_reversion":
        return {
            "window": args.ma_window,
            "entry_band": args.entry_band_bps / 10_000,
            "exit_band": args.exit_band_bps / 10_000,
        }
    return {}


def print_report(
    result: BacktestResult, symbol: str, strategy_name: str, fill_mode: FillMode
) -> None:
    """Print a human-readable backtest report.

    Args:
        result: The finished backtest.
        symbol: Trading pair that was tested.
        strategy_name: Registry name of the strategy.
        fill_mode: Fill model the backtest ran with.
    """
    metrics = result.metrics
    print(f"\n=== Backtest report: {strategy_name} on {symbol} ===")
    print(f"Fill mode:            {fill_mode.value:>12}")
    print(f"Bars replayed:        {len(result.equity_curve):>12,}")
    print(f"Completed trades:     {metrics['num_trades']:>12,.0f}")
    print(f"Total return:         {metrics['total_return_pct']:>11.2f}%")
    print(f"Net PnL:              {metrics['net_pnl']:>12.2f}")
    print(f"Gross PnL (pre-fee):  {metrics['gross_pnl']:>12.2f}")
    print(f"Win rate:             {metrics['win_rate_pct']:>11.2f}%")
    print(f"Max drawdown:         {metrics['max_drawdown_pct']:>11.2f}%")
    print(f"Sharpe-like ratio:    {metrics['sharpe_like']:>12.2f}")
    print(f"Fees paid:            {metrics['fees_total']:>12.2f}")
    print(f"Fee drag (% of gross):{metrics['fee_drag_pct_of_gross']:>11.2f}%")
    print(f"Fees (% of capital):  {metrics['fees_pct_of_capital']:>11.2f}%")
    if result.open_position_qty > 0:
        print(
            f"NOTE: open position of {result.open_position_qty:.8f} base units "
            "remained at the end (marked to market in equity)."
        )
    if fill_mode is FillMode.MAKER_OPTIMISTIC:
        print(
            "WARNING: maker_optimistic assumes every price touch fills (no queue modeling) "
            "— results are an optimistic bound."
        )
    print()


def run_backtest(args: argparse.Namespace, config: AppConfig) -> None:
    """Fetch data (cache-first) and run the backtest.

    Args:
        args: Parsed CLI arguments.
        config: Loaded application configuration.
    """
    start_ms, end_ms = resolve_range(args)
    logger.info(
        "Loading %s %s klines for range %d-%d", args.symbol, args.interval, start_ms, end_ms
    )
    bars = get_klines(args.symbol, args.interval, start_ms, end_ms)
    if len(bars) < 2:
        sys.exit("Not enough data returned for the requested range.")
    strategy = STRATEGIES[args.strategy](**strategy_kwargs(args))
    backtest_config = config.backtest
    if args.fill_mode is not None:
        backtest_config = dataclasses.replace(backtest_config, fill_mode=FillMode(args.fill_mode))
    risk_manager = RiskManager(
        RiskLimits(
            max_position_quote=backtest_config.position_size_quote,
            max_position_pct=0.25,
        )
    )
    engine = BacktestEngine(strategy, risk_manager, config.fees, backtest_config, args.symbol)
    result = engine.run(bars)
    print_report(result, args.symbol, args.strategy, backtest_config.fill_mode)


def main() -> None:
    """Dispatch to the selected mode."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    args = parse_args()
    config = load_config()
    if args.mode == "backtest":
        run_backtest(args, config)
    elif args.mode == "paper":
        try:
            PaperExecutor(config)
        except NotImplementedError as exc:
            sys.exit(f"paper mode: {exc}")
    elif args.mode == "live":
        try:
            LiveExecutor(config)
        except (RuntimeError, NotImplementedError) as exc:
            sys.exit(f"live mode: {exc}")


if __name__ == "__main__":
    main()
