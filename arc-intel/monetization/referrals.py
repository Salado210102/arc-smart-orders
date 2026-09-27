"""Referral program (pure): code/link parsing + 30% lifetime commission math.

Economics (see docs/ARC_AI_ECONOMIC_MODEL.md): the platform charges a **1%** fee on the
traded notional and pays the referrer a **lifetime 30%** of that fee ("sobre la comisión
neta"). Market benchmark: Trojan <=35%, BullX 30%, Maestro 25%.

This module is dependency-free and side-effect-free (easy to unit-test); persistence and
attribution live in `bot/store.py`.
"""
from __future__ import annotations

import hashlib
import os

FEE_BPS = 100             # 1% of the traded notional
REFERRAL_PCT_BPS = 3000   # 30% of that fee, for life
CODE_PREFIX = "ref_"
CODE_LEN = 8
# No ambiguous characters (no 0/O/1/I) so codes are easy to read and share.
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def make_code(chat_id) -> str:
    """Deterministic, stable code for a chat (same chat always gets the same code)."""
    h = hashlib.sha256(f"arcai-ref:{chat_id}".encode()).digest()
    n = int.from_bytes(h[:8], "big")
    out = []
    for _ in range(CODE_LEN):
        out.append(_ALPHABET[n % len(_ALPHABET)])
        n //= len(_ALPHABET)
    return "".join(out)


def normalize_code(code) -> str:
    c = (code or "").strip().upper()
    if not c:
        return ""
    return c if all(ch in _ALPHABET for ch in c) else ""


def parse_ref_param(text: str) -> str:
    """Extract a referral code from '/start ref_XXXX' (or '/start XXXX'). '' if none."""
    if not text:
        return ""
    parts = text.strip().split()
    if len(parts) < 2:
        return ""
    arg = parts[1].strip()
    if arg.lower().startswith(CODE_PREFIX):
        arg = arg[len(CODE_PREFIX):]
    return normalize_code(arg)


def bot_username() -> str:
    return os.environ.get("ARC_INTEL_BOT_USERNAME", "").lstrip("@")


def referral_link(bot_username: str, code: str) -> str:
    u = (bot_username or "").lstrip("@")
    return f"https://t.me/{u}?start={CODE_PREFIX}{code}" if u else ""


def fee_from_notional(notional_usdc: float, fee_bps: int = FEE_BPS) -> float:
    if notional_usdc < 0:
        raise ValueError("notional_must_be_non_negative")
    if not 0 <= fee_bps <= 10_000:
        raise ValueError("fee_bps_out_of_range")
    return round(notional_usdc * fee_bps / 10_000.0, 6)


def commission_usdc(fee_usdc: float, pct_bps: int = REFERRAL_PCT_BPS) -> float:
    if fee_usdc < 0:
        raise ValueError("fee_must_be_non_negative")
    if not 0 <= pct_bps <= 10_000:
        raise ValueError("pct_bps_out_of_range")
    return round(fee_usdc * pct_bps / 10_000.0, 6)


def commission_from_notional(notional_usdc: float, fee_bps: int = FEE_BPS,
                            pct_bps: int = REFERRAL_PCT_BPS) -> float:
    """Convenience: referral commission for a fill of `notional_usdc`."""
    return commission_usdc(fee_from_notional(notional_usdc, fee_bps), pct_bps)
