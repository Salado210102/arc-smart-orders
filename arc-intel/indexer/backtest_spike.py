"""Backtest the discovery signals (esp. volume_spike) over indexed history.

Replays `legs` in block order through IncrementalState, collects discovery alerts, then measures
FORWARD returns (median, % positive, worst) at several horizons. This is a *quality* measurement so
we don't push buy alerts that don't work. Read-only.

Usage: python -m indexer.backtest_spike --dsn <dsn> --start 22500000
"""
from __future__ import annotations

import argparse
import statistics

from .stream_alerts import IncrementalState, load_creators

DISCOVERY = ("whale_buy", "graduation")
SECONDS_PER_BLOCK = 0.52


def _collect(storage, state, creators, start_block):
    """Stream legs in order; return discovery alerts + a price index for their tokens."""
    alerts = []
    tokens = set()
    conn = storage.pool.getconn()
    try:
        with conn.cursor(name="bt_legs") as sc:
            sc.itersize = 200000
            sc.execute(
                "SELECT wallet, token, block, side, token_qty, stable_value FROM legs "
                "WHERE block >= %s ORDER BY block, log_index", (int(start_block),))
            for w, t, b, s, q, sv in sc:
                for a in state.apply_leg({"wallet": w, "token": t, "block": b, "side": s,
                                          "token_qty": q, "stable_value": sv}, creators, emit=True):
                    if a.kind in DISCOVERY:
                        alerts.append((a.kind, a.token, int(b)))
                        tokens.add(a.token)
    finally:
        storage.pool.putconn(conn)
    return alerts, tokens


def _prices(storage, tokens):
    """token -> sorted [(block, price)] for the alert tokens only."""
    out: dict = {}
    if not tokens:
        return out
    conn = storage.pool.getconn()
    try:
        with conn.cursor(name="bt_px") as sc:
            sc.itersize = 200000
            sc.execute("SELECT token, block, price FROM legs WHERE token = ANY(%s) ORDER BY token, block",
                       (list(tokens),))
            for t, b, p in sc:
                out.setdefault(t, []).append((int(b), float(p or 0.0)))
    finally:
        storage.pool.putconn(conn)
    return out


def _return(series, alert_block, horizon_blocks):
    import bisect
    blocks = [x[0] for x in series]
    i = bisect.bisect_left(blocks, alert_block)
    if i >= len(series):
        return None
    p0 = series[i][1]
    if p0 <= 0:
        return None
    j = bisect.bisect_left(blocks, alert_block + horizon_blocks)
    if j >= len(series):
        return None
    return series[j][1] / p0 - 1.0


def run(dsn, start_block):
    from .pg_storage import PostgresStorage
    storage = PostgresStorage(dsn)
    state = IncrementalState()
    creators = load_creators(storage)
    print("replaying legs from block", start_block, "...", flush=True)
    alerts, tokens = _collect(storage, state, creators, start_block)
    print(f"discovery alerts: {len(alerts)} over {len(tokens)} tokens", flush=True)
    px = _prices(storage, tokens)
    horizons = {"1h": int(3600 / SECONDS_PER_BLOCK), "4h": int(14400 / SECONDS_PER_BLOCK),
                "24h": int(86400 / SECONDS_PER_BLOCK)}
    for kind in DISCOVERY:
        rows = [(t, b) for (k, t, b) in alerts if k == kind]
        if not rows:
            print(f"\n{kind}: no alerts")
            continue
        print(f"\n{kind}: n={len(rows)}")
        for hn, hb in horizons.items():
            rets = [r for r in (_return(px.get(t, []), b, hb) for (t, b) in rows) if r is not None]
            if not rets:
                print(f"  {hn}: no data")
                continue
            pos = sum(1 for r in rets if r > 0) / len(rets) * 100
            print(f"  {hn}: n={len(rets)} · mediana={statistics.median(rets)*100:+.1f}% · "
                  f"%positivos={pos:.0f}% · peor={min(rets)*100:+.1f}% · mejor={max(rets)*100:+.1f}%")
    storage.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", required=True)
    ap.add_argument("--start", type=int, default=22500000)
    args = ap.parse_args()
    run(args.dsn, args.start)


if __name__ == "__main__":
    main()
