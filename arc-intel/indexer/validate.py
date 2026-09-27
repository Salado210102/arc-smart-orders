"""Phase 2.2 (round 3) — PIT multi-fold walk-forward of the FULL composite score.

Design:
  - Build a `legs` table once (streaming, memory-bounded).
  - For each fold (split B, horizon H):
      * train stats ≤ B  (closed-trade realized/mult/wins via SQL window avg-cost; entry timing;
        shrinkage on win rate)
      * signal = composite score over train stats (PIT)
      * target = Δ total PnL over (B, B+H], total PnL = net cashflow + open qty*last_price
        (mark-to-market; no cost basis needed)
      * pairs = wallets with n>=min_trades in train AND present in test; pearson real vs shuffled
  - Sample sizes are reported per fold BEFORE correlations (`--samples-only`).
"""
from __future__ import annotations

import argparse

from .pnl import leg_from_swap
from .scoring import _percentiles, pearson, walk_forward

WEIGHTS = {"win_rate": 0.35, "exit_multiple": 0.25, "entry_timing": 0.20, "consistency": 0.20}
FOLDS = [(21600000, 300000), (21900000, 300000), (22200000, 300000), (22500000, 221550)]


def build_legs_pg(storage, chunk: int = 100, on_progress=None) -> int:
    conn = storage.pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pool_id, currency0, currency1 FROM pools_v4")
            pools = {pid.lower(): (c0, c1) for pid, c0, c1 in cur.fetchall()}
    finally:
        storage.pool.putconn(conn)
    storage.create_legs_table()
    pool_ids = list(pools)
    total = 0
    conn = storage.pool.getconn()
    try:
        for ci in range(0, len(pool_ids), chunk):
            ch = pool_ids[ci:ci + chunk]
            with conn.cursor() as cc:
                cc.execute("SELECT s.trader, s.pool, s.block_number, s.log_index, s.amount_in, "
                           "s.amount_out FROM swaps s WHERE s.trader IS NOT NULL AND s.pool = ANY(%s)",
                           (ch,))
                rows = cc.fetchall()
            batch = []
            for w, p, b, i, ai, ao in rows:
                leg = leg_from_swap({"wallet": w, "pool": p, "block_number": b, "log_index": i,
                                     "amount_in": ai, "amount_out": ao}, pools)
                if leg and leg["token_qty"] > 0 and leg["stable_value"] > 0:
                    batch.append((leg["wallet"], leg["token"], leg["pool"], leg["block"],
                                  leg["log_index"], leg["side"], leg["token_qty"],
                                  leg["stable_value"], leg["stable_value"] / leg["token_qty"]))
            total += storage.insert_legs(batch)
            if on_progress and (ci // chunk) % 20 == 0:
                on_progress(ci, len(pool_ids), total)
    finally:
        storage.pool.putconn(conn)
    return total


def pit_train_stats(storage, block: int) -> dict:
    """Per-wallet closed-trade stats with average-cost realized, strictly ≤ block."""
    conn = storage.pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "WITH o AS (SELECT wallet, pool, side, token_qty, stable_value, "
                "  sum(CASE WHEN side='buy' THEN token_qty ELSE 0 END) OVER w AS cbq, "
                "  sum(CASE WHEN side='buy' THEN stable_value ELSE 0 END) OVER w AS cbc "
                "  FROM legs WHERE block <= %s "
                "  WINDOW w AS (PARTITION BY wallet, pool ORDER BY block, log_index "
                "               ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING)) "
                "SELECT wallet, "
                " count(*) FILTER (WHERE cbq>0) AS n, "
                " sum(CASE WHEN cbq>0 AND (stable_value - cbc/cbq*token_qty)>0 THEN 1 ELSE 0 END) AS wins, "
                " sum(CASE WHEN cbq>0 THEN stable_value - cbc/cbq*token_qty ELSE 0 END) AS realized, "
                " sum(CASE WHEN cbq>0 AND cbc>0 THEN stable_value/(cbc/cbq*token_qty) ELSE 0 END) AS sum_mult, "
                " sum(CASE WHEN cbq>0 AND cbc>0 THEN power(stable_value/(cbc/cbq*token_qty),2) ELSE 0 END) AS sum_mult2 "
                "FROM o WHERE side='sell' GROUP BY wallet", (block,))
            stats = {}
            for w, n, wins, realized, sm, sm2 in cur.fetchall():
                n = int(n or 0)
                if n == 0:
                    continue
                mean = (sm or 0.0) / n
                var = max(0.0, (sm2 or 0.0) / n - mean * mean)
                stats[w] = {"n": n, "wins": int(wins or 0), "realized": realized or 0.0,
                            "avg_mult": mean, "variance": var}
            return stats
    finally:
        storage.pool.putconn(conn)


