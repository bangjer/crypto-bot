"""Risk manager: the single gate every order must pass through.

Non-negotiable design rule from the build spec: backtest, paper, and live
order paths ALL call RiskManager.review_order() before any fill happens. No
mode may bypass it.

Stage 1 enforces position-size limits and logs every decision with a reason.
Stage 3 will add the remaining limits (per-trade stop-loss, daily max loss,
error-rate threshold) and wire them to the kill switch — the fields already
exist on RiskLimits so configs written now stay valid.
"""

import logging
from dataclasses import dataclass

from core.models import AccountState, OrderRequest, Side

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RiskLimits:
    """Hard limits enforced by the risk manager.

    Attributes:
        max_position_quote: Max position size in quote currency (absolute).
        max_position_pct: Max position size as a fraction of account equity.
        daily_max_loss_pct: Daily loss (fraction of equity) that triggers the
            kill switch. Defined now, ENFORCED in Stage 3.
        max_consecutive_errors: Failed-order streak that triggers the kill
            switch. Defined now, ENFORCED in Stage 3.
    """

    max_position_quote: float = 1_000.0
    max_position_pct: float = 0.25
    daily_max_loss_pct: float = 0.03
    max_consecutive_errors: int = 5


@dataclass(frozen=True)
class RiskDecision:
    """Outcome of a risk review.

    Attributes:
        approved: Whether the order may proceed.
        reason: Human-readable explanation, logged for every decision.
    """

    approved: bool
    reason: str


class RiskManager:
    """Reviews every order against configured limits and logs each decision."""

    def __init__(self, limits: RiskLimits | None = None) -> None:
        """Create a risk manager.

        Args:
            limits: Limits to enforce; defaults to RiskLimits defaults.
        """
        self.limits = limits if limits is not None else RiskLimits()

    def review_order(self, order: OrderRequest, account: AccountState) -> RiskDecision:
        """Approve or reject an order against position-size limits.

        Args:
            order: The proposed order.
            account: Current account snapshot for sizing checks.

        Returns:
            RiskDecision with approval flag and reason. Every decision,
            including approvals, is logged.
        """
        decision = self._evaluate(order, account)
        log = logger.info if decision.approved else logger.warning
        log(
            "Risk %s: %s %s qty=%.8f @ %.2f — %s",
            "APPROVED" if decision.approved else "REJECTED",
            order.side.value.upper(),
            order.symbol,
            order.quantity,
            order.price,
            decision.reason,
        )
        return decision

    def _evaluate(self, order: OrderRequest, account: AccountState) -> RiskDecision:
        """Run the actual limit checks (no logging).

        Args:
            order: The proposed order.
            account: Current account snapshot.

        Returns:
            The resulting RiskDecision.
        """
        if order.quantity <= 0:
            return RiskDecision(False, "quantity must be positive")
        if order.side is Side.BUY:
            resulting_notional = (account.position_qty + order.quantity) * order.price
            if resulting_notional > self.limits.max_position_quote:
                return RiskDecision(
                    False,
                    f"position {resulting_notional:.2f} would exceed absolute cap "
                    f"{self.limits.max_position_quote:.2f}",
                )
            max_by_pct = self.limits.max_position_pct * account.equity
            if resulting_notional > max_by_pct:
                return RiskDecision(
                    False,
                    f"position {resulting_notional:.2f} would exceed "
                    f"{self.limits.max_position_pct:.0%} of equity ({max_by_pct:.2f})",
                )
        elif order.quantity > account.position_qty + 1e-12:
            return RiskDecision(
                False,
                f"cannot sell {order.quantity:.8f}, only hold {account.position_qty:.8f}",
            )
        return RiskDecision(True, "within limits")
