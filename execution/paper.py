"""Paper trading executor — Stage 4 stub.

When implemented, this will run the SAME strategy and risk-manager code path
as live mode, but simulate fills against Binance's real-time websocket feed
instead of placing orders. Its purpose is to confirm backtested performance
holds up under live market conditions before any capital is at risk.
"""

from config.settings import AppConfig


class PaperExecutor:
    """Simulates order execution against live market data (not yet built)."""

    def __init__(self, config: AppConfig) -> None:
        """Refuse to construct until Stage 4 is implemented.

        Args:
            config: Application configuration.

        Raises:
            NotImplementedError: Always, until Stage 4.
        """
        raise NotImplementedError(
            "Stage 4 (paper trading) is not implemented yet. "
            "Finish and validate the Stage 1 backtester and Stage 2-3 "
            "strategy/risk modules first — do not skip ahead."
        )