def first_buys(storage, block: int) -> dict:
    conn = storage.pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT wallet, token, min(block) FROM legs "
                        "WHERE block <= %s AND side='buy' GROUP BY wallet, token", (block,))
            return (cur.fetchall() or [])
    finally:
        storage.pool.putconn(conn)


def entry_timing(storage, block: int) -> dict:
    fb = first_buys(storage, block)
    by_token: dict[str, list] = {}
    for w, tok, b in fb:
        by_token.setdefault(tok, []).append((w, b))
    pct: dict[str, list] = {}
    for _tok, arr in by_token.items():
        arr.sort(key=lambda x: x[1])
        m = len(arr)
        for rank, (w, _b) in enumerate(arr):
            pct.setdefault(w, []).append((m - rank) / m)
    return {w: sum(v) / len(v) for w, v in pct.items()}


def total_pnl(storage, block: int) -> dict:
    conn = storage.pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT wallet, sum(CASE WHEN side='sell' THEN stable_value "
                        "ELSE -stable_value END) FROM legs WHERE block <= %s GROUP BY wallet", (block,))
            cash = {w: float(c or 0.0) for w, c in cur.fetchall()}
            cur.execute("SELECT wallet, pool, sum(CASE WHEN side='buy' THEN token_qty "
                        "ELSE -token_qty END) FROM legs WHERE block <= %s GROUP BY wallet, pool", (block,))
            qty = cur.fetchall()
            cur.execute("SELECT DISTINCT ON (pool) pool, price FROM legs WHERE block <= %s "
                        "ORDER BY pool, block DESC, log_index DESC", (block,))
            price = {p: float(pr or 0.0) for p, pr in cur.fetchall()}
    finally:
        storage.pool.putconn(conn)
    out = {w: c for w, c in cash.items()}
    for w, p, q in qty:
        val = float(q or 0.0) * price.get(p, 0.0)
        out[w] = out.get(w, 0.0) + val
    return out


def _snapshot(cash: dict, qty: dict, price: dict) -> dict:
    tot = dict(cash)
    for (w, p), q in qty.items():
        if q != 0.0:
            tot[w] = tot.get(w, 0.0) + q * price.get(p, 0.0)
    return tot


def total_pnl_boundaries(storage, boundaries) -> dict:
    """Single streaming pass over legs (ordered by block) snapshotting total PnL at each block."""
    bounds = sorted({int(b) for b in boundaries})
    conn = storage.pool.getconn()
    try:
        cash: dict[str, float] = {}
        qty: dict[tuple, float] = {}
        price: dict[str, float] = {}
        out: dict[int, dict] = {}
        idx = 0
        with conn.cursor(name="legs_stream") as sc:
            sc.itersize = 100000
            sc.execute("SELECT wallet, pool, side, token_qty, stable_value, block "
                       "FROM legs ORDER BY block, log_index")
            for w, p, side, tq, sv, b in sc:
                b = int(b)
                while idx < len(bounds) and b > bounds[idx]:
                    out[bounds[idx]] = _snapshot(cash, qty, price)
                    idx += 1
                tq = float(tq or 0.0)
                sv = float(sv or 0.0)
                if side == "buy":
                    cash[w] = cash.get(w, 0.0) - sv
                    k = (w, p)
                    qty[k] = qty.get(k, 0.0) + tq
                else:
                    cash[w] = cash.get(w, 0.0) + sv
                    k = (w, p)
                    qty[k] = qty.get(k, 0.0) - tq
                if tq > 0:
                    price[p] = sv / tq
                if abs(qty.get(k, 0.0)) < 1e-18:
                    qty.pop(k, None)
        while idx < len(bounds):
            out[bounds[idx]] = _snapshot(cash, qty, price)
            idx += 1
        return out
    finally:
        storage.pool.putconn(conn)


