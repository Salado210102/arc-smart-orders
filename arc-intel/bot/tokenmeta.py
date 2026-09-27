"""Best-effort token metadata (symbol + logo) via the public DexScreener API.

Cached in memory, short timeout, and **never fatal**: if the token is not listed
(Arc tokens often won't be yet) or the network fails, it just returns empty fields.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request

IPFS_GATEWAY = os.environ.get("ARC_INTEL_IPFS_GATEWAY", "https://gateway.pinata.cloud/ipfs/")


def _words(data_hex: str) -> list:
    h = (data_hex or "")
    h = h[2:] if h.startswith("0x") else h
    return [h[i:i + 64] for i in range(0, len(h), 64)]


def _abi_string(words: list, slot: int):
    try:
        off = int(words[slot], 16) // 32
        if off >= len(words):
            return None
        length = int(words[off], 16)
        body = "".join(words[off + 1: off + 1 + (length + 31) // 32])
        return bytes.fromhex(body[:length * 2]).decode("utf-8", "replace").replace("\x00", "")
    except Exception:
        return None


def ipfs_to_http(uri: str) -> str:
    uri = (uri or "").strip()
    if uri.startswith("ipfs://"):
        return IPFS_GATEWAY + uri[len("ipfs://"):]
    return uri


def argus_image(token_created_data: str) -> str:
    """Argus TokenCreated data: (string name, string symbol, bytes32 poolId, string imageURI, ...)"""
    w = _words(token_created_data)
    if len(w) < 7:
        return ""
    return ipfs_to_http(_abi_string(w, 3) or "")

_CACHE: dict[str, tuple] = {}
_TTL_OK = 3600        # found: re-check hourly
_TTL_MISS = 21600     # not found: don't hammer the API (Arc tokens are often unlisted)
_DEX = "https://api.dexscreener.com/latest/dex/tokens/"


def fetch(token: str) -> dict:
    token = (token or "").lower()
    if not token:
        return {"symbol": "", "name": "", "logo": ""}
    now = time.time()
    hit = _CACHE.get(token)
    if hit:
        ts, cached, found = hit
        if now - ts < (_TTL_OK if found else _TTL_MISS):
            return cached
    info = {"symbol": "", "name": "", "logo": ""}
    try:
        req = urllib.request.Request(_DEX + token, headers={"User-Agent": "sniper-ia/1.0"})
        data = json.load(urllib.request.urlopen(req, timeout=4))
        for p in (data.get("pairs") or []):
            base = p.get("baseToken") or {}
            if (base.get("address") or "").lower() == token:
                info["symbol"] = base.get("symbol") or ""
                info["name"] = base.get("name") or ""
                info["logo"] = ((p.get("info") or {}).get("imageUrl")) or ""
                break
    except Exception:
        pass
    found = bool(info["symbol"] or info["logo"])
    _CACHE[token] = (now, info, found)
    return info


def symbol(token: str) -> str:
    return fetch(token).get("symbol", "")


def logo(token: str) -> str:
    return fetch(token).get("logo", "")
