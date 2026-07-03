"""Swappable strategy modules sharing the Strategy interface (Stage 2).

Stage 1 ships only the random null strategy used to sanity-check the fee
model. Real strategies get added here in Stage 2 and registered in STRATEGIES.
"""

from strategies.base import Strategy
from strategies.random_strategy import RandomStrategy

# Registry used by main.py's --strategy flag.
STRATEGIES: dict[str, type[Strategy]] = {
    "random": RandomStrategy,
}

__all__ = ["STRATEGIES", "RandomStrategy", "Strategy"]
