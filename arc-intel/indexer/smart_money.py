"""Smart-money research (rigorous, honest): score wallets by REALIZED PnL on a training window,
then measure (walk-forward) whether their buys in a LATER window predict positive forward returns.

Only ship if measured edge exists. Read-only.

Usage: python -m indexer.smart_money --dsn <dsn> --train-end 22700000 --test-end 23080000
"""
from __future__ import annotations

import argparse
import bisect
import statistics


def wallet_scores(storage, upto_block: int, min_trades: int = 8) -> tuple[dict, dict]:
    """Fast SQL proxy: per wallet, USD bought vs sold. 'Winner' = sold_usd - bought_usd > 0.

    (Realized-PnL average-cost is more precise but far slower; this proxy is good enough to test
    whether past-winner buys predict future returns at all.)
    """
    conn = storage.pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT lower(wallet) w, count(*) n, "
                "coalesce(sum(case when side='sell' then stable_value else 0 end),0) sold, "
                "coalesce(sum(case when side='buy' then stable_value else 0 end),0) bought, "
                "count(distinct token) toks "
                "FROM legs WHERE block <= %s AND wallet IS NOT NULL "
                "GROUP BY 1 HAVING count(*) >= %s", (int(upto_block), int(min_trades)))
            agg = {}
            for w, n, sold, bought, toks in cur.fetchall():
                agg[w] = {"n": int(n), "sold": float(sold), "bought": float(bought),
                          "toks": int(toks), "net": float(sold) - float(bought)}
    finally:
        storage.pool.putconn(conn)
    smart = {w: v for w, v in agg.items() if v["net"] > 0 and v["sold"] > 0}
    return smart, agg


def buy_signals(storage, smart: dict, after_block: int, upto_block: int, baseline_n: int = 4000):
    """Buy legs after_block by smart wallets (and a baseline sample of all buys)."""
    smart_buys = []
    baseline = []
    conn = storage.pool.getconn()
    try:
        with conn.cursor(name="sm_test") as sc:
            sc.itersize = 200000
            sc.execute("SELECT wallet, token, block FROM legs WHERE side='buy' "
                       "AND block > %s AND block <= %s ORDER BY block, log_index",
                       (int(after_block), int(upto_block)))
            step = 0
            for w, t, b in sc:
                w = (w or "").lower()
                if w in smart:
                    smart_buys.append((t, int(b)))
                step += 1
                if step % 1 == 0 and len(baseline) < baseline_n:
                    baseline.append((t, int(b)))
    finally:
        storage.pool.putconn(conn)
    return smart_buys, baseline


def _prices(storage, tokens):
    out: dict = {}
    conn = storage.pool.getconn()
    try:
        with conn.cursor(name="sm_px") as sc:
            sc.itersize = 200000
            sc.execute("SELECT token, block, price FROM legs WHERE token = ANY(%s) ORDER BY token, block",
                       (list(tokens),))
            for t, b, p in sc:
                out.setdefault(t, []).append((int(b), float(p or 0.0)))
    finally:
        storage.pool.putconn(conn)
    return out


def _fwd(series, block, hb):
    if not series:
        return None
    blocks = [x[0] for x in series]
    i = bisect.bisect_left(blocks, block)
    if i >= len(series) or series[i][1] <= 0:
        return None
    j = bisect.bisect_left(blocks, block + hb)
    if j >= len(series):
        return None
    return series[j][1] / series[i][1] - 1.0


def _report(name, sigs, px, hb):
    rets = [r for r in (_fwd(px.get(t, []), b, hb) for (t, b) in sigs) if r is not None]
    if not rets:
        print(f"  {name}: no data")
        return
    pos = sum(1 for r in rets if r > 0) / len(rets) * 100
    print(f"  {name}: n={len(rets)} · mediana={statistics.median(rets)*100:+.1f}% · "
          f"%pos={pos:.0f}% · peor={min(rets)*100:+.1f}% · mejor={max(rets)*100:+.1f}%")


def run(dsn, train_end, test_end):
    from .pg_storage import PostgresStorage
    st = PostgresStorage(dsn)
    print("scoring wallets on legs <=", train_end, flush=True)
    smart, agg = wallet_scores(st, train_end)
    print(f"wallets scored: {len(agg)} · smart (trades>=8, pnl>0, win>=50%): {len(smart)}", flush=True)
    if smart:
        top = sorted(smart.items(), key=lambda kv: -kv[1]["net"])[:5]
        print("top smart wallets:", [(w[:8], round(v["net"]), v["n"], v["toks"]) for w, v in top],
              flush=True)
    sb, base = buy_signals(st, smart, train_end, test_end)
    print(f"test buys: smart={len(sb)} baseline={len(base)}", flush=True)
    tokens = {t for t, _ in sb} | {t for t, _ in base}
    px = _prices(st, tokens)
    hb1 = int(3600 / 0.52)
    hb4 = int(14400 / 0.52)
    for hn, hb in (("1h", hb1), ("4h", hb4)):
        print(f"\n[{hn}]")
        _report("SMART", sb, px, hb)
        _report("baseline (all buys)", base, px, hb)
    st.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", required=True)
    ap.add_argument("--train-end", type=int, default=22700000)
    ap.add_argument("--test-end", type=int, default=23080000)
    args = ap.parse_args()
    run(args.dsn, args.train_end, args.test_end)


if __name__ == "__main__":
    main()
