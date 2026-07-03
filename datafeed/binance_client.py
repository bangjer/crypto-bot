"""Fetch historical kline (candlestick) data from Binance's public REST API.

Uses only the public /api/v3/klines endpoint — no API key required. Responses
are paginated at 1000 klines per request, so longer ranges are fetched in a
loop with a short pause to stay well inside Binance's rate limits.
"""

import logging
import time

import requests

logger = logging.getLogger(__name__)

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
MAX_KLINES_PER_REQUEST = 1000
REQUEST_PAUSE_SECONDS = 0.25
REQUEST_TIMEOUT_SECONDS = 10

# Milliseconds per bar for the intervals this bot supports.
INTERVAL_MS: dict[str, int] = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
}


def _normalize(raw: list) -> dict[str, float | int]:
    """Convert one raw Binance kline row into a flat dict.

    Binance returns each kline as a 12-element list; only OHLCV and the open
    time are kept.

    Args:
        raw: One kline row from the Binance API response.

    Returns:
        Dict with keys open_time, open, high, low, close, volume.
    """
    return {
        "open_time": int(raw[0]),
        "open": float(raw[1]),
        "high": float(raw[2]),
        "low": float(raw[3]),
        "close": float(raw[4]),
        "volume": float(raw[5]),
    }


def fetch_klines(
    symbol: str,
    interval: str,
    start_ms: int,
    end_ms: int,
    session: requests.Session | None = None,
) -> list[dict[str, float | int]]:
    """Fetch klines for a symbol between two timestamps, paginating as needed.

    Args:
        symbol: Trading pair, e.g. "BTCUSDT".
        interval: Kline interval, e.g. "1m". Must be a key of INTERVAL_MS.
        start_ms: Range start, inclusive, in milliseconds since epoch.
        end_ms: Range end, exclusive, in milliseconds since epoch.
        session: Optional requests.Session (injectable for tests).

    Returns:
        List of normalized kline dicts ordered by open_time ascending.

    Raises:
        ValueError: If the interval is not supported.
        requests.HTTPError: If Binance returns a non-2xx response.
    """
    if interval not in INTERVAL_MS:
        raise ValueError(f"Unsupported interval {interval!r}; use one of {sorted(INTERVAL_MS)}")
    session = session or requests.Session()
    rows: list[dict[str, float | int]] = []
    cursor = start_ms
    while cursor < end_ms:
        response = session.get(
            BINANCE_KLINES_URL,
            params={
                "symbol": symbol,
                "interval": interval,
                "startTime": cursor,
                "endTime": end_ms - 1,
                "limit": MAX_KLINES_PER_REQUEST,
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        batch = response.json()
        if not batch:
            break
        rows.extend(_normalize(raw) for raw in batch)
        cursor = int(batch[-1][0]) + INTERVAL_MS[interval]
        logger.info("Fetched %d klines for %s, cursor now %d", len(batch), symbol, cursor)
        if cursor < end_ms:
            time.sleep(REQUEST_PAUSE_SECONDS)
    return rows
