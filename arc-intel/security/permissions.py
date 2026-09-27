"""Phase 4 — non-custodial execution permissions (reference policy engine).

Design lessons applied (from real incidents):
  - Banana Gun ($3M): a message/oracle path triggered actions with no re-confirmation
    window -> require an explicit, human-reviewable CANCEL WINDOW before any fund movement.
  - Unibot ($600K): an unrevoked approval was abused -> approvals EXPIRE automatically and
    must be revocable; 2FA is required above a spend threshold.

This module is pure and deterministic (permission *policy*), independent from any chain.
It never signs or moves funds; it gates intent -> approval -> (user-signed) execution.
The LLM never holds keys.
"""
from __future__ import annotations

from dataclasses import dataclass, field

PENDING = "pending"
CANCELLED = "cancelled"
EXPIRED = "expired"
APPROVED = "approved"
EXECUTED = "executed"

DEFAULT_CANCEL_SECONDS = 300
DEFAULT_TTL_SECONDS = 3600
DEFAULT_TWOFA_THRESHOLD = 50.0


@dataclass
class Approval:
    id: str
    user: str
    intent: dict
    amount: float
    created_at: int
    cancel_until: int
    expires_at: int
    requires_2fa: bool = False
    status: str = PENDING
    history: list = field(default_factory=list)


def create_approval(approval_id: str, user: str, intent: dict, amount: float, now: int,
                    cancel_seconds: int = DEFAULT_CANCEL_SECONDS,
                    ttl_seconds: int = DEFAULT_TTL_SECONDS,
                    twofa_threshold: float = DEFAULT_TWOFA_THRESHOLD) -> Approval:
    return Approval(
        id=approval_id, user=user, intent=dict(intent), amount=float(amount), created_at=now,
        cancel_until=now + int(cancel_seconds), expires_at=now + int(ttl_seconds),
        requires_2fa=float(amount) >= float(twofa_threshold), status=PENDING,
        history=[("created", now)],
    )


def can_cancel(a: Approval, now: int) -> bool:
    return a.status == PENDING and now <= a.cancel_until


def cancel(a: Approval, now: int) -> bool:
    if not can_cancel(a, now):
        return False
    a.status = CANCELLED
    a.history.append(("cancelled", now))
    return True


def is_expired(a: Approval, now: int) -> bool:
    return now > a.expires_at


def confirm(a: Approval, now: int, twofa_ok: bool = False) -> tuple[bool, str]:
    """Confirm an approval after its cancel window; requires 2FA above threshold."""
    if a.status != PENDING:
        return False, f"not_pending:{a.status}"
    if is_expired(a, now):
        a.status = EXPIRED
        a.history.append(("expired", now))
        return False, "expired"
    if now <= a.cancel_until:
        return False, "cancel_window_open"
    if a.requires_2fa and not twofa_ok:
        return False, "2fa_required"
    a.status = APPROVED
    a.history.append(("approved", now))
    return True, "approved"


def can_execute(a: Approval, now: int) -> bool:
    return a.status == APPROVED and not is_expired(a, now)


def mark_executed(a: Approval, now: int) -> bool:
    if not can_execute(a, now):
        return False
    a.status = EXECUTED
    a.history.append(("executed", now))
    return True
