"""Null/random strategy — a sanity check, not a trading idea.

A strategy with zero predictive power must, on average, lose money at exactly
the rate of fees plus slippage. If a backtest of this strategy shows profits,
or losses smaller than the fees it paid, the fill simulation is broken.
"""

import random

import pandas as pd

from core.models import Signal
from strategies.base import Strategy


class RandomStrategy(Strategy):
    """Emits random buy/sell signals with no regard for market data."""

    def __init__(self, trade_probability: float = 0.3, seed: int = 42) -> None:
        """Initialize the random signal generator.

        Args:
            trade_probability: Chance per bar of emitting a non-HOLD signal,
                split evenly between BUY and SELL.
            seed: RNG seed so backtests are reproducible.
        """
        self._trade_probability = trade_probability
        self._rng = random.Random(seed)

    def on_bar(self, bars: pd.DataFrame) -> Signal:
        """Ignore the data entirely and roll the dice.

        Args:
            bars: Recent market data (unused).

        Returns:
            A random Signal.
        """
        roll = self._rng.random()
        if roll < self._trade_probability / 2:
            return Signal.BUY
        if roll < self._trade_probability:
            return Signal.SELL
        return Signal.HOLD
