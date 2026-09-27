"""Telegram WebApp `initData` validation (HMAC-SHA256) for Mini App auth.

Pure crypto: no network, no baked secrets. The bot token is passed in by the caller
(`bot.telegram.load_token` reads it from env/.env). Spec:
https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl


def _secret_key(bot_token: str) -> bytes:
    # secret_key = HMAC_SHA256(key="WebAppData", msg=bot_token)
    return hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()


def parse_init_data(init_data: str) -> dict:
    return dict(parse_qsl(init_data or "", keep_blank_values=True))


def data_check_string(fields: dict) -> str:
    return "\n".join(f"{k}={fields[k]}" for k in sorted(fields) if k != "hash")


def sign_init_data(fields: dict, bot_token: str) -> str:
    """Test helper: compute the `hash` for a set of fields (not used at runtime)."""
    return hmac.new(_secret_key(bot_token), data_check_string(fields).encode(),
                    hashlib.sha256).hexdigest()


def validate_init_data(init_data: str, bot_token: str, max_age: int = 86400,
                       now: int | None = None) -> dict | None:
    """Return parsed data (with 'user' as dict, 'auth_date' as int) if valid + fresh, else None."""
    if not init_data or not bot_token:
        return None
    fields = parse_init_data(init_data)
    recv = fields.get("hash")
    if not recv:
        return None
    calc = sign_init_data(fields, bot_token)
    if not hmac.compare_digest(calc, recv):
        return None
    now = int(time.time()) if now is None else int(now)
    try:
        auth_date = int(fields.get("auth_date", "0"))
    except ValueError:
        return None
    if max_age and (now - auth_date) > int(max_age):
        return None
    fields["auth_date"] = auth_date
    if "user" in fields:
        try:
            fields["user"] = json.loads(fields["user"])
        except ValueError:
            return None
    return fields
