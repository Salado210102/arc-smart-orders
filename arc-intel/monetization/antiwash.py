"""Anti-wash-trading filters for the volume contest (pure, testable).

Rules (docs/ARC_AI_ECONOMIC_MODEL.md §anti-abuso):
- **Minimum notional** per trade (dust / spam fills don't count).
- **Own tokens** excluded (a user's volume on tokens *they* created is not real trade).
- **Round-trips** excluded: a buy AND a sell of the same token by the same user within `window_s`
  (auto-trading / wash).
- **Same-funding wallets** collapse into ONE entity (merge their volume), so splitting funds across
  wallets doesn't double-count.
"""
from __future__ import annotations

DEFAULT_MIN_NOTIONAL = 5.0   # USDC
DEFAULT_WINDOW_S = 60        # round-trip detection window


def qualifies(fill, min_notional: float = DEFAULT_MIN_NOTIONAL) -> bool:
    return float((fill or {}).get("usdc") or 0.0) >= float(min_notional)


def roundtrip_fill_ids(fills, window_s: int = DEFAULT_WINDOW_S) -> set:
    """Ids of fills that form a same-user, same-token buy+sell pair within `window_s`."""
    by: dict = {}
    for f in fills or []:
        by.setdefault((str(f.get("user")), str(f.get("token") or "").lower()), []).append(f)
    drop = set()
    for lst in by.values():
        lst = sorted(lst, key=lambda x: int(x.get("ts") or 0))
        for i in range(len(lst)):
            for j in range(i + 1, len(lst)):
                a, b = lst[i], lst[j]
                if a.get("side") == b.get("side"):
                    continue
                if abs(int(b.get("ts") or 0) - int(a.get("ts") or 0)) <= int(window_s):
                    drop.add(a.get("fill_id"))
                    drop.add(b.get("fill_id"))
    return drop


def filter_fills(fills, *, min_notional: float = DEFAULT_MIN_NOTIONAL, own_tokens=(),
                 window_s: int = DEFAULT_WINDOW_S) -> list:
    own = {str(t).lower() for t in (own_tokens or ())}
    drop = roundtrip_fill_ids(fills, window_s)
    out = []
    for f in fills or []:
        tok = str(f.get("token") or "").lower()
        if tok in own:
            continue
        if not qualifies(f, min_notional):
            continue
        if f.get("fill_id") in drop:
            continue
        out.append(f)
    return out


def volume_by_user(fills, **kw) -> dict:
    """Volume by user after applying the anti-wash filters."""
    out: dict = {}
    for f in filter_fills(fills, **kw):
        u = str(f.get("user"))
        out[u] = out.get(u, 0.0) + float(f.get("usdc") or 0.0)
    return out


def merge_by_funding(volume_by_user: dict, funding_of) -> dict:
    """Collapse wallets that share a funding source into one entity (sum of volume).

    `funding_of(user) -> source_id`; on error the user is its own source.
    """
    out: dict = {}
    for u, v in (volume_by_user or {}).items():
        try:
            src = funding_of(u) or u
        except Exception:
            src = u
        out[str(src)] = out.get(str(src), 0.0) + float(v)
    return out
