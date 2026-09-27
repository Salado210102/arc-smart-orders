"""Token-contract risk scanner (anti-rug heuristic): honeypot machinery, mint, pause, blacklist...

Honesty: this is a **static heuristic** (function selectors present in the bytecode + owner/proxy
state). It is NOT a proof that a token can or cannot be sold. A real honeypot simulation is a future
step. We label results as heuristic everywhere.

Pure core (`keccak256`, `scan_bytecode`, `classify`) is testable with no network; `analyze_token`
takes injectable RPC fetchers.
"""
from __future__ import annotations

import time

# --- Keccak-256 (Ethereum) in pure Python (stdlib only) -----------------------------------------

_KECCAK_RC = [
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
    0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
    0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
    0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
]
_KECCAK_R = [[0, 36, 3, 41, 18], [1, 44, 10, 45, 2], [62, 6, 43, 15, 61],
             [28, 55, 25, 21, 56], [27, 20, 39, 8, 14]]
_MASK64 = (1 << 64) - 1


def _rol(x: int, n: int) -> int:
    if n == 0:
        return x
    return ((x << n) | (x >> (64 - n))) & _MASK64


def _keccak_f(state: list) -> None:
    for rc in _KECCAK_RC:
        c = [state[x] ^ state[x + 5] ^ state[x + 10] ^ state[x + 15] ^ state[x + 20] for x in range(5)]
        d = [c[(x - 1) % 5] ^ _rol(c[(x + 1) % 5], 1) for x in range(5)]
        for x in range(5):
            for y in range(0, 25, 5):
                state[x + y] ^= d[x]
        b = [0] * 25
        for x in range(5):
            for y in range(5):
                b[y + 5 * ((2 * x + 3 * y) % 5)] = _rol(state[x + 5 * y], _KECCAK_R[x][y])
        for x in range(5):
            for y in range(5):
                state[x + 5 * y] = b[x + 5 * y] ^ ((~b[(x + 1) % 5 + 5 * y]) & b[(x + 2) % 5 + 5 * y])
        state[0] ^= rc


