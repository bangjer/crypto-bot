"""Local SQLite cache for kline data so repeated backtests don't re-fetch."""

import logging
import sqlite3
from pathlib import Path
from types import TracebackType

import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "klines.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS klines (
    symbol    TEXT    NOT NULL,
    interval  TEXT    NOT NULL,
    open_time INTEGER NOT NULL,
    open      REAL    NOT NULL,
    high      REAL    NOT NULL,
    low       REAL    NOT NULL,
    close     REAL    NOT NULL,
    volume    REAL    NOT NULL,
    PRIMARY KEY (symbol, interval, open_time)
)
"""


class KlineStore:
    """SQLite-backed cache of kline bars, keyed by (symbol, interval, open_time)."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        """Open (creating if necessary) the cache database.

        Args:
            db_path: Path to the SQLite file. Parent directories are created.
        """
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def save(self, symbol: str, interval: str, rows: list[dict[str, float | int]]) -> int:
        """Insert kline rows, silently skipping ones already cached.

        Args:
            symbol: Trading pair.
            interval: Kline interval, e.g. "1m".
            rows: Normalized kline dicts from datafeed.binance_client.

        Returns:
            Number of newly inserted rows.
        """
        cursor = self._conn.executemany(
            "INSERT OR IGNORE INTO klines VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    symbol,
                    interval,
                    row["open_time"],
                    row["open"],
                    row["high"],
                    row["low"],
                    row["close"],
                    row["volume"],
                )
                for row in rows
            ],
        )
        self._conn.commit()
        logger.info("Cached %d new klines for %s %s", cursor.rowcount, symbol, interval)
        return cursor.rowcount

    def load(
        self,
        symbol: str,
        interval: str,
        start_ms: int | None = None,
        end_ms: int | None = None,
    ) -> pd.DataFrame:
        """Load cached klines as a DataFrame ordered by open_time.

        Args:
            symbol: Trading pair.
            interval: Kline interval.
            start_ms: Optional range start, inclusive (milliseconds).
            end_ms: Optional range end, exclusive (milliseconds).

        Returns:
            DataFrame with columns open_time, open, high, low, close, volume.
        """
        query = (
            "SELECT open_time, open, high, low, close, volume FROM klines "
            "WHERE symbol = ? AND interval = ?"
        )
        params: list[float | int | str] = [symbol, interval]
        if start_ms is not None:
            query += " AND open_time >= ?"
            params.append(start_ms)
        if end_ms is not None:
            query += " AND open_time < ?"
            params.append(end_ms)
        query += " ORDER BY open_time"
        return pd.read_sql_query(query, self._conn, params=params)

    def cached_range(self, symbol: str, interval: str) -> tuple[int, int] | None:
        """Return the (min, max) cached open_time for a symbol, or None if empty.

        Args:
            symbol: Trading pair.
            interval: Kline interval.

        Returns:
            Tuple of (earliest, latest) open_time in milliseconds, or None.
        """
        row = self._conn.execute(
            "SELECT MIN(open_time), MAX(open_time) FROM klines WHERE symbol = ? AND interval = ?",
            (symbol, interval),
        ).fetchone()
        if row is None or row[0] is None:
            return None
        return int(row[0]), int(row[1])

    def close(self) -> None:
        """Close the underlying database connection."""
        self._conn.close()

    def __enter__(self) -> "KlineStore":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
