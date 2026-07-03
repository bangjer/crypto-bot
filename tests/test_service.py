"""Tests for cache-first data access, with the network fetcher faked out."""

from pathlib import Path

import pytest

import datafeed.service as service
from datafeed.store import KlineStore

BAR_MS = 60_000


def _fake_fetch(symbol: str, interval: str, start_ms: int, end_ms: int) -> list[dict]:
    """Generate deterministic bars for the requested range, like the real API."""
    return [
        {
            "open_time": t,
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 1.0,
        }
        for t in range(start_ms, end_ms, BAR_MS)
    ]


@pytest.fixture
def fetch_spy(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, int]]:
    """Replace the network fetcher and record each requested range."""
    calls: list[tuple[int, int]] = []

    def spy(symbol: str, interval: str, start_ms: int, end_ms: int) -> list[dict]:
        calls.append((start_ms, end_ms))
        return _fake_fetch(symbol, interval, start_ms, end_ms)

    monkeypatch.setattr(service, "fetch_klines", spy)
    return calls


def test_empty_cache_fetches_full_range(tmp_path: Path, fetch_spy: list) -> None:
    db = tmp_path / "cache.db"
    frame = service.get_klines("BTCUSDT", "1m", 0, 10 * BAR_MS, db_path=db)
    assert len(frame) == 10
    assert fetch_spy == [(0, 10 * BAR_MS)]


def test_fully_cached_range_makes_no_network_calls(tmp_path: Path, fetch_spy: list) -> None:
    db = tmp_path / "cache.db"
    service.get_klines("BTCUSDT", "1m", 0, 10 * BAR_MS, db_path=db)
    fetch_spy.clear()
    frame = service.get_klines("BTCUSDT", "1m", 2 * BAR_MS, 8 * BAR_MS, db_path=db)
    assert len(frame) == 6
    assert fetch_spy == []


def test_only_missing_head_and_tail_are_fetched(tmp_path: Path, fetch_spy: list) -> None:
    db = tmp_path / "cache.db"
    # Pre-cache bars 5..9 (open_times 5*BAR_MS .. 9*BAR_MS).
    with KlineStore(db) as store:
        store.save("BTCUSDT", "1m", _fake_fetch("BTCUSDT", "1m", 5 * BAR_MS, 10 * BAR_MS))
    frame = service.get_klines("BTCUSDT", "1m", 0, 15 * BAR_MS, db_path=db)
    assert len(frame) == 15
    # Head gap [0, 5*BAR_MS) and tail gap [10*BAR_MS, 15*BAR_MS) only.
    assert fetch_spy == [(0, 5 * BAR_MS), (10 * BAR_MS, 15 * BAR_MS)]