def keccak256(data: bytes) -> bytes:
    rate = 136  # 1088-bit rate
    d = bytearray(data)
    d.append(0x01)               # Keccak (Ethereum) padding, not SHA3's 0x06
    while len(d) % rate != 0:
        d.append(0x00)
    d[-1] ^= 0x80
    state = [0] * 25
    for off in range(0, len(d), rate):
        block = d[off:off + rate]
        for i in range(rate // 8):
            state[i] ^= int.from_bytes(block[i * 8:i * 8 + 8], "little")
        _keccak_f(state)
    return b"".join(state[i].to_bytes(8, "little") for i in range(25))[:32]


def selector(signature: str) -> str:
    """4-byte function selector as 0x-hex, e.g. selector('transfer(address,uint256)')."""
    return "0x" + keccak256(signature.encode()).hex()[:8]


# --- Risk signatures -----------------------------------------------------------------------------

RISKY = {
    "mint": ["mint(address,uint256)", "mint(uint256)", "_mint(address,uint256)"],
    "pause": ["pause()", "unpause()", "paused()"],
    "blacklist": ["blacklist(address)", "addBlackList(address)", "setBlacklist(address,bool)",
                  "isBlacklisted(address)", "addBotToBlackList(address)"],
    "trading_toggle": ["enableTrading()", "openTrading()", "setTrading(bool)", "tradingEnabled()",
                       "enableTrading(bool)", "startTrading()"],
    "tax": ["setTax(uint256)", "setTaxFee(uint256)", "setFees(uint256,uint256)",
            "setMarketingFee(uint256)", "setBuyFee(uint256)"],
    "limits": ["setMaxTxAmount(uint256)", "setMaxWalletAmount(uint256)", "setMaxWallet(uint256)"],
    "control": ["owner()", "renounceOwnership()", "transferOwnership(address)"],
}

EIP1967_IMPL_SLOT = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"
ZERO_ADDR = "0x" + "0" * 40


def scan_bytecode(code_hex: str) -> dict:
    """Which risky selectors appear literally in the runtime bytecode (PUSH4 dispatchers)."""
    code = (code_hex or "").lower()
    code = code[2:] if code.startswith("0x") else code
    if not code or code in ("0", "00"):
        return {"has_code": False, "found": {}, "categories": []}
    found = {}
    for cat, sigs in RISKY.items():
        hits = [s for s in sigs if selector(s)[2:] in code]
        if hits:
            found[cat] = hits
    return {"has_code": True, "found": found, "categories": sorted(found)}


def extract_minimal_proxy_impl(code_hex: str) -> str | None:
    """EIP-1167 minimal-proxy target address, or None. (Argus tokens are clones.)"""
    code = (code_hex or "").lower()
    code = code[2:] if code.startswith("0x") else code
    prefix = "363d3d373d3d3d363d73"
    suffix = "5af43d82803e903d91602b57fd5bf3"
    if code.startswith(prefix) and code.endswith(suffix) and len(code) >= len(prefix) + 40:
        return "0x" + code[len(prefix):len(prefix) + 40]
    return None


def classify(flags: dict, owner: str | None, is_upgradeable: bool, proxy_kind: str | None = None) -> dict:
    """Heuristic risk level + reasons from the scan flags."""
    cats = set(flags.get("categories") or [])
    reasons = []
    level = "low"
    if not flags.get("has_code"):
        return {"level": "unknown", "reasons": ["no_bytecode"], "honeypot_hint": False}
    if is_upgradeable:
        reasons.append("upgradeable_proxy")
        level = "high"
    if "blacklist" in cats or "trading_toggle" in cats:
        reasons.append("honeypot_machinery")
        level = "high"
    if "pause" in cats:
        reasons.append("can_pause")
        level = "high"
    if "mint" in cats:
        reasons.append("can_mint")
        level = "high"
    if "tax" in cats:
        reasons.append("configurable_tax")
        level = "high" if level == "high" else "medium"
    if "limits" in cats:
        reasons.append("trading_limits")
        if level == "low":
            level = "medium"
    if "control" in cats and owner and owner != ZERO_ADDR:
        reasons.append("owner_active")
        if level == "low":
            level = "medium"
    if proxy_kind == "minimal":
        reasons.append("minimal_proxy")   # informational: immutable clone, not upgradeable
    honeypot_hint = ("blacklist" in cats) or ("trading_toggle" in cats)
    return {"level": level, "reasons": reasons, "honeypot_hint": honeypot_hint,
            "categories": sorted(cats)}


_CACHE: dict = {}
_TTL = 3600
DEFAULT_RPC = "https://rpc.mainnet.arc.io"


def _jsonrpc(rpc: str, method: str, params: list, retries: int = 2):
    import json
    import urllib.request
    for i in range(retries):
        try:
            body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
            req = urllib.request.Request(rpc, data=body,
                                         headers={"Content-Type": "application/json",
                                                  "User-Agent": "sniper-ia/1.0"})
            return json.load(urllib.request.urlopen(req, timeout=8)).get("result")
        except Exception:
            time.sleep(0.4 * (i + 1))
    return None


def _default_fetchers():
    import os
    rpc = os.environ.get("ARC_RPC", DEFAULT_RPC)
    return (lambda tok: _jsonrpc(rpc, "eth_getCode", [tok, "latest"]),
            lambda tok, data: _jsonrpc(rpc, "eth_call", [{"to": tok, "data": data}, "latest"]),
            lambda tok, slot: _jsonrpc(rpc, "eth_getStorageAt", [tok, slot, "latest"]))


def _addr_from_word(res) -> str | None:
    if not res or res == "0x" or len(res) < 42:
        return None
    return "0x" + res[-40:].lower()


def analyze_token(token: str, *, get_code=None, call=None, get_storage=None,
                  use_cache: bool = True) -> dict:
    """Fetch bytecode (resolving minimal proxies) + owner + proxy slot; classify. Never raises."""
    token = (token or "").lower()
    if not token:
        return {"address": "", "level": "unknown", "reasons": [], "flags": {}, "owner": None}
    now = time.time()
    if use_cache and token in _CACHE and now - _CACHE[token][0] < _TTL:
        return _CACHE[token][1]
    if get_code is None:
        get_code, call, get_storage = _default_fetchers()
    try:
        code = get_code(token)
    except Exception:
        code = None
    if code is None:
        return {"address": token, "level": "unknown", "reasons": ["rpc_unavailable"],
                "flags": {}, "owner": None, "impl": None, "proxy_kind": None}
    impl = extract_minimal_proxy_impl(code)
    proxy_kind = "minimal" if impl else None
    scan_code = code
    if impl:
        try:
            impl_code = get_code(impl)
        except Exception:
            impl_code = None
        if impl_code and impl_code not in ("0x", "0x0"):
            scan_code = impl_code
    flags = scan_bytecode(scan_code)
    owner = None
    is_upgradeable = False
    if flags.get("has_code") or impl:
        try:
            owner = _addr_from_word(call(token, selector("owner()")))
        except Exception:
            owner = None
        try:
            s = get_storage(token, EIP1967_IMPL_SLOT)
            is_upgradeable = bool(s and s != "0x" and int(s, 16) != 0)
        except Exception:
            is_upgradeable = False
    cls = classify(flags, owner, is_upgradeable, proxy_kind)
    out = {"address": token, "owner": owner, "impl": impl, "proxy_kind": proxy_kind,
           "flags": flags.get("found", {}), "categories": cls.get("categories", []),
           "level": cls["level"], "reasons": cls["reasons"], "honeypot_hint": cls["honeypot_hint"],
           "heuristic": True}
    _CACHE[token] = (now, out)
    return out
