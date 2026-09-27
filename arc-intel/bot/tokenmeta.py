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
ARC_RPC = os.environ.get("ARC_RPC", "https://rpc.mainnet.arc.io")

_SYM_CACHE: dict[str, str] = {}


def _decode_string(hexstr: str) -> str:
    h = (hexstr or "")
    h = h[2:] if h.startswith("0x") else h
    w = [h[i:i + 64] for i in range(0, len(h), 64)]
    return _abi_string(w, 0) or ""


_RPC_CACHE: dict[tuple, int] = {}


def _eth_call(token: str, selector: str, retries: int = 3):
    """eth_call with retry/backoff (the Arc RPC rate-limits and is flaky). None on failure."""
    t = (token or "").lower()
    if not t:
        return None
    for i in range(retries):
        try:
            payload = {"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                       "params": [{"to": t, "data": selector}, "latest"]}
            req = urllib.request.Request(ARC_RPC, data=json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json",
                                                  "User-Agent": "sniper-ia/1.0"})
            return json.load(urllib.request.urlopen(req, timeout=8)).get("result")
        except Exception:
            time.sleep(0.4 * (i + 1))
    return None


def rpc_uint(token: str, selector: str) -> int:
    """eth_call returning a uint256 (0 on failure). Successful values are cached."""
    key = ((token or "").lower(), selector)
    if key in _RPC_CACHE:
        return _RPC_CACHE[key]
    res = _eth_call(token, selector)
    val = 0
    if res and res != "0x":
        try:
            val = int(res, 16)
        except ValueError:
            val = 0
    if val:
        _RPC_CACHE[key] = val
    return val


def rpc_decimals(token: str) -> int:
    d = rpc_uint(token, "0x313ce567")  # decimals()
    return d if 0 < d <= 36 else 18


def rpc_total_supply(token: str) -> int:
    return rpc_uint(token, "0x18160ddd")  # totalSupply()


USDC = "0x3600000000000000000000000000000000000000"


def _rpc(method: str, params: list, retries: int = 3):
    for i in range(retries):
        try:
            payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
            req = urllib.request.Request(ARC_RPC, data=json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json",
                                                  "User-Agent": "sniper-ia/1.0"})
            return json.load(urllib.request.urlopen(req, timeout=8)).get("result")
        except Exception:
            time.sleep(0.4 * (i + 1))
    return None


def native_balance_eth(addr: str) -> int:
    r = _rpc("eth_getBalance", [addr, "latest"])
    try:
        return int(r, 16)
    except (TypeError, ValueError):
        return 0


def erc20_balance(addr: str, token: str = USDC, decimals: int = 6) -> float:
    data = "0x70a08231" + addr.lower().replace("0x", "").rjust(64, "0")
    r = _rpc("eth_call", [{"to": token, "data": data}, "latest"])
    try:
        return int(r, 16) / (10 ** decimals)
    except (TypeError, ValueError):
        return 0.0


def rpc_symbol(token: str) -> str:
    """On-chain ERC20 symbol() via Arc RPC (cached). '' on failure."""
    t = (token or "").lower()
    if not t:
        return ""
    if t in _SYM_CACHE:
        return _SYM_CACHE[t]
    res = _eth_call(token, "0x95d89b41")  # symbol()
    sym = _decode_string(res) if res and res != "0x" else ""
    if sym:
        _SYM_CACHE[t] = sym
    return sym


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
