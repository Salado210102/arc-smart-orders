"""Bounded, resumable backfill + Transfer indexing (read-only).

Error handling separates causes explicitly:
  - rate limit / 403 / 429  -> exponential-backoff RETRY (never split)
  - result-limit (node says range exceeds max results) -> SPLIT
  - exhausted retries       -> recorded in `data_gaps` (never silently dropped)
"""
from __future__ import annotations

import argparse
import time

from .config import (
    POOLMANAGER_V4,
    TRANSFER_TOPIC0,
    V4_DONATE_TOPIC0,
    V4_INITIALIZE_TOPIC0,
    V4_MODIFYLIQUIDITY_TOPIC0,
    V4_SWAP_TOPIC0,
    load_config,
)
from .models import PoolV4Row, RawEvent, SwapRow, TokenTransferRow, V4EventRow, V4LiquidityRow
from .processor import decode_donate, decode_initialize, decode_v4_swap
from .service import setup_logging
from .sources import RpcEventSource

RATE_LIMIT_HINTS = ("rate limit", "too many requests", "429", "403", "forbidden")
RESULT_LIMIT_HINTS = ("max allowed range", "max results", "exceeds", "more than")


def classify_rpc_error(message: str) -> str:
    m = message.lower()
    if any(h in m for h in RATE_LIMIT_HINTS):
        return "rate_limit"
    if any(h in m for h in RESULT_LIMIT_HINTS):
        return "result_limit"
    return "other"


def _ev(log: dict, kind: str, dex=None, with_ts=None) -> RawEvent:
    return RawEvent(
        source="rpc", kind=kind, tx_hash=log["transactionHash"],
        log_index=int(log["logIndex"], 16), block_number=int(log["blockNumber"], 16),
        block_time=with_ts, address=log["address"].lower(),
        topics=list(log.get("topics", [])), data=log.get("data", "0x"), dex=dex,
    )


def _fetch_topic_logs(source, address, topic, a, b, job, storage, min_size=50,
                      max_retries=6, stats=None):
    attempt = 0
    while True:
        try:
            return source._logs({"address": address, "topics": [topic],
                                 "fromBlock": hex(a), "toBlock": hex(b)})
        except Exception as e:
            kind = classify_rpc_error(str(e))
            if kind == "result_limit":
                if (b - a + 1) <= min_size:
                    storage.insert_gap(job, a, b, "result_limit", attempt + 1, int(time.time()))
                    if stats is not None:
                        stats["gaps_result_limit"] = stats.get("gaps_result_limit", 0) + 1
                    return []
                mid = (a + b) // 2
                return (_fetch_topic_logs(source, address, topic, a, mid, job, storage, min_size, max_retries, stats)
                        + _fetch_topic_logs(source, address, topic, mid + 1, b, job, storage, min_size, max_retries, stats))
            # rate_limit / other -> backoff retry on the SAME range (no split)
            if attempt >= max_retries:
                storage.insert_gap(job, a, b, kind, attempt + 1, int(time.time()))
                if stats is not None:
                    stats[f"gaps_{kind}"] = stats.get(f"gaps_{kind}", 0) + 1
                return []
            if stats is not None:
                stats["retries"] = stats.get("retries", 0) + 1
            time.sleep(min(30, 2 ** attempt))
            attempt += 1


def resolve_launch_block(source: RpcEventSource, target_ts: int) -> int:
    lo, hi = 0, source.head()
    while lo < hi:
        mid = (lo + hi) // 2
        b = source._rpc("eth_getBlockByNumber", [hex(mid), False])
        t = int(b["timestamp"], 16) if b else None
        if t is not None and t < target_ts:
            lo = mid + 1
        else:
            hi = mid
    return lo


