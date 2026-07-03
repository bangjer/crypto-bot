"""Tests for the Binance kline fetcher, with the HTTP layer faked out."""

import pytest

from datafeed.binance_client import INTERVAL_MS, MAX_KLINES_PER_REQUEST, fetch_klines


class FakeResponse:
    def __init__(self, payload: list) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> list:
        return self._payload


class FakeSession:
    """Serves synthetic klines the way Binance paginates them."""

    def __init__(self, total_bars: int, bar_ms: int = 60_000) -> None:
        self._total_bars = total_bars
        self._bar_ms = bar_ms
        self.request_count = 0

    def get(self, url: str, params: dict, timeout: int) -> FakeResponse:
        self.request_count += 1
        start = params["startTime"]
        first_index = start // self._bar_ms
        rows = []
        for i in range(first_index, min(first_index + params["limit"], self._total_bars)):
            open_time = i * self._bar_ms
            if open_time > params["endTime"]:
                break
            rows.append(
                [open_time, "100.0", "101.0", "99.0", "100.5", "5.0", 0, "0", 0, "0", "0", "0"]
            )
        return FakeResponse(rows)


def test_fetch_paginates_across_batches() -> None:
    """2500 bars require three 1000-bar pages."""
    total = 2500
    session = FakeSession(total)
    rows = fetch_klines("BTCUSDT", "1m", 0, total * INTERVAL_MS["1m"], session=session)
    assert len(rows) == total
    assert session.request_count == 3
    assert rows[0]["open_time"] == 0
    assert rows[-1]["open_time"] == (total - 1) * INTERVAL_MS["1m"]
    # Values arrive as strings from the API and must be normalized to floats.
    assert rows[0]["open"] == 100.0


def test_fetch_single_page() -> None:
    session = FakeSession(50)
    rows = fetch_klines("BTCUSDT", "1m", 0, 50 * INTERVAL_MS["1m"], session=session)
    assert len(rows) == 50
    assert session.request_count == 1


def test_fetch_rejects_unknown_interval() -> None:
    with pytest.raises(ValueError):
        fetch_klines("BTCUSDT", "7m", 0, 1_000_000, session=FakeSession(10))


def test_pagination_limit_constant_matches_binance() -> None:
    assert MAX_KLINES_PER_REQUEST == 1000
