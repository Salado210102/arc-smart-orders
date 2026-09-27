"""Live ingestion: keep `swaps` current (IndexerService/backfill) and APPEND new `legs`
incrementally via a block cursor (`legs_cursor`), without rebuilding from scratch.
"""
from __future__ import annotations

import argparse
import time

from .pnl import leg_from_swap


def append_legs_pg(storage, upto_block: int | None = None, chunk: int = 200,
                   on_progress=None) -> int:
    """Append legs for swaps in (legs_cursor, upto_block]; advance legs_cursor."""
    cursor = int(storage.get_meta("legs_cursor", "0") or 0)
    conn = storage.pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pool_id, currency0, currency1 FROM pools_v4")
            pools = {pid.lower(): (c0, c1) for pid, c0, c1 in cur.fetchall()}
            if upto_block is None:
                cur.execute("SELECT max(block_number) FROM swaps")
                upto_block = int(cur.fetchone()[0] or 0)
    finally:
        storage.pool.putconn(conn)
    if cursor == 0:
        # bootstrap: if legs already exist, start after the last appended block (no dup);
        # otherwise start just before the earliest swap.
        conn = storage.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT max(block) FROM legs")
                mx = cur.fetchone()[0]
                if mx is None:
                    cur.execute("SELECT min(block_number) FROM swaps")
                    cursor = int(cur.fetchone()[0] or 0) - 1
                else:
                    cursor = int(mx)
        finally:
            storage.pool.putconn(conn)
    pool_ids = list(pools)
    total = 0
    conn = storage.pool.getconn()
    try:
        for ci in range(0, len(pool_ids), chunk):
            ch = pool_ids[ci:ci + chunk]
            with conn.cursor() as cc:
                cc.execute("SELECT s.trader, s.pool, s.block_number, s.log_index, s.amount_in, "
                           "s.amount_out FROM swaps s WHERE s.trader IS NOT NULL "
                           "AND s.block_number > %s AND s.block_number <= %s AND s.pool = ANY(%s)",
                           (cursor, upto_block, ch))
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
            if on_progress and (ci // chunk) % 50 == 0:
                on_progress(ci, len(pool_ids), total)
    finally:
        storage.pool.putconn(conn)
    storage.set_meta("legs_cursor", str(int(upto_block)))
    return total


def ingest_new(storage, source, head: int | None = None, chunk: int = 2000) -> dict:
    """One live cycle: backfill new swaps, resolve tx.from, materialize, append legs."""
    from .backfill import backfill_v4_run
    from .resolve_senders import run_blocks

    if head is None:
        head = source.head()
    conn = storage.pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT max(block_number) FROM swaps")
            start = int(cur.fetchone()[0] or 0)
    finally:
        storage.pool.putconn(conn)
    b = backfill_v4_run(storage, source, start=start, end=head, chunk=chunk, job="live_v4",
                        progress=False)
    run_blocks(storage, source.rpc_url, batch=200, start=start, end=head,
               materialize_every=0, max_attempts=3)
    mats = storage.materialize_traders_batched(start, head + 1, step=100000)
    added = append_legs_pg(storage, upto_block=head)
    return {"head": head, "new_swaps": b.get("swaps"), "materialized": mats, "new_legs": added}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", type=str)
    ap.add_argument("--append-only", action="store_true", help="only append legs (no RPC)")
    ap.add_argument("--upto", type=int, default=None)
    args = ap.parse_args()
    from .pg_storage import PostgresStorage
    storage = PostgresStorage(args.dsn)
    storage.migrate()
    if args.append_only:
        n = append_legs_pg(storage, upto_block=args.upto,
                           on_progress=lambda i, t, tot: print(f"legs {tot} ({i}/{t})", flush=True))
        print({"mode": "append-only", "new_legs": n})
    else:
        from .config import load_config
        from .sources import RpcEventSource
        cfg = load_config()
        source = RpcEventSource(cfg.rpc_url, cfg.launchpads)
        print(ingest_new(storage, source))
    storage.close()


if __name__ == "__main__":
    main()
