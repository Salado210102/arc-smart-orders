"""Phase 4 — persistent approval engine + [PAPER] execution. NO funds, NO signing.

Flow: propose (from a real alert) -> cancel window -> threshold confirmation (simulated 2FA via
the bot) -> auto-expiry. On approval we record a [PAPER] simulated outcome vs holding.
"""
from __future__ import annotations

import random

from indexer.paper import DEFAULT_DELAY_SECONDS, paper_message, paper_outcome

CANCEL_SECONDS = 300
TTL_SECONDS = 3600
TWOFA_THRESHOLD = 50.0


def propose(store, chat, token, kind, side, notional, alert_block, now,
            cancel_seconds: int = CANCEL_SECONDS, ttl_seconds: int = TTL_SECONDS,
            threshold: float = TWOFA_THRESHOLD) -> int:
    requires = float(notional) >= float(threshold)
    code = f"{random.randint(0, 9999):04d}" if requires else None
    return store.create_approval(chat, token, kind, side, float(notional), alert_block, now,
                                 now + cancel_seconds, now + ttl_seconds, requires, code)


def pending(store, chat, now: int) -> list:
    return store.list_open_approvals(chat, now)


def can_cancel(a: dict, now: int) -> bool:
    return a.get("status") == "pending"


def approve(store, chat, approval_id, now: int, code=None) -> tuple[bool, str]:
    a = store.get_approval(approval_id)
    if not a or str(a["chat_id"]) != str(chat):
        return False, "not found"
    if a["status"] != "pending":
        return False, f"already {a['status']}"
    if now > a["expires_ts"]:
        store.update_approval(approval_id, "expired", now, "expired")
        return False, "expired"
    if now <= a["cancel_until"]:
        return False, f"cancel window open (until ts {a['cancel_until']})"
    if a["requires_2fa"] and str(code) != str(a["code"]):
        return False, "2fa_required"
    store.update_approval(approval_id, "approved", now, "approved")
    return True, "approved"


def cancel(store, chat, approval_id, now: int) -> tuple[bool, str]:
    a = store.get_approval(approval_id)
    if not a or str(a["chat_id"]) != str(chat):
        return False, "not found"
    if a["status"] != "pending":
        return False, f"already {a['status']}"
    store.update_approval(approval_id, "cancelled", now, "cancelled")
    return True, "cancelled"


def paper_result(price_series_fn, token: str, alert_block: int,
                 delay_seconds: float = DEFAULT_DELAY_SECONDS) -> str:
    series = price_series_fn(token) if price_series_fn else []
    out = paper_outcome(series, alert_block, delay_seconds=delay_seconds)
    return paper_message(token, out)
