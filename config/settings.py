"""Central configuration for the crypto bot.

Fee assumptions
---------------
Defaults follow Binance's spot standard (VIP 0) fee schedule: 0.10% maker /
0.10% taker, expressed as fractions (0.001). The 25% BNB fee discount is NOT
assumed. Check https://www.binance.com/en/fee/schedule if your account tier or
discounts differ, and override via environment variables (see .env.example).

Slippage assumptions
--------------------
Slippage is modeled as a fixed number of basis points applied against the
trader on every fill (buys fill higher, sells fill lower). The 1 bp default is
a placeholder until paper trading provides real fill data.

Secrets
-------
API keys load from the environment (.env file) only. Stage 1 uses public
endpoints and needs no keys. Keys must never be hardcoded anywhere in this
repo, and the Binance keys themselves must be created without withdrawal
permission.
"""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv


@dataclass(frozen=True)
class FeeConfig:
    """Binance trading fees as fractions (0.001 == 0.10%)."""

    maker_fee: float = 0.001
    taker_fee: float = 0.001


@dataclass(frozen=True)
class BacktestConfig:
    """Backtest simulation parameters.

    Attributes:
        slippage_bps: Slippage per fill in basis points, applied against you.
        initial_cash: Starting quote-currency (USDT) balance.
        position_size_quote: Quote value of each position the bot opens.
        lookback_bars: Number of recent bars handed to the strategy each step.
    """

    slippage_bps: float = 1.0
    initial_cash: float = 10_000.0
    position_size_quote: float = 1_000.0
    lookback_bars: int = 100


@dataclass(frozen=True)
class AppConfig:
    """Top-level application configuration assembled from the environment."""

    fees: FeeConfig = field(default_factory=FeeConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    live_trading_enabled: bool = False
    binance_api_key: str = ""
    binance_api_secret: str = ""


def load_config() -> AppConfig:
    """Load configuration from environment variables (and a .env file if present).

    Returns:
        AppConfig with environment overrides applied on top of the documented
        defaults. ``live_trading_enabled`` is True only when the environment
        variable LIVE_TRADING_ENABLED is exactly the string "true"
        (case-insensitive) — it can never be enabled by accident.
    """
    load_dotenv()
    fees = FeeConfig(
        maker_fee=float(os.getenv("MAKER_FEE", "0.001")),
        taker_fee=float(os.getenv("TAKER_FEE", "0.001")),
    )
    backtest = BacktestConfig(
        slippage_bps=float(os.getenv("SLIPPAGE_BPS", "1.0")),
    )
    return AppConfig(
        fees=fees,
        backtest=backtest,
        live_trading_enabled=os.getenv("LIVE_TRADING_ENABLED", "false").strip().lower() == "true",
        binance_api_key=os.getenv("BINANCE_API_KEY", ""),
        binance_api_secret=os.getenv("BINANCE_API_SECRET", ""),
    )
