"""High-level data access: serve klines from cache, fetching only what's missing.

The gap-filling here is deliberately simple: it extends the cached range at the
head and tail, but does not detect holes in the middle of an already-cached
range. Good enough for Stage 1, where data is fetched in contiguous chunks.
"""

import logging
from pathlib import Path

import pandas as pd

from datafeed.binance_client import INTERVAL_MS, fetch_klines
from datafeed.store import DEFAULT_DB_PATH, KlineStore

logger = logging.getLogger(__name__)


def get_klines(
    symbol: str,
    interval: str,
    start_ms: int,
    end_ms: int,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> pd.DataFrame:
    """Return klines for a range, using the local cache and fetching gaps.

    Args:
        symbol: Trading pair, e.g. "BTCUSDT".
        interval: Kline interval, e.g. "1m".
        start_ms: Range start, inclusive, in milliseconds since epoch.
        end_ms: Range end, exclusive, in milliseconds since epoch.
        db_path: SQLite cache location (overridable for tests).

    Returns:
        DataFrame with columns open_time, open, high, low, close, volume,
        ordered by open_time ascending.
    """
    bar_ms = INTERVAL_MS[interval]
    with KlineStore(db_path) as store:
        cached = store.cached_range(symbol, interval)
        if cached is None:
            logger.info("Cache empty for %s %s — fetching full range", symbol, interval)
            store.save(symbol, interval, fetch_klines(symbol, interval, start_ms, end_ms))
        else:
            cached_start, cached_end = cached
            if start_ms < cached_start:
                logger.info("Fetching head gap %d -> %d", start_ms, cached_start)
                store.save(symbol, interval, fetch_klines(symbol, interval, start_ms, cached_start))
            if end_ms > cached_end + bar_ms:
                logger.info("Fetching tail gap %d -> %d", cached_end + bar_ms, end_ms)
                store.save(
                    symbol, interval, fetch_klines(symbol, interval, cached_end + bar_ms, end_ms)
                )
        return store.load(symbol, interval, start_ms, end_ms)
