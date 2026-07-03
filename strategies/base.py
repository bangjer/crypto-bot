"""Common strategy interface.

Every strategy — in backtest, paper, or live mode — implements this one
interface and is fed data the same way, so strategy code is never duplicated
per mode.
"""

from abc import ABC, abstractmethod

import pandas as pd

from core.models import Signal


class Strategy(ABC):
    """Base class for all trading strategies."""

    @abstractmethod
    def on_bar(self, bars: pd.DataFrame) -> Signal:
        """Produce a signal from recent market data.

        Args:
            bars: The most recent bars (oldest first) with columns open_time,
                open, high, low, close, volume. The last row is the bar that
                just closed. The window length is set by config
                (lookback_bars); early in a run it may be shorter.

        Returns:
            Signal.BUY, Signal.SELL, or Signal.HOLD. The engine acts on the
            signal at the NEXT bar's open — strategies never see the future.
        """
