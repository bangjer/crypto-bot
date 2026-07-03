"""Live trading executor — Stage 5 stub with the opt-in guard already wired.

Even once implemented, live trading must never start by accident:
    * LIVE_TRADING_ENABLED must be exactly "true" in the environment/.env —
      a config flag, not a CLI argument that is easy to pass by mistake.
    * API keys load from the environment and must be created WITHOUT
      withdrawal permission (configured in the Binance UI).
    * Every order still passes through the shared RiskManager, whose kill
      switch (daily loss limit, error-rate threshold) halts all trading.
"""

from config.settings import AppConfig


class LiveExecutor:
    """Places real orders on Binance (not yet built; guard is active now)."""

    def __init__(self, config: AppConfig) -> None:
        """Refuse to construct unless live trading is explicitly enabled.

        Args:
            config: Application configuration.

        Raises:
            RuntimeError: If LIVE_TRADING_ENABLED is not "true". This guard
                stays even after Stage 5 is implemented.
            NotImplementedError: Always for now, until Stage 5.
        """
        if not config.live_trading_enabled:
            raise RuntimeError(
                "Live trading is disabled. It requires LIVE_TRADING_ENABLED=true "
                "in your .env — an explicit, deliberate opt-in. Do not enable it "
                "until Stage 4 paper trading has run well for a meaningful stretch."
            )
        raise NotImplementedError(
            "Stage 5 (live trading) is not implemented yet. "
            "Complete Stages 1-4 first — never skip ahead to live trading."
        )
