"""URL sanitization for untrusted (creator/chain-controlled) links and images.

Only absolute `https://` URLs are allowed; `javascript:`, `data:`, `http:` and anything malformed are
rejected (returns ""). Used by the Mini App data layer and the bot when rendering token metadata.
"""
from __future__ import annotations

from urllib.parse import urlparse


def safe_url(u) -> str:
    u = (u or "").strip()
    if not u or len(u) > 2048:
        return ""
    try:
        p = urlparse(u)
    except Exception:
        return ""
    if p.scheme.lower() != "https" or not p.netloc:
        return ""
    return u


def is_https(u) -> bool:
    return bool(safe_url(u))


def sanitize_dex(dex) -> dict:
    """Return a copy of a DexScreener-style dict with only https links/images/embeds."""
    if not isinstance(dex, dict):
        return {}
    d = dict(dex)
    for key in ("socials", "websites"):
        items = []
        for it in (d.get(key) or []):
            if not isinstance(it, dict):
                continue
            u = safe_url(it.get("url"))
            if u:
                it = dict(it)
                it["url"] = u
                items.append(it)
        d[key] = items
    if d.get("logo") and not safe_url(d.get("logo")):
        d.pop("logo", None)
    if d.get("embed") and not safe_url(d.get("embed")):
        d.pop("embed", None)
    return d
