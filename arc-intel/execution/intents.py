"""Phase 5 — non-custodial trade intents (construction + validation). NO SIGNING.

The LLM never holds keys and never signs. It only produces a structured intent; the user
reviews/cancels (Phase 4) and authorizes with their own wallet. This module builds and
validates the intent and computes the economic guards (min-out from slippage).
"""
from __future__ import annotations

from dataclasses import dataclass, field

SIDES = {"buy", "sell"}
MAX_SLIPPAGE_BPS = 5000  # 50% hard cap
DEFAULT_TTL_SECONDS = 300


class IntentError(ValueError):
    pass


@dataclass
class TradeIntent:
    user: str
    token: str
    side: str
    amount: float
    limit_price: float | None
    max_slippage_bps: int
    deadline: int
    nonce: int
    venue: str = "uniswap_v4"
    meta: dict = field(default_factory=dict)


def build_intent(user: str, token: str, side: str, amount: float, now: int,
                 limit_price: float | None = None, max_slippage_bps: int = 100,
                 ttl_seconds: int = DEFAULT_TTL_SECONDS, nonce: int = 0,
                 venue: str = "uniswap_v4", require_limit: bool = False,
                 meta: dict | None = None) -> TradeIntent:
    if not user:
        raise IntentError("user_required")
    if not token:
        raise IntentError("token_required")
    if side not in SIDES:
        raise IntentError(f"invalid_side:{side}")
    if amount <= 0:
        raise IntentError("amount_must_be_positive")
    if not (0 <= int(max_slippage_bps) <= MAX_SLIPPAGE_BPS):
        raise IntentError("slippage_out_of_range")
    if require_limit and limit_price is None:
        raise IntentError("limit_required")
    if limit_price is not None and limit_price <= 0:
        raise IntentError("limit_must_be_positive")
    return TradeIntent(user=user, token=token, side=side, amount=float(amount),
                       limit_price=limit_price, max_slippage_bps=int(max_slippage_bps),
                       deadline=int(now) + int(ttl_seconds), nonce=int(nonce), venue=venue,
                       meta=dict(meta or {}))


def expected_out(intent: TradeIntent) -> float | None:
    """Expected proceeds/base for the intent at its limit price (None if no limit)."""
    if intent.limit_price is None:
        return None
    return intent.amount * intent.limit_price


def min_out(intent: TradeIntent) -> float | None:
    """Worst acceptable output after slippage (economic guard baked into the intent)."""
    exp = expected_out(intent)
    if exp is None:
        return None
    return exp * (1.0 - intent.max_slippage_bps / 10_000.0)


def is_expired(intent: TradeIntent, now: int) -> bool:
    return now > intent.deadline


def intent_digest(intent: TradeIntent) -> dict:
    """Canonical, signing-ready structure (contains no secrets/keys)."""
    return {
        "user": intent.user.lower(),
        "token": intent.token.lower(),
        "side": intent.side,
        "amount": intent.amount,
        "limit_price": intent.limit_price,
        "max_slippage_bps": intent.max_slippage_bps,
        "deadline": intent.deadline,
        "nonce": intent.nonce,
        "venue": intent.venue,
    }
