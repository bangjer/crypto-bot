"""Moving-average band mean-reversion strategy.

Buys when price dips a configurable fraction below its simple moving average
and sells once price reverts back to (or above) the average. The strategy is
stateless with respect to position — the engine owns position state and
ignores redundant signals — so it simply emits its opinion every bar.
"""

import pandas as pd

from core.models import Signal
from strategies.base import Strategy


class MeanReversionStrategy(Strategy):
    """Long-only mean reversion around a simple moving average band.

    Attributes:
        window: SMA lookback length in bars.
        entry_band: Fractional deviation below the SMA that triggers a long
            entry (0.002 = 0.2%).
        exit_band: Fractional deviation at/above which to exit; 0.0 means
            exit as soon as price reverts to the SMA.
    """

    def __init__(self, window: int = 20, entry_band: float = 0.002, exit_band: float = 0.0) -> None:
        """Configure the band parameters.

        Args:
            window: SMA lookback in bars; must be at least 2.
            entry_band: Fractional dip below the SMA that triggers a BUY;
                must be positive.
            exit_band: Fractional deviation at/above which to emit SELL.

        Raises:
            ValueError: If window < 2 or entry_band <= 0.
        """
        if window < 2:
            raise ValueError(f"window must be >= 2, got {window}")
        if entry_band <= 0:
            raise ValueError(f"entry_band must be > 0, got {entry_band}")
        self.window = window
        self.entry_band = entry_band
        self.exit_band = exit_band

    def on_bar(self, bars: pd.DataFrame) -> Signal:
        """Compare the latest close against the SMA band.

        Args:
            bars: Recent bars, oldest first; the last row just closed.

        Returns:
            Signal.HOLD until `window` bars exist. Then BUY when the close
            sits at least `entry_band` below the SMA, SELL when it sits at or
            above `exit_band` relative to the SMA, otherwise HOLD.
        """
        if len(bars) < self.window:
            return Signal.HOLD
        closes = bars["close"].iloc[-self.window :]
        sma = float(closes.mean())
        close = float(closes.iloc[-1])
        deviation = (close - sma) / sma
        if deviation <= -self.entry_band:
            return Signal.BUY
        if deviation >= self.exit_band:
            return Signal.SELL
        return Signal.HOLD