def test_wallets(storage, lo: int, hi: int) -> set:
    conn = storage.pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT wallet FROM legs WHERE block > %s AND block <= %s", (lo, hi))
            return {r[0] for r in cur.fetchall()}
    finally:
        storage.pool.putconn(conn)


def composite_signal(stats: dict, entry: dict, min_trades: int = 8) -> dict:
    wallets = [w for w, s in stats.items() if s["n"] >= min_trades]
    if not wallets:
        return {}
    comp = {
        "win_rate": _percentiles([_wilson(stats[w]["wins"], stats[w]["n"]) for w in wallets]),
        "exit_multiple": _percentiles([stats[w]["avg_mult"] for w in wallets]),
        "entry_timing": _percentiles([entry.get(w, 0.0) for w in wallets]),
        "consistency": _percentiles([1.0 / (1.0 + stats[w]["variance"]) for w in wallets]),
    }
    out = {}
    for i, w in enumerate(wallets):
        out[w] = sum(WEIGHTS[k] * comp[k][i] for k in WEIGHTS)
    return out


def _wilson(wins: int, n: int) -> float:
    from .shrinkage import wilson_lower_bound
    return wilson_lower_bound(wins, n)


def run_folds(storage, folds=None, min_trades: int = 8, samples_only: bool = False) -> list[dict]:
    folds = folds or FOLDS
    tp = None
    if not samples_only:
        bounds = sorted({s for s, _h in folds} | {s + h for s, h in folds})
        tp = total_pnl_boundaries(storage, bounds)
    results = []
    for k, (split, horizon) in enumerate(folds, 1):
        stats = pit_train_stats(storage, split)
        entry = entry_timing(storage, split)
        signal = composite_signal(stats, entry, min_trades)
        present = test_wallets(storage, split, split + horizon)
        if samples_only:
            res = {"fold": k, "split": split, "horizon": horizon,
                   "candidates": sum(1 for w in signal if w in present)}
            results.append(res)
            print(res, flush=True)
            continue
        base = tp[split]
        end = tp[split + horizon]
        pairs = [(signal[w], end.get(w, base.get(w, 0.0)) - base.get(w, 0.0))
                 for w in signal if w in present]
        wf = walk_forward(pairs, seed=k)
        res = {"fold": k, "split": split, "horizon": horizon, "candidates": len(pairs),
               "real_corr": wf.get("real_corr"), "shuffled_corr": wf.get("shuffled_corr"),
               "status": wf.get("status")}
        results.append(res)
        print(res, flush=True)
    return results


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", type=str)
    ap.add_argument("--build-legs", action="store_true")
    ap.add_argument("--samples-only", action="store_true")
    ap.add_argument("--min-trades", type=int, default=8)
    args = ap.parse_args()
    from .pg_storage import PostgresStorage
    storage = PostgresStorage(args.dsn)
    storage.migrate()
    if args.build_legs:
        n = build_legs_pg(storage, on_progress=lambda i, t, tot: print(f"legs {tot} ({i}/{t} pools)", flush=True))
        print(f"legs built: {n}")
    run_folds(storage, min_trades=args.min_trades, samples_only=args.samples_only)
    storage.close()


if __name__ == "__main__":
    main()