def backfill_v4_run(storage, source, start, end, chunk=2000, min_size=50, job="backfill_v4",
                    progress=True, max_retries=6):
    ck = storage.get_meta(f"{job}_cursor")
    cur = int(ck) + 1 if ck is not None else start
    stats = {"pools": 0, "swaps": 0, "donates": 0, "retries": 0,
             "gaps_result_limit": 0, "gaps_rate_limit": 0, "gaps_other": 0, "blocks": 0}
    t0 = time.time()
    for a in range(cur, end + 1, chunk):
        b = min(a + chunk - 1, end)
        pool_rows, swap_rows, don_rows = [], [], []
        for log in _fetch_topic_logs(source, POOLMANAGER_V4, V4_INITIALIZE_TOPIC0, a, b, job, storage, min_size, max_retries, stats):
            d = decode_initialize(_ev(log, "pool_init"))
            if d:
                pool_rows.append(PoolV4Row(pool_id=d["pool_id"], currency0=d["currency0"],
                                           currency1=d["currency1"], fee=d.get("fee"),
                                           tick_spacing=d.get("tick_spacing"), hooks=d.get("hooks"),
                                           sqrt_price_x96=d.get("sqrt_price_x96"), tick=d.get("tick"),
                                           block_number=int(log["blockNumber"], 16), ts=None))
        for log in _fetch_topic_logs(source, POOLMANAGER_V4, V4_SWAP_TOPIC0, a, b, job, storage, min_size, max_retries, stats):
            d = decode_v4_swap(_ev(log, "dex_swap", dex="uniswap_v4"))
            if d:
                swap_rows.append(SwapRow(tx_hash=log["transactionHash"], log_index=int(log["logIndex"], 16),
                                         block_number=int(log["blockNumber"], 16), ts=None, token=None,
                                         wallet=d.get("sender"), side="unknown", amount_in=d.get("amount0"),
                                         amount_out=d.get("amount1"), price_implied=None, dex="uniswap_v4",
                                         pool=d.get("pool_id")))
        for log in _fetch_topic_logs(source, POOLMANAGER_V4, V4_DONATE_TOPIC0, a, b, job, storage, min_size, max_retries, stats):
            d = decode_donate(_ev(log, "v4_donate"))
            if d:
                don_rows.append(V4EventRow(kind="Donate", tx_hash=log["transactionHash"],
                                           log_index=int(log["logIndex"], 16), pool_id=d["pool_id"],
                                           sender=d["sender"], amount0=d["amount0"], amount1=d["amount1"],
                                           block_number=int(log["blockNumber"], 16), ts=None))
        stats["pools"] += storage.insert_pool_v4_rows(pool_rows)
        stats["swaps"] += storage.insert_swaps(swap_rows)
        stats["donates"] += storage.insert_v4_events(don_rows)
        storage.set_meta(f"{job}_cursor", str(b))
        stats["blocks"] += b - a + 1
        if progress:
            dt = time.time() - t0
            rows = stats["pools"] + stats["swaps"] + stats["donates"]
            gaps = stats["gaps_result_limit"] + stats["gaps_rate_limit"] + stats["gaps_other"]
            print(f"  blocks {a}-{b} | pools={stats['pools']} swaps={stats['swaps']} donates={stats['donates']} "
                  f"| {rows} rows in {dt:.0f}s ({rows/dt:.0f} rows/s, {stats['blocks']/dt:.0f} blk/s) "
                  f"retries={stats['retries']} gaps={gaps}", flush=True)
    dt = time.time() - t0
    rows = stats["pools"] + stats["swaps"] + stats["donates"]
    stats.update({"seconds": round(dt, 1), "rows": rows,
                  "rows_per_sec": round(rows / dt, 1) if dt else None,
                  "blocks_per_sec": round(stats["blocks"] / dt, 1) if dt else None,
                  "gaps_pending": len(storage.list_gaps(job))})
    return stats


def backfill_liquidity_run(storage, source, start, end, chunk=2000, job="backfill_liq",
                           progress=True, max_retries=6):
    """Index Uniswap v4 ModifyLiquidity events (liquidity add/remove)."""
    from .processor import decode_modify_liquidity
    ck = storage.get_meta(f"{job}_cursor")
    cur = int(ck) + 1 if ck is not None else start
    stats = {"liq": 0, "retries": 0, "gaps_result_limit": 0, "gaps_rate_limit": 0,
             "gaps_other": 0, "blocks": 0}
    t0 = time.time()
    for a in range(cur, end + 1, chunk):
        b = min(a + chunk - 1, end)
        rows = []
        for log in _fetch_topic_logs(source, POOLMANAGER_V4, V4_MODIFYLIQUIDITY_TOPIC0, a, b, job,
                                     storage, 50, max_retries, stats):
            d = decode_modify_liquidity(_ev(log, "v4_liq"))
            if d:
                rows.append(V4LiquidityRow(tx_hash=log["transactionHash"],
                                           log_index=int(log["logIndex"], 16), pool_id=d["pool_id"],
                                           sender=d["sender"], tick_lower=d["tick_lower"],
                                           tick_upper=d["tick_upper"],
                                           liquidity_delta=d["liquidity_delta"], salt=d["salt"],
                                           block_number=int(log["blockNumber"], 16), ts=None))
        stats["liq"] += storage.insert_v4_liquidity_rows(rows)
        storage.set_meta(f"{job}_cursor", str(b))
        stats["blocks"] += b - a + 1
        if progress:
            dt = time.time() - t0
            rate = stats["blocks"] / dt if dt > 0 else 0.0
            print(f"  blocks {a}-{b} | liq={stats['liq']} | {rate:.0f} blk/s "
                  f"retries={stats['retries']}", flush=True)
    stats["seconds"] = round(time.time() - t0, 1)
    return stats


