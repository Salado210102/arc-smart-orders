"""TOTP (RFC 6238 / RFC 4226) — pure, no dependencies.

Used for custody 2FA (registering withdrawal addresses + withdrawing). Secrets are base32 and
stored **encrypted** at rest (see `execution.signer`); this module never persists anything.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import struct
import time
from urllib.parse import quote

DIGITS = 6
PERIOD = 30


def new_secret(nbytes: int = 20) -> str:
    return base64.b32encode(os.urandom(int(nbytes))).decode().rstrip("=")


def _decode(secret: str) -> bytes:
    s = (secret or "").strip().upper().replace(" ", "")
    pad = "=" * ((8 - len(s) % 8) % 8)
    return base64.b32decode(s + pad)


def code(secret: str, at: int | None = None, period: int = PERIOD, digits: int = DIGITS) -> str:
    counter = int(at if at is not None else time.time()) // int(period)
    mac = hmac.new(_decode(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    val = struct.unpack(">I", mac[off:off + 4])[0] & 0x7FFFFFFF
    return str(val % (10 ** int(digits))).zfill(int(digits))


def verify(secret: str, token: str, at: int | None = None, window: int = 1,
           period: int = PERIOD, digits: int = DIGITS) -> bool:
    """True if `token` matches within +/- `window` periods (clock skew tolerance)."""
    if not secret or not token:
        return False
    at = int(at if at is not None else time.time())
    tok = str(token).strip()
    for w in range(-int(window), int(window) + 1):
        if hmac.compare_digest(code(secret, at + w * int(period), period, digits), tok):
            return True
    return False


def provisioning_uri(secret: str, account: str, issuer: str = "SNIPER IA") -> str:
    return (f"otpauth://totp/{quote(issuer)}:{quote(str(account))}?secret={secret}"
            f"&issuer={quote(issuer)}&digits={DIGITS}&period={PERIOD}")
