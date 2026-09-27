"""Phase 2.3 — cross-chain reputation bootstrap (interfaces + pure logic).

Goal: for a new Arc wallet with insufficient history, use the origin of its first funding to
assign a prior from known reputation on other chains (Ethereum/Base/Solana).

HARD data dependency (documented, not faked):
  (a) a funding graph (who funded the wallet, through which bridge), and
  (b) cross-chain reputation providers (API) with an address mapping.
Native funding is not indexed yet and bridge settlement data is not accessible, so callers
pass empty edges and receive NOT_AVAILABLE. The logic below is testable with injected data.
"""
from __future__ import annotations

from dataclasses import dataclass

ZERO = "0x" + "0" * 40


@dataclass
class FundingEdge:
    wallet: str
    funder: str
    block: int


def funding_edges_from_transfers(native_transfers: list[dict], min_value: int = 0) -> list[FundingEdge]:
    """Build funding edges from native transfers {to_addr, from_addr, value, block_number}."""
    out: list[FundingEdge] = []
    for t in native_transfers:
        to = (t.get("to_addr") or "").lower()
        fr = (t.get("from_addr") or "").lower()
        if not to or not fr or fr == ZERO:
            continue
        try:
            v = int(t.get("value") or 0)
        except (TypeError, ValueError):
            v = 0
        if v <= min_value:
            continue
        out.append(FundingEdge(to, fr, int(t.get("block_number") or 0)))
    return out


def detect_bridge(funder: str, bridges: dict[str, str] | None) -> str | None:
    """Return the source chain name if `funder` is a known bridge, else None."""
    return (bridges or {}).get((funder or "").lower())


def bootstrap_priors(edges: list[FundingEdge], providers: list, bridges: dict[str, str] | None = None,
                     min_history: int = 8, arc_history: dict[str, int] | None = None) -> dict[str, dict]:
    """Assign a cross-chain prior to under-historical wallets.

    providers: list of callables (funder_address, source_chain) -> float|None (reputation 0..1).
    arc_history: {wallet: closed_trades}; wallets with >= min_history are left untouched.
    """
    arc_history = {k.lower(): v for k, v in (arc_history or {}).items()}
    seen: set[str] = set()
    out: dict[str, dict] = {}
    for e in edges:
        w = e.wallet.lower()
        if w in seen or arc_history.get(w, 0) >= min_history:
            continue
        seen.add(w)
        chain = detect_bridge(e.funder, bridges)
        if not chain:
            out[w] = {"status": "NOT_AVAILABLE", "reason": "funder_not_a_known_bridge",
                      "funder": e.funder.lower()}
            continue
        prior = None
        for p in providers:
            try:
                prior = p(e.funder, chain)
            except Exception:
                prior = None
            if prior is not None:
                break
        if prior is None:
            out[w] = {"status": "NOT_AVAILABLE", "reason": "no_provider_has_reputation",
                      "funder": e.funder.lower(), "chain": chain}
        else:
            out[w] = {"status": "ok", "prior": max(0.0, min(1.0, float(prior))),
                      "funder": e.funder.lower(), "chain": chain, "source": "cross_chain"}
    return out
