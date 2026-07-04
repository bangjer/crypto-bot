"""Bar-by-bar backtesting engine with realistic fill simulation.

Fill model (documented assumptions):
    * The strategy sees bars up to and including bar i, and its signal
      executes during bar i+1 — never at prices the strategy already saw.
      This prevents look-ahead bias.
    * In TAKER mode (the default, config.settings.FillMode): all orders are
      market orders filled at bar i+1's OPEN, so the TAKER fee applies to
      every fill (a scalper crossing the spread is a taker). Fees are
      configured in config.settings.FeeConfig; the Binance VIP 0 default is
      0.10%. Slippage is a fixed bps penalty against the trader: buys fill
      at open * (1 + slip), sells at open * (1 - slip).
    * In MAKER_OPTIMISTIC mode: each signal is a LIMIT order at the signal
      bar's CLOSE (L). A pending BUY fills during bar i+1 iff that bar's
      low <= L; a pending SELL fills iff the bar's high >= L. Fills happen
      at exactly L, pay the MAKER fee, and take no slippage.
      WARNING — optimistic by construction: this model has NO queue-position
      awareness. It assumes any price touch fills immediately, which real
      limit orders often don't (you rest behind other orders at that price),
      and touch-fills are adversely selected. Maker-mode results are a lower
      bound on cost / an upper bound on performance, not a proven achievable
      cost.
    * Deliberate maker-mode simplifications: order lifetime is one bar
      (cancel-and-replace, as the strategy re-emits its signal each bar),
      there are no partial fills, and fills happen at exactly the limit
      price even when the bar gaps through it. A stricter trade-through rule
      (low < L instead of <=) is a possible future refinement, not
      implemented.
    * Positions are long/flat only in Stage 1. BUY opens a fixed
      quote-value position when flat; SELL closes the whole position.
    * Every order is reviewed by the RiskManager before it can fill —
      the same gate paper and live modes will use.
"""

import logging
from dataclasses import dataclass, field

import pandas as pd

from config.settings import BacktestConfig, FeeConfig, FillMode
from core.models import AccountState, Fill, OrderRequest, Side, Signal, Trade
from backtest.metrics import compute_metrics
from risk.risk_manager import RiskManager
from strategies.base import Strategy

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """Everything a backtest run produces.

    Attributes:
        metrics: Summary statistics (see backtest.metrics.compute_metrics).
        equity_curve: Per-bar account equity, indexed by bar open_time (ms).
        trades: Completed round trips.
        fills: Every individual fill.
        fees_total: Total fees paid in quote currency.
        open_position_qty: Base quantity still held at the end (not
            force-liquidated; it is marked to market in the equity curve).
    """

    metrics: dict[str, float]
    equity_curve: pd.Series
    trades: list[Trade] = field(default_factory=list)
    fills: list[Fill] = field(default_factory=list)
    fees_total: float = 0.0
    open_position_qty: float = 0.0


