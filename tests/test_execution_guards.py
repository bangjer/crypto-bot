"""Tests that the Stage 4/5 stubs refuse to run, and live mode stays opt-in."""

import pytest

from config.settings import AppConfig
from execution.live import LiveExecutor
from execution.paper import PaperExecutor


def test_paper_executor_is_not_implemented() -> None:
    with pytest.raises(NotImplementedError):
        PaperExecutor(AppConfig())


def test_live_executor_blocked_when_disabled() -> None:
    """The default config must never allow live trading to construct."""
    config = AppConfig()
    assert config.live_trading_enabled is False
    with pytest.raises(RuntimeError, match="LIVE_TRADING_ENABLED"):
        LiveExecutor(config)


def test_live_executor_unimplemented_even_when_enabled() -> None:
    """Even with the flag on, Stage 5 code doesn't exist yet."""
    config = AppConfig(live_trading_enabled=True)
    with pytest.raises(NotImplementedError):
        LiveExecutor(config)


def test_live_flag_requires_exact_true(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only the exact string 'true' enables live mode — not '1', 'yes', etc."""
    from config.settings import load_config

    for value in ("1", "yes", "on", "TRUE ", "enabled"):
        monkeypatch.setenv("LIVE_TRADING_ENABLED", value)
        loaded = load_config()
        if value.strip().lower() == "true":
            assert loaded.live_trading_enabled
        else:
            assert not loaded.live_trading_enabled
