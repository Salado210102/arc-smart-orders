"""Token metadata for valuation: decimals and stablecoin registry.

Arc mainnet verified addresses (see session notes). Unknown tokens default to 18 decimals
(the launchpad standard); callers can enrich via RPC decimals() and pass a full map.
"""
from __future__ import annotations

DEFAULT_DECIMALS = 18

# address(lower) -> (symbol, decimals)
KNOWN_TOKEN_META: dict[str, tuple[str, int]] = {
    "0x0000000000000000000000000000000000000000": ("NATIVE", 18),
    "0xfffffffffffffffffffffffffffffffffffffffe": ("USDC", 18),
    "0x3600000000000000000000000000000000000000": ("USDC", 6),
    "0xbef5f6d51cb62b58e6a8f77868681825c6fe21c1": ("EURC", 6),
    "0x171a4217b86a807a64eb94757db6849fb4dbdaa0": ("cirBTC", 8),
}

# Quote assets usable to value a launchpad token in ~USD.
USD_STABLES: dict[str, int] = {
    "0x0000000000000000000000000000000000000000": 18,
    "0xfffffffffffffffffffffffffffffffffffffffe": 18,
    "0x3600000000000000000000000000000000000000": 6,
    "0xbef5f6d51cb62b58e6a8f77868681825c6fe21c1": 6,  # EURC (approx ~USD)
}


def decimals(token: str, meta: dict[str, int] | None = None) -> int:
    t = (token or "").lower()
    if meta and t in meta:
        return meta[t]
    if t in KNOWN_TOKEN_META:
        return KNOWN_TOKEN_META[t][1]
    return DEFAULT_DECIMALS


def is_usd_stable(token: str, extra: set[str] | None = None) -> bool:
    t = (token or "").lower()
    return t in USD_STABLES or (extra is not None and t in extra)
