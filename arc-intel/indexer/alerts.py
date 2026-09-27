"""Phase 3 — risk alert engine (dev-sell / insider / volume collapse / compound).

Detects objectively bad on-chain behavior (not predictive skill). Reuses the Fase 2.1
insider set (tokens.creator + dev-buy recipients) — not rebuilt here. Alert objects are
Telegram-ready (all context included).
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from .risk import rolling_zscore

SECONDS_PER_BLOCK = 0.52
POSITION_MANAGER = "0x6049c9a0e26405c0985f9e3685c87d0ae917f82b"
DEFAULT_RPC = "https://rpc.mainnet.arc.io"


def _owner_of(rpc_url: str, block: int, token_id: int, retries: int = 6):
    data = "0x6352211e" + format(token_id, "064x")  # ownerOf(uint256)
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                       "params": [{"to": POSITION_MANAGER, "data": data}, hex(max(0, block - 1))]}).encode()
    for attempt in range(retries):
        req = urllib.request.Request(rpc_url, data=body,
                                     headers={"Content-Type": "application/json",
                                              "User-Agent": "Mozilla/5.0"})
        try:
            res = json.load(urllib.request.urlopen(req, timeout=30)).get("result")
            if res and res != "0x":
                return "0x" + res[-40:]
            return None
        except urllib.error.HTTPError as e:
            if e.code in (429, 403) and attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            return None
    return None


def attribute_liquidity_owners(rows: list[dict], rpc_url: str = DEFAULT_RPC,
                               min_ratio: float = 0.5) -> dict:
    """Resolve the PositionManager NFT owner for significant removals (sender == PM)."""
    cache: dict = {}
    resolved = 0
    by_creator = 0
    for r in rows:
        if (r.get("sender") or "").lower() != POSITION_MANAGER:
            continue
        added = r.get("added") or 0.0
        delta = r.get("delta") or 0.0
        if added <= 0 or delta >= 0 or (abs(delta) / added) < min_ratio:
            continue
        salt = r.get("salt") or ""
        try:
            tid = int(salt, 16)
        except (TypeError, ValueError):
            continue
        if tid == 0:
            continue
        key = (tid, r["block"])
        if key not in cache:
            cache[key] = _owner_of(rpc_url, r["block"], tid)
        owner = cache[key]
        r["owner"] = owner
        r["owner_is_creator"] = bool(owner and (owner.lower() == (r.get("creator") or "").lower()))
        resolved += 1
        if r["owner_is_creator"]:
            by_creator += 1
    return {"attempted": resolved, "owner_is_creator": by_creator}


@dataclass
class Alert:
    token: str
    kind: str                    # dev_sell | volume_collapse | compound | liquidity_removal
    severity: str                # low | medium | high
    block: int
    wallet: str | None = None
    role: str | None = None      # creator | insider
    amount_usdc: float | None = None
    pct_position: float | None = None
    context: dict = field(default_factory=dict)
    message: str = ""


def pct_of_position(sell_qty: float, pos_before: float) -> float | None:
    if pos_before <= 0:
        return None
    return max(0.0, min(1.0, sell_qty / pos_before))


def is_significant_sell(sell_qty: float, pos_before: float, usdc: float,
                        min_pct: float = 0.5, min_usdc: float = 100.0) -> bool:
    pct = pct_of_position(sell_qty, pos_before)
    if pct is None:
        return False
    return pct >= min_pct or usdc >= min_usdc


def severity_for(pct: float | None, usdc: float | None) -> str:
    p = pct if pct is not None else 0.0
    u = usdc if usdc is not None else 0.0
    if p >= 0.8 or u >= 5000:
        return "high"
    if p >= 0.5 or u >= 500:
        return "medium"
    return "low"


def detect_compound(dev_sell_blocks: dict[str, int], collapse_buckets: dict[str, int],
                    window_blocks: int) -> dict[str, int]:
    """Tokens where a volume collapse occurs shortly after a dev-sell (same token)."""
    out = {}
    for token, sell_block in dev_sell_blocks.items():
        cb = collapse_buckets.get(token)
        if cb is None:
            continue
        if 0 <= (cb - sell_block) <= window_blocks:
            out[token] = cb
    return out


def _msg_dev_sell(a: Alert) -> str:
    pct = f"{a.pct_position * 100:.0f}%" if a.pct_position is not None else "?"
    return (f"{a.wallet} ({a.role}) sold {pct} of its {a.token} position"
            f" (~${a.amount_usdc:,.0f}) at block {a.block}")


def _msg_volume(a: Alert) -> str:
    return (f"{a.token}: volume collapse at block {a.block} "
            f"(z={a.context.get('z')})")


def _msg_compound(a: Alert) -> str:
    return (f"{a.token}: dev-sell at block {a.context.get('sell_block')} followed by "
            f"volume collapse at {a.block} (z={a.context.get('z')})")


def dev_sell_alerts(rows: list[dict], min_pct: float = 0.5, min_usdc: float = 100.0) -> list[Alert]:
    out = []
    for r in rows:
        pct = pct_of_position(r["sell_qty"], r["pos_before"])
        if not is_significant_sell(r["sell_qty"], r["pos_before"], r["usdc"], min_pct, min_usdc):
            continue
        a = Alert(token=r["token"], kind="dev_sell",
                  severity=severity_for(pct, r["usdc"]), block=r["block"],
                  wallet=r["wallet"], role=r.get("role", "creator"),
                  amount_usdc=r["usdc"], pct_position=pct,
                  context={"pos_before": r["pos_before"], "sell_qty": r["sell_qty"]})
        a.message = _msg_dev_sell(a)
        out.append(a)
    return out


def volume_collapse_alerts(series_by_token: dict, z_threshold: float = -2.0,
                           lookback: int = 12) -> list[Alert]:
    out = []
    for token, series in series_by_token.items():
        z = rolling_zscore(series, lookback)
        if not z or z[-1][1] is None:
            continue
        b, val = z[-1]
        if val <= z_threshold:
            a = Alert(token=token, kind="volume_collapse",
                      severity="high" if val <= -3 else "medium", block=b,
                      context={"z": round(val, 3), "last_bucket": b})
            a.message = _msg_volume(a)
            out.append(a)
    return out


def compound_alerts(dev_sells: list[Alert], collapse: list[Alert],
                    window_blocks: int) -> list[Alert]:
    collapse_by_token = {c.token: c for c in collapse}
    sell_blocks = {a.token: a.block for a in dev_sells}
    hits = detect_compound(sell_blocks, {t: c.block for t, c in collapse_by_token.items()},
                           window_blocks)
    out = []
    for token, cb in hits.items():
        sellers = [a for a in dev_sells if a.token == token]
        pct = max((a.pct_position or 0.0) for a in sellers) if sellers else None
        a = Alert(token=token, kind="compound", severity="high", block=cb,
                  wallet=sellers[0].wallet if sellers else None, role="creator",
                  pct_position=pct,
                  context={"sell_block": sell_blocks[token],
                           "z": collapse_by_token[token].context.get("z"),
                           "sellers": len(sellers)})
        a.message = _msg_compound(a)
        out.append(a)
    return out


def liquidity_removal_alerts(rows: list[dict], min_ratio: float = 0.5) -> list[Alert]:
    out = []
    for r in rows:
        added = r.get("added") or 0.0
        delta = r.get("delta") or 0.0
        if delta >= 0 or added <= 0:
            continue
        ratio = min(1.0, abs(delta) / added)
        if ratio < min_ratio:
            continue
        creator = (r.get("creator") or "").lower()
        sender = (r.get("sender") or "").lower()
        is_creator = bool(r.get("owner_is_creator")) or (creator and sender == creator)
        role = "creator" if is_creator else "unknown"
        sev = "high" if (ratio >= 0.9 and is_creator) else ("medium" if ratio >= 0.7 else "low")
        try:
            token_id = int(r.get("salt") or "0x0", 16)
        except (TypeError, ValueError):
            token_id = 0
        a = Alert(token=r.get("token") or r.get("pool_id"), kind="liquidity_removal",
                  severity=sev, block=int(r["block"]), wallet=r.get("owner") or sender, role=role,
                  context={"pool_id": r.get("pool_id"), "removed_ratio": round(ratio, 3),
                           "token_id": token_id, "owner": r.get("owner")})
        a.message = (f"{(r.get('owner') or sender)} removed {ratio * 100:.0f}% of pool "
                     f"{r.get('pool_id')} liquidity (role={role}) at block {r['block']}")
        out.append(a)
    return out


def load_liquidity_removals(storage) -> list[dict]:
    conn = storage.pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "WITH agg AS (SELECT pool_id, sum(CASE WHEN (liquidity_delta)::numeric > 0 "
                "  THEN (liquidity_delta)::numeric ELSE 0 END) AS added "
                "  FROM v4_liquidity GROUP BY pool_id) "
                "SELECT l.pool_id, l.sender, l.block_number, (l.liquidity_delta)::numeric, "
                " t.creator, t.address, a.added, l.salt "
                "FROM v4_liquidity l LEFT JOIN tokens t ON t.pool_id = l.pool_id "
                "LEFT JOIN agg a ON a.pool_id = l.pool_id "
                "WHERE (l.liquidity_delta)::numeric < 0")
            return [{"pool_id": r[0], "sender": r[1], "block": int(r[2]), "delta": float(r[3] or 0),
                     "creator": r[4], "token": r[5], "added": float(r[6] or 0), "salt": r[7]}
                    for r in cur.fetchall()]
    finally:
        storage.pool.putconn(conn)


def is_thin_market(swaps: int, distinct_wallets: int, age_blocks: int,
                   no_trade_blocks: int = 100000, min_wallets: int = 2) -> str | None:
    """Informative (low severity): 'no_trades' if old & never traded; 'single_wallet' if
    it traded but only via one wallet after enough age. Returns a reason or None."""
    if age_blocks < no_trade_blocks:
        return None
    if swaps == 0:
        return "no_trades"
    if distinct_wallets <= 1:
        return "single_wallet"
    return None


def thin_market_alerts(storage, head_block: int | None = None, no_trade_blocks: int = 100000,
                       max_scan: int = 40000) -> list[Alert]:
    conn = storage.pool.getconn()
    try:
        with conn.cursor() as cur:
            if head_block is None:
                cur.execute("SELECT max(block_number) FROM swaps")
                head_block = int(cur.fetchone()[0] or 0)
            cur.execute(
                "WITH tc AS (SELECT token, min(block_number) cb FROM launchpad_events "
                "  WHERE event_name='TokenCreated' GROUP BY 1), "
                "s AS (SELECT token, count(*) n, count(DISTINCT wallet) w FROM legs GROUP BY 1) "
                "SELECT tc.token, coalesce(s.n,0), coalesce(s.w,0) FROM tc LEFT JOIN s ON s.token=tc.token "
                "WHERE (%s - tc.cb) >= %s AND (coalesce(s.n,0)=0 OR coalesce(s.w,0) <= 1) "
                "LIMIT %s", (head_block, no_trade_blocks, max_scan))
            out = []
            for token, n, w in cur.fetchall():
                n = int(n)
                w = int(w)
                reason = "no_trades" if n == 0 else ("single_wallet" if w <= 1 else None)
                if not reason:
                    continue
                a = Alert(token=token, kind="thin_market", severity="low", block=head_block,
                          context={"swaps": n, "distinct_wallets": w, "reason": reason})
                a.message = (f"{token}: thin market - {reason} ({n} swaps, {w} wallets) "
                             f"after {no_trade_blocks} blocks; may have no real market")
                out.append(a)
            return out
    finally:
        storage.pool.putconn(conn)
def load_creator_sells(storage) -> list[dict]:
    """Creator dev-sells, attributing intermediary (dev) activity to the creator.

    The creator's initial dev-buy is executed by an intermediary contract, so the creator's
    own wallet has no prior buy. We identify the dev-wallet per token (wallet of the first
    buy leg in that token) and treat its legs as the creator's, so pos_before is meaningful.
    """
    conn = storage.pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "WITH dev AS (SELECT DISTINCT ON (l.token) l.token, l.wallet AS dev_wallet "
                "  FROM legs l JOIN tokens t ON t.address=l.token WHERE l.side='buy' "
                "  ORDER BY l.token, l.block, l.log_index), "
                "act AS (SELECT l.token, t.creator, l.block, l.log_index, l.side, l.token_qty, "
                "  l.stable_value, "
                "  sum(CASE WHEN l.side='buy' THEN l.token_qty ELSE 0 END) OVER w AS cbq, "
                "  sum(CASE WHEN l.side='sell' THEN l.token_qty ELSE 0 END) OVER w AS csq "
                "  FROM legs l JOIN tokens t ON t.address=l.token JOIN dev d ON d.token=l.token "
                "  WHERE l.wallet = t.creator OR l.wallet = d.dev_wallet "
                "  WINDOW w AS (PARTITION BY l.token ORDER BY l.block, l.log_index "
                "               ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING)) "
                "SELECT a.token, a.creator, a.block, a.token_qty, a.stable_value, (a.cbq - a.csq) "
                "FROM act a WHERE a.side='sell' AND (a.cbq - a.csq) > 0")
            return [{"token": r[0], "wallet": r[1], "block": int(r[2]),
                     "sell_qty": float(r[3] or 0.0), "usdc": float(r[4] or 0.0),
                     "pos_before": float(r[5] or 0.0)} for r in cur.fetchall()]
    finally:
        storage.pool.putconn(conn)


def load_volume_buckets(storage, bucket_seconds: int = 600) -> dict:
    bpb = max(1, int(bucket_seconds / SECONDS_PER_BLOCK))
    conn = storage.pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT token, (block / %s) AS b, sum(stable_value) FROM legs "
                        "GROUP BY 1,2 ORDER BY 1,2", (bpb,))
            series: dict[str, list] = {}
            for token, b, vol in cur.fetchall():
                series.setdefault(token, []).append((int(b) * bpb, float(vol or 0.0)))
            return series
    finally:
        storage.pool.putconn(conn)


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", type=str)
    ap.add_argument("--min-pct", type=float, default=0.5)
    ap.add_argument("--min-usdc", type=float, default=100.0)
    ap.add_argument("--bucket-seconds", type=int, default=600)
    ap.add_argument("--z", type=float, default=-2.0)
    ap.add_argument("--window-blocks", type=int, default=6000)
    ap.add_argument("--resolve-liquidity", action="store_true",
                    help="resolve PositionManager NFT owner for liquidity removals (RPC calls)")
    ap.add_argument("--thin-blocks", type=int, default=100000,
                    help="age (blocks) after which a dead/single-wallet token is thin-market")
    ap.add_argument("--top", type=int, default=5)
    args = ap.parse_args()
    from .pg_storage import PostgresStorage
    storage = PostgresStorage(args.dsn)
    rows = load_creator_sells(storage)
    dev = dev_sell_alerts(rows, args.min_pct, args.min_usdc)
    series = load_volume_buckets(storage, args.bucket_seconds)
    try:
        liq_rows = load_liquidity_removals(storage)
    except Exception:
        liq_rows = []
    try:
        thin = thin_market_alerts(storage, no_trade_blocks=args.thin_blocks, max_scan=40000)
    except Exception:
        thin = []
    storage.close()
    collapse = volume_collapse_alerts(series, z_threshold=args.z)
    comp = compound_alerts(dev, collapse, args.window_blocks)
    liq_attr = attribute_liquidity_owners(liq_rows) if (liq_rows and args.resolve_liquidity) else {"attempted": 0, "owner_is_creator": 0}
    liq = liquidity_removal_alerts(liq_rows)
    liq_creator = sum(1 for a in liq if a.role == "creator")

    full = sum(1 for a in dev if (a.pct_position or 0) >= 0.8)
    partial = sum(1 for a in dev if (a.pct_position or 0) < 0.25)
    dev_sorted = sorted(dev, key=lambda a: (a.severity == "high", a.amount_usdc or 0), reverse=True)
    print({"creator_sells_total": len(rows), "dev_sell_alerts": len(dev),
           "full_exits(>=80%)": full, "partial(<25%)": partial,
           "volume_collapse_tokens": len(collapse), "compound_alerts": len(comp),
           "liquidity_removals_total": len(liq_rows), "liquidity_removal_alerts": len(liq),
           "liquidity_owner_attribution": liq_attr, "liquidity_alerts_creator": liq_creator,
           "thin_market_alerts": len(thin),
           "thin_example": [thin[0].__dict__] if thin else [],
           "top_dev_sells": [a.__dict__ for a in dev_sorted[:args.top]],
           "compound_examples": [a.__dict__ for a in comp[:args.top]],
           "liquidity_examples": [a.__dict__ for a in liq[:args.top]]})


if __name__ == "__main__":
    main()
