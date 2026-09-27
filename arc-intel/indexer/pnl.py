"""Phase 2 — trade reconstruction and PnL metrics per wallet (pure, testable).

From raw v4 swaps (amount0/amount1 signed, pool currencies known) we reconstruct each
wallet's buy/sell legs against a USD stable quote, then compute closed-trade statistics:
win rate, average/median exit multiple, realized PnL, return variance, holding time and
entry-timing percentile relative to other wallets in the same token.

Skips pools with no USD-stable leg (cannot value). Amounts are floats for analysis
(not accounting); precision limits are documented in the report.
"""
from __future__ import annotations

from dataclasses import dataclass

from .tokenmeta import decimals, is_usd_stable

SECONDS_PER_BLOCK = 0.52


def _int(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def leg_from_swap(swap: dict, pools: dict, dec_meta: dict | None = None,
                  usd_stables: set | None = None) -> dict | None:
    """Convert one swap into a valued leg (buy/sell of a token against a USD stable)."""
    pool = (swap.get("pool") or "").lower()
    pair = pools.get(pool)
    if not pair:
        return None
    c0, c1 = (pair[0] or "").lower(), (pair[1] or "").lower()
    a0, a1 = _int(swap.get("amount_in")), _int(swap.get("amount_out"))
    if is_usd_stable(c0, usd_stables):
        stable_amt, tok, tok_amt, dec_s = a0, c1, a1, decimals(c0, dec_meta)
    elif is_usd_stable(c1, usd_stables):
        stable_amt, tok, tok_amt, dec_s = a1, c0, a0, decimals(c1, dec_meta)
    else:
        return None
    # stable-vs-stable (e.g. USDC/EURC FX) is not a tradable launchpad token
    if is_usd_stable(tok, usd_stables):
        return None
    if stable_amt == 0 or tok_amt == 0:
        return None
    dec_t = decimals(tok, dec_meta)
    if stable_amt > 0 and tok_amt < 0:
        side, token_qty, stable_value = "buy", -tok_amt / 10 ** dec_t, stable_amt / 10 ** dec_s
    elif stable_amt < 0 and tok_amt > 0:
        side, token_qty, stable_value = "sell", tok_amt / 10 ** dec_t, -stable_amt / 10 ** dec_s
    else:
        return None
    return {
        "wallet": (swap.get("wallet") or "").lower(), "token": tok, "pool": pool,
        "block": int(swap.get("block_number") or 0), "log_index": int(swap.get("log_index") or 0),
        "side": side, "token_qty": token_qty, "stable_value": stable_value,
    }


def reconstruct_legs(swaps: list, pools: dict, dec_meta: dict | None = None,
                     usd_stables: set | None = None) -> tuple[list[dict], int]:
    legs, skipped = [], 0
    for s in swaps:
        leg = leg_from_swap(s, pools, dec_meta, usd_stables)
        if leg is None:
            skipped += 1
        else:
            legs.append(leg)
    return legs, skipped


@dataclass
class ClosedTrade:
    wallet: str
    token: str
    qty: float
    cost: float
    proceeds: float
    realized: float
    exit_multiple: float
    entry_block: int
    exit_block: int


def closed_trades(legs: list[dict]) -> list[ClosedTrade]:
    """Average-cost accounting per (wallet, token); emits a closed trade per sell."""
    groups: dict[tuple, list] = {}
    for l in legs:
        groups.setdefault((l["wallet"], l["token"]), []).append(l)
    out: list[ClosedTrade] = []
    for (w, t), evs in groups.items():
        evs.sort(key=lambda x: (x["block"], x["log_index"]))
        qty = 0.0
        cost = 0.0
        entry_block = None
        for l in evs:
            if l["side"] == "buy":
                qty += l["token_qty"]
                cost += l["stable_value"]
                if entry_block is None:
                    entry_block = l["block"]
            else:
                if qty <= 0:
                    continue
                sell_qty = min(l["token_qty"], qty)
                frac = sell_qty / l["token_qty"]
                proceeds = l["stable_value"] * frac
                avg = cost / qty
                cogs = avg * sell_qty
                realized = proceeds - cogs
                exit_mult = (proceeds / cogs) if cogs > 0 else 0.0
                out.append(ClosedTrade(w, t, sell_qty, cogs, proceeds, realized, exit_mult,
                                       entry_block or l["block"], l["block"]))
                qty -= sell_qty
                cost -= cogs
                if qty <= 1e-18:
                    qty = 0.0
                    cost = 0.0
                    entry_block = None
    return out


@dataclass
class WalletPnl:
    wallet: str
    closed_trades: int
    wins: int
    win_rate: float
    realized_pnl: float
    avg_exit_multiple: float
    median_exit_multiple: float
    return_variance: float
    avg_holding_blocks: float
    tokens: int
    confidence: str
    unrealized_pnl: float = 0.0
    open_positions: int = 0


def wallet_pnl(trades: list[ClosedTrade], min_trades: int = 8) -> dict[str, WalletPnl]:
    by: dict[str, list[ClosedTrade]] = {}
    for t in trades:
        by.setdefault(t.wallet, []).append(t)
    out: dict[str, WalletPnl] = {}
    for w, ts in by.items():
        n = len(ts)
        rets = [t.exit_multiple for t in ts]
        wins = sum(1 for t in ts if t.realized > 0)
        mean = sum(rets) / n
        var = sum((r - mean) ** 2 for r in rets) / n if n > 1 else 0.0
        med = sorted(rets)[n // 2]
        out[w] = WalletPnl(
            wallet=w, closed_trades=n, wins=wins, win_rate=wins / n,
            realized_pnl=sum(t.realized for t in ts), avg_exit_multiple=mean,
            median_exit_multiple=med, return_variance=var,
            avg_holding_blocks=sum(t.exit_block - t.entry_block for t in ts) / n,
            tokens=len({t.token for t in ts}),
            confidence="ok" if n >= min_trades else "insuficiente",
        )
    return out


def collect_legs_pg(storage, limit: int | None = None) -> list[dict]:
    """Collect valued legs (bounded) for downstream risk/exit analysis."""
    conn = storage.pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pool_id, currency0, currency1 FROM pools_v4")
            pools = {pid.lower(): (c0, c1) for pid, c0, c1 in cur.fetchall()}
        legs: list[dict] = []
        pool_ids = list(pools)
        chunk = 300
        for ci in range(0, len(pool_ids), chunk):
            ch = pool_ids[ci:ci + chunk]
            with conn.cursor() as cc:
                cc.execute("SELECT s.trader, s.pool, s.block_number, s.log_index, s.amount_in, "
                           "s.amount_out FROM swaps s WHERE s.trader IS NOT NULL AND s.pool = ANY(%s)",
                           (ch,))
                rows = cc.fetchall()
            for w, p, b, i, ai, ao in rows:
                leg = leg_from_swap({"wallet": w, "pool": p, "block_number": b, "log_index": i,
                                     "amount_in": ai, "amount_out": ao}, pools)
                if leg:
                    legs.append(leg)
                    if limit and len(legs) >= limit:
                        return legs
        return legs
    finally:
        storage.pool.putconn(conn)


def _mark_open(positions: dict, last_price, agg: dict, counts: dict) -> None:
    """Mark still-open positions to market at the last observed pool price (survivorship fix)."""
    if not last_price or last_price <= 0:
        return
    for wallet, pos in positions.items():
        if pos[0] <= 1e-18:
            continue
        unreal = pos[0] * last_price - pos[1]
        a = agg.setdefault(wallet, [0, 0, 0.0, 0.0, 0.0, 0.0, set(), 0.0, 0])
        a[7] += unreal
        a[8] += 1
        counts["open_positions"] += 1


def _close_pool(first_entry: dict[str, int], pct_sum: dict[str, float], pct_cnt: dict[str, int]) -> None:
    arr = sorted(first_entry.items(), key=lambda x: x[1])
    m = len(arr)
    if m == 0:
        return
    for rank, (w, _b) in enumerate(arr):
        pct_sum[w] = pct_sum.get(w, 0.0) + (m - rank) / m
        pct_cnt[w] = pct_cnt.get(w, 0) + 1


def stream_pnl_pg(storage, min_trades: int = 8, limit: int | None = None,
                  collect_trades: bool = False) -> dict:
    """Stream swaps ordered by pool (memory-bounded on 3.8GB VPS) and aggregate PnL.

    Note: median_exit_multiple is not tracked in streaming mode (reported as the mean).
    Set collect_trades=True to also return the full ClosedTrade list (for walk-forward).
    """
    conn = storage.pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pool_id, currency0, currency1 FROM pools_v4")
            pools = {pid.lower(): (c0, c1) for pid, c0, c1 in cur.fetchall()}

        agg: dict[str, list] = {}
        pct_sum: dict[str, float] = {}
        pct_cnt: dict[str, int] = {}
        first_buy: dict[tuple, int] = {}
        trades: list[ClosedTrade] = []
        cur_pool = None
        positions: dict[str, list] = {}
        first_entry: dict[str, int] = {}
        last_price = None
        counts = {"swaps": 0, "legs": 0, "skipped": 0, "closed": 0,
                  "left_censored_sells": 0, "open_positions": 0}

        pool_ids = list(pools.keys())
        chunk_size = 300
        stop = False
        for ci in range(0, len(pool_ids), chunk_size):
            if stop:
                break
            chunk = pool_ids[ci:ci + chunk_size]
            with conn.cursor() as cc:
                cc.execute(
                    "SELECT s.trader, s.pool, s.block_number, s.log_index, "
                    "s.amount_in, s.amount_out FROM swaps s "
                    "WHERE s.trader IS NOT NULL AND s.pool = ANY(%s) "
                    "ORDER BY s.pool, s.block_number, s.log_index", (chunk,))
                rows = cc.fetchall()
            for w, pool, block, logi, ai, ao in rows:
                counts["swaps"] += 1
                if limit and limit > 0 and counts["swaps"] > limit:
                    stop = True
                    break
                p = (pool or "").lower()
                if p != cur_pool:
                    _close_pool(first_entry, pct_sum, pct_cnt)
                    _mark_open(positions, last_price, agg, counts)
                    positions, first_entry = {}, {}
                    last_price = None
                    cur_pool = p
                leg = leg_from_swap({"wallet": w, "pool": p, "block_number": block,
                                     "log_index": logi, "amount_in": ai, "amount_out": ao}, pools)
                if leg is None:
                    counts["skipped"] += 1
                    continue
                counts["legs"] += 1
                if leg["token_qty"] > 0:
                    last_price = leg["stable_value"] / leg["token_qty"]
                wallet = leg["wallet"]
                pos = positions.get(wallet)
                if leg["side"] == "buy":
                    if pos is None:
                        positions[wallet] = [leg["token_qty"], leg["stable_value"], leg["block"]]
                    else:
                        pos[0] += leg["token_qty"]
                        pos[1] += leg["stable_value"]
                    first_entry.setdefault(wallet, leg["block"])
                else:
                    if pos is None or pos[0] <= 0:
                        counts["left_censored_sells"] += 1
                        continue
                    sell_qty = min(leg["token_qty"], pos[0])
                    frac = sell_qty / leg["token_qty"]
                    proceeds = leg["stable_value"] * frac
                    cogs = (pos[1] / pos[0]) * sell_qty
                    realized = proceeds - cogs
                    mult = (proceeds / cogs) if cogs > 0 else 0.0
                    hold = leg["block"] - pos[2]
                    a = agg.setdefault(wallet, [0, 0, 0.0, 0.0, 0.0, 0.0, set(), 0.0, 0])
                    a[0] += 1
                    a[1] += 1 if realized > 0 else 0
                    a[2] += realized
                    a[3] += mult
                    a[4] += mult * mult
                    a[5] += hold
                    a[6].add(leg["token"])
                    counts["closed"] += 1
                    if collect_trades:
                        trades.append(ClosedTrade(wallet, leg["token"], sell_qty, cogs, proceeds,
                                                  realized, mult, pos[2], leg["block"]))
                    fb = (leg["token"], wallet)
                    if fb not in first_buy or pos[2] < first_buy[fb]:
                        first_buy[fb] = pos[2]
                    pos[1] = max(0.0, pos[1] - cogs)
                    pos[0] -= sell_qty
                    if pos[0] <= 1e-18:
                        positions.pop(wallet, None)
        _close_pool(first_entry, pct_sum, pct_cnt)
        _mark_open(positions, last_price, agg, counts)

        stats: dict[str, WalletPnl] = {}
        for w, a in agg.items():
            n = a[0]
            mean = a[3] / n if n else 0.0
            var = max(0.0, a[4] / n - mean * mean) if n else 0.0
            stats[w] = WalletPnl(w, n, a[1], (a[1] / n if n else 0.0), a[2], mean, mean, var,
                                 (a[5] / n if n else 0.0), len(a[6]),
                                 "ok" if n >= min_trades else "insuficiente",
                                 unrealized_pnl=a[7], open_positions=a[8])
        entry = {w: pct_sum[w] / pct_cnt[w] for w in pct_sum if pct_cnt.get(w)}
        return {"stats": stats, "entry": entry, "first_buy": first_buy, "trades": trades, **counts}
    finally:
        storage.pool.putconn(conn)


def build_report(swaps: list, pools: dict, dec_meta: dict | None = None, min_trades: int = 8):
    legs, skipped = reconstruct_legs(swaps, pools, dec_meta)
    trades = closed_trades(legs)
    stats = wallet_pnl(trades, min_trades=min_trades)
    entry = entry_timing_percentiles(trades)
    return {"legs": legs, "trades": trades, "stats": stats, "entry": entry,
            "swaps": len(swaps), "skipped": skipped}


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--storage", choices=["pg"], default="pg")
    ap.add_argument("--dsn", type=str)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--min-trades", type=int, default=8)
    ap.add_argument("--top", type=int, default=10)
    args = ap.parse_args()
    from .pg_storage import PostgresStorage
    storage = PostgresStorage(args.dsn)
    rep = stream_pnl_pg(storage, min_trades=args.min_trades, limit=args.limit)
    storage.close()
    stats = rep["stats"]
    active = [s for s in stats.values() if s.closed_trades > 0 or s.open_positions > 0]
    closed_n = sum(s.closed_trades for s in stats.values())
    closed_w = sum(round(s.win_rate * s.closed_trades) for s in stats.values())
    net_winners = sum(1 for s in active if (s.realized_pnl + s.unrealized_pnl) > 0)
    ranked = [s for s in stats.values() if s.confidence == "ok"]
    ranked.sort(key=lambda s: (s.win_rate, s.realized_pnl), reverse=True)
    print({"swaps": rep["swaps"], "legs": rep["legs"], "skipped": rep["skipped"],
           "closed_trades": rep["closed"], "left_censored_sells": rep.get("left_censored_sells", 0),
           "open_positions_marked": rep.get("open_positions", 0),
           "wallets": len(stats), "wallets_ok": len(ranked), "min_trades": args.min_trades,
           "closed_trade_win_rate": round(closed_w / closed_n, 4) if closed_n else None,
           "active_wallets": len(active),
           "net_win_rate_wallets": round(net_winners / len(active), 4) if active else None,
           "top": [{"wallet": s.wallet, "trades": s.closed_trades, "win_rate": round(s.win_rate, 3),
                    "avg_mult": round(s.avg_exit_multiple, 3), "pnl": round(s.realized_pnl, 3),
                    "unreal": round(s.unrealized_pnl, 3), "open": s.open_positions,
                    "var": round(s.return_variance, 3),
                    "entry_pct": round(rep["entry"].get(s.wallet, 0), 3),
                    "tokens": s.tokens} for s in ranked[:args.top]]})


def coordinated_clusters(first_buy: dict, min_wallets: int = 5) -> dict[str, int]:
    """Sybil proxy: cluster wallets that first-buy the same token in the same block.

    first_buy: {(token, wallet): first_entry_block}. Wallets sharing a (token, block)
    group of >= min_wallets are unioned. Returns {wallet: cluster_id} for grouped wallets.
    NOTE: proxy for coordinated entry, not proof of common funding (native funding not indexed).
    """
    groups: dict[tuple, list] = {}
    for (tok, w), b in first_buy.items():
        groups.setdefault((tok, b), []).append(w)
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for ws in groups.values():
        if len(ws) >= min_wallets:
            for w in ws:
                find(w)
            for w in ws[1:]:
                union(ws[0], w)
    roots: dict[str, int] = {}
    out: dict[str, int] = {}
    for w in list(parent):
        r = find(w)
        if r not in roots:
            roots[r] = len(roots)
        out[w] = roots[r]
    return out


def entry_timing_percentiles(trades: list[ClosedTrade]) -> dict[str, float]:
    """Per-token percentile of wallet entry timing (earliest entry -> ~1.0)."""
    first: dict[tuple, int] = {}
    for t in trades:
        k = (t.token, t.wallet)
        if k not in first or t.entry_block < first[k]:
            first[k] = t.entry_block
    by_token: dict[str, list] = {}
    for (tok, w), b in first.items():
        by_token.setdefault(tok, []).append((w, b))
    pct: dict[str, list] = {}
    for _tok, arr in by_token.items():
        arr.sort(key=lambda x: x[1])
        m = len(arr)
        for rank, (w, _b) in enumerate(arr):
            pct.setdefault(w, []).append((m - rank) / m)
    return {w: sum(v) / len(v) for w, v in pct.items()}


if __name__ == "__main__":
    main()
