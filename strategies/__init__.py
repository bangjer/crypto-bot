"""Swappable strategy modules sharing the Strategy interface (Stage 2).

Stage 1 ships only the random null strategy used to sanity-check the fee
model. Real strategies get added here in Stage 2 and registered in STRATEGIES.
"""

from strategies.base import Strategy
from strategies.mean_reversion import MeanReversionStrategy
from strategies.random_strategy import RandomStrategy

# Registry used by main.py's --strategy flag.
STRATEGIES: dict[str, type[Strategy]] = {
    "random": RandomStrategy,
    "mean_reversion": MeanReversionStrategy,
}

__all__ = ["STRATEGIES", "MeanReversionStrategy", "RandomStrategy", "Strategy"]
