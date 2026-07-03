"""Tests for the SQLite kline cache."""

from pathlib import Path

from datafeed.store import KlineStore


def _rows(start: int, count: int, bar_ms: int = 60_000) -> list[dict[str, float | int]]:
    return [
        {
            "open_time": start + i * bar_ms,
            "open": 100.0 + i,
            "high": 101.0 + i,
            "low": 99.0 + i,
            "close": 100.5 + i,
            "volume": 5.0,
        }
        for i in range(count)
    ]


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    with KlineStore(tmp_path / "test.db") as store:
        inserted = store.save("BTCUSDT", "1m", _rows(0, 10))
        assert inserted == 10
        frame = store.load("BTCUSDT", "1m")
        assert len(frame) == 10
        assert list(frame.columns) == ["open_time", "open", "high", "low", "close", "volume"]
        assert frame["open"].iloc[3] == 103.0


def test_duplicate_rows_are_ignored(tmp_path: Path) -> None:
    with KlineStore(tmp_path / "test.db") as store:
        store.save("BTCUSDT", "1m", _rows(0, 10))
        inserted_again = store.save("BTCUSDT", "1m", _rows(0, 10))
        assert inserted_again == 0
        assert len(store.load("BTCUSDT", "1m")) == 10


def test_load_respects_range_bounds(tmp_path: Path) -> None:
    with KlineStore(tmp_path / "test.db") as store:
        store.save("BTCUSDT", "1m", _rows(0, 10))
        frame = store.load("BTCUSDT", "1m", start_ms=120_000, end_ms=300_000)
        # start inclusive, end exclusive: bars at 120k, 180k, 240k
        assert list(frame["open_time"]) == [120_000, 180_000, 240_000]


def test_cached_range(tmp_path: Path) -> None:
    with KlineStore(tmp_path / "test.db") as store:
        assert store.cached_range("BTCUSDT", "1m") is None
        store.save("BTCUSDT", "1m", _rows(60_000, 5))
        assert store.cached_range("BTCUSDT", "1m") == (60_000, 300_000)


def test_symbols_are_isolated(tmp_path: Path) -> None:
    with KlineStore(tmp_path / "test.db") as store:
        store.save("BTCUSDT", "1m", _rows(0, 5))
        assert len(store.load("ETHUSDT", "1m")) == 0