def backfill_launchpad_run(storage, source, start, end, chunk=2000, job="backfill_launchpad",
                           progress=True, max_retries=6):
    """Index launchpad events (Argus TokenCreated/PartsDeployed/CurveOpened).

    TokenCreated populates tokens(name/symbol/creator/pool_id). created_ts is approximated
    as block*0.52s (block_time left NULL on this path for speed); accurate enough for the
    insider filter, flagged wherever used.
    """
    from .processor import EventProcessor
    proc = EventProcessor(storage, source.launchpads)
    ck = storage.get_meta(f"{job}_cursor")
    cur = int(ck) + 1 if ck is not None else start
    stats = {"tokens": 0, "events": 0, "retries": 0,
             "gaps_result_limit": 0, "gaps_rate_limit": 0, "gaps_other": 0, "blocks": 0}
    t0 = time.time()
    for a in range(cur, end + 1, chunk):
        b = min(a + chunk - 1, end)
        for lp in source.launchpads:
            for topic in lp.topic_map:
                for log in _fetch_topic_logs(source, lp.address, topic, a, b, job, storage,
                                             50, max_retries, stats):
                    ts = int(int(log["blockNumber"], 16) * 0.52)
                    ev = _ev(log, "launchpad", with_ts=ts)
                    ev.launchpad = lp.name
                    res = proc.process(ev)
                    stats["tokens"] += res.tokens
                    stats["events"] += res.launchpad_events
        storage.set_meta(f"{job}_cursor", str(b))
        stats["blocks"] += b - a + 1
        if progress:
            dt = time.time() - t0
            rate = stats["blocks"] / dt if dt > 0 else 0.0
            print(f"  blocks {a}-{b} | tokens={stats['tokens']} events={stats['events']} "
                  f"| {rate:.0f} blk/s retries={stats['retries']}", flush=True)
    stats["seconds"] = round(time.time() - t0, 1)
    stats["gaps_pending"] = len(storage.list_gaps(job))
    return stats


def index_token_transfers(storage, source, token, start, end, chunk=2000, with_ts=True, job="transfers"):
    n = 0
    stats = {}
    for a in range(start, end + 1, chunk):
        b = min(a + chunk - 1, end)
        rows = []
        for log in _fetch_topic_logs(source, token, TRANSFER_TOPIC0, a, b, job, storage, stats=stats):
            ts = source._block_time(int(log["blockNumber"], 16)) if with_ts else None
            ev = _ev(log, "token_transfer", with_ts=ts)
            if len(ev.topics) < 3:
                continue
            value = str(int(ev.data, 16)) if ev.data and ev.data != "0x" else "0"
            rows.append(TokenTransferRow(
                tx_hash=ev.tx_hash, log_index=ev.log_index, token=ev.address,
                from_addr="0x" + ev.topics[1][-40:].lower(), to_addr="0x" + ev.topics[2][-40:].lower(),
                value=value, block_number=ev.block_number, ts=ts))
        n += storage.insert_transfers(rows)
    return n


def _make_storage(args):
    if args.storage == "pg":
        from .pg_storage import PostgresStorage
        return PostgresStorage(args.dsn)
    from .storage import Storage
    return Storage(args.db or load_config().db_path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["launch", "v4", "launchpad", "liquidity", "transfers"], required=True)
    ap.add_argument("--storage", choices=["sqlite", "pg"], default="sqlite")
    ap.add_argument("--dsn", type=str)
    ap.add_argument("--start", type=int)
    ap.add_argument("--end", type=int)
    ap.add_argument("--chunk", type=int, default=2000)
    ap.add_argument("--token", type=str)
    ap.add_argument("--job", type=str, default="backfill_v4")
    ap.add_argument("--ts", type=int, default=1789516800)
    ap.add_argument("--db", type=str)
    args = ap.parse_args()

    cfg = load_config()
    logger = setup_logging(cfg.log_path)
    storage = _make_storage(args)
    storage.migrate()
    source = RpcEventSource(cfg.rpc_url, cfg.launchpads)

    if args.mode == "launch":
        print({"launch_block": resolve_launch_block(source, args.ts)})
        return
    if args.mode == "v4":
        stats = backfill_v4_run(storage, source, args.start, args.end, args.chunk, job=args.job)
        print({"mode": "v4", "range": [args.start, args.end], **stats})
        return
    if args.mode == "launchpad":
        stats = backfill_launchpad_run(storage, source, args.start, args.end, args.chunk, job=args.job)
        print({"mode": "launchpad", "range": [args.start, args.end], **stats})
        storage.close()
        return
    if args.mode == "liquidity":
        stats = backfill_liquidity_run(storage, source, args.start, args.end, args.chunk, job=args.job)
        print({"mode": "liquidity", "range": [args.start, args.end], **stats})
        storage.close()
        return
    if args.mode == "transfers":
        n = index_token_transfers(storage, source, args.token, args.start, args.end, args.chunk)
        print({"mode": "transfers", "token": args.token, "processed": n,
               "inferred": storage.query_dev_buys_inferred()[:5]})
    storage.close()


if __name__ == "__main__":
    main()
