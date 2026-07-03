"""Shared data models for orders, fills, trades, and account state.

These models are the common language between the strategy, risk manager,
backtester, and (later) the paper/live executors, so that every mode runs the
exact same order path.
"""

from dataclasses import dataclass
from enum import Enum


class Side(Enum):
    """Order side."""

    BUY = "buy"
    SELL = "sell"


class Signal(Enum):
    """Strategy output for a single bar."""

    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass(frozen=True)
class OrderRequest:
    """An order the strategy wants to place, before risk review.

    Attributes:
        symbol: Trading pair, e.g. "BTCUSDT".
        side: Buy or sell.
        quantity: Base-asset quantity (BTC for BTCUSDT).
        price: Expected fill price used for risk sizing checks.
        timestamp: Bar open time in milliseconds since epoch.
    """

    symbol: str
    side: Side
    quantity: float
    price: float
    timestamp: int


@dataclass(frozen=True)
class Fill:
    """A simulated or real order fill.

    Attributes:
        symbol: Trading pair.
        side: Buy or sell.
        quantity: Base-asset quantity filled.
        price: Actual fill price including slippage.
        fee: Fee paid in quote currency.
        timestamp: Fill time in milliseconds since epoch.
    """

    symbol: str
    side: Side
    quantity: float
    price: float
    fee: float
    timestamp: int


@dataclass(frozen=True)
class Trade:
    """A completed round trip (entry fill + exit fill).

    Attributes:
        entry: The opening fill.
        exit: The closing fill.
        pnl: Net profit/loss in quote currency, after both fills' fees.
    """

    entry: Fill
    exit: Fill
    pnl: float


@dataclass(frozen=True)
class AccountState:
    """Snapshot of the account used for risk checks.

    Attributes:
        cash: Free quote-currency balance.
        position_qty: Currently held base-asset quantity.
        equity: cash + position marked to market.
    """

    cash: float
    position_qty: float
    equity: float