class BacktestEngine:
    """Replays historical bars through a strategy with simulated fills."""

    def __init__(
        self,
        strategy: Strategy,
        risk_manager: RiskManager,
        fees: FeeConfig,
        config: BacktestConfig,
        symbol: str = "BTCUSDT",
    ) -> None:
        """Wire up a backtest.

        Args:
            strategy: The strategy under test.
            risk_manager: The shared risk gate — every order goes through it.
            fees: Fee schedule; the taker rate is charged on every fill.
            config: Simulation parameters (slippage, cash, position size).
            symbol: Trading pair the bars belong to.
        """
        self._strategy = strategy
        self._risk = risk_manager
        self._fees = fees
        self._config = config
        self._symbol = symbol

    def run(self, bars: pd.DataFrame) -> BacktestResult:
        """Replay the bars and return performance results.

        Args:
            bars: Klines ordered by open_time with columns open_time, open,
                high, low, close, volume.

        Returns:
            BacktestResult with metrics, equity curve, trades, and fills.

        Raises:
            ValueError: If fewer than 2 bars are supplied.
        """
        if len(bars) < 2:
            raise ValueError("Backtest needs at least 2 bars")
        bars = bars.reset_index(drop=True)
        slip = self._config.slippage_bps / 10_000.0
        cash = self._config.initial_cash
        qty = 0.0
        entry_fill: Fill | None = None
        fees_total = 0.0
        equity_points: list[float] = []
        trades: list[Trade] = []
        fills: list[Fill] = []
        pending = Signal.HOLD
        pending_price: float | None = None
        maker = self._config.fill_mode is FillMode.MAKER_OPTIMISTIC

        for i in range(len(bars)):
            bar = bars.iloc[i]
            open_price = float(bar["open"])
            timestamp = int(bar["open_time"])

            # 1. Execute last bar's signal: at this bar's open (taker mode),
            #    or as a limit at the signal bar's close if this bar touches
            #    it (maker_optimistic mode).
            if pending is Signal.BUY and qty == 0.0:
                if maker:
                    touched = pending_price is not None and float(bar["low"]) <= pending_price
                    exec_price = pending_price if touched else None
                    fee_rate = self._fees.maker_fee
                else:
                    exec_price = open_price * (1 + slip)
                    fee_rate = self._fees.taker_fee
                if exec_price is not None:
                    order_qty = self._config.position_size_quote / exec_price
                    order = OrderRequest(self._symbol, Side.BUY, order_qty, exec_price, timestamp)
                    account = AccountState(cash, qty, cash + qty * open_price)
                    if self._risk.review_order(order, account).approved:
                        fee = order_qty * exec_price * fee_rate
                        cost = order_qty * exec_price + fee
                        if cost <= cash:
                            cash -= cost
                            qty = order_qty
                            fees_total += fee
                            entry_fill = Fill(
                                self._symbol, Side.BUY, order_qty, exec_price, fee, timestamp
                            )
                            fills.append(entry_fill)
                        else:
                            logger.warning(
                                "Skipped BUY at %d: cost %.2f > cash %.2f", timestamp, cost, cash
                            )
            elif pending is Signal.SELL and qty > 0.0 and entry_fill is not None:
                if maker:
                    touched = pending_price is not None and float(bar["high"]) >= pending_price
                    exec_price = pending_price if touched else None
                    fee_rate = self._fees.maker_fee
                else:
                    exec_price = open_price * (1 - slip)
                    fee_rate = self._fees.taker_fee
                if exec_price is not None:
                    order = OrderRequest(self._symbol, Side.SELL, qty, exec_price, timestamp)
                    account = AccountState(cash, qty, cash + qty * open_price)
                    if self._risk.review_order(order, account).approved:
                        proceeds = qty * exec_price
                        fee = proceeds * fee_rate
                        cash += proceeds - fee
                        fees_total += fee
                        exit_fill = Fill(self._symbol, Side.SELL, qty, exec_price, fee, timestamp)
                        fills.append(exit_fill)
                        pnl = (proceeds - fee) - (
                            entry_fill.quantity * entry_fill.price + entry_fill.fee
                        )
                        trades.append(Trade(entry_fill, exit_fill, pnl))
                        qty = 0.0
                        entry_fill = None

            # 2. Mark equity to market at this bar's close.
            equity_points.append(cash + qty * float(bar["close"]))

            # 3. Ask the strategy for the signal to act on next bar. The
            #    signal bar's close is the limit price in maker mode.
            window_start = max(0, i - self._config.lookback_bars + 1)
            pending = self._strategy.on_bar(bars.iloc[window_start : i + 1])
            pending_price = float(bar["close"])

        equity_curve = pd.Series(equity_points, index=bars["open_time"].to_numpy())
        metrics = compute_metrics(equity_curve, trades, fees_total, self._config.initial_cash)
        logger.info(
            "Backtest done: %d bars, %d trades, %d fills, fees %.2f",
            len(bars),
            len(trades),
            len(fills),
            fees_total,
        )
        return BacktestResult(metrics, equity_curve, trades, fills, fees_total, qty)
