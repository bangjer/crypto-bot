"""Tests for the risk manager order gate."""

from core.models import AccountState, OrderRequest, Side
from risk.risk_manager import RiskLimits, RiskManager


def _account(cash: float = 10_000.0, qty: float = 0.0, equity: float = 10_000.0) -> AccountState:
    return AccountState(cash=cash, position_qty=qty, equity=equity)


def test_approves_order_within_limits() -> None:
    manager = RiskManager(RiskLimits(max_position_quote=1_000.0, max_position_pct=0.25))
    order = OrderRequest("BTCUSDT", Side.BUY, 0.005, 100_000.0, 0)  # 500 USDT
    decision = manager.review_order(order, _account())
    assert decision.approved


def test_rejects_order_over_absolute_cap() -> None:
    manager = RiskManager(RiskLimits(max_position_quote=1_000.0, max_position_pct=0.9))
    order = OrderRequest("BTCUSDT", Side.BUY, 0.02, 100_000.0, 0)  # 2000 USDT
    decision = manager.review_order(order, _account())
    assert not decision.approved
    assert "absolute cap" in decision.reason


def test_rejects_order_over_equity_percentage() -> None:
    manager = RiskManager(RiskLimits(max_position_quote=50_000.0, max_position_pct=0.10))
    order = OrderRequest("BTCUSDT", Side.BUY, 0.02, 100_000.0, 0)  # 2000 > 10% of 10k
    decision = manager.review_order(order, _account())
    assert not decision.approved
    assert "of equity" in decision.reason


def test_buy_cap_counts_existing_position() -> None:
    """A buy that is fine alone but breaches the cap combined must be rejected."""
    manager = RiskManager(RiskLimits(max_position_quote=1_000.0, max_position_pct=0.9))
    order = OrderRequest("BTCUSDT", Side.BUY, 0.006, 100_000.0, 0)  # 600 USDT
    holding = _account(qty=0.006, equity=10_000.0)  # already holding 600 USDT worth
    decision = manager.review_order(order, holding)
    assert not decision.approved


def test_rejects_selling_more_than_held() -> None:
    manager = RiskManager()
    order = OrderRequest("BTCUSDT", Side.SELL, 1.0, 100_000.0, 0)
    decision = manager.review_order(order, _account(qty=0.5))
    assert not decision.approved


def test_rejects_nonpositive_quantity() -> None:
    manager = RiskManager()
    order = OrderRequest("BTCUSDT", Side.BUY, 0.0, 100_000.0, 0)
    assert not manager.review_order(order, _account()).approved
