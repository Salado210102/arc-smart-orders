"""Resolve the real swapper (tx.from) for indexed swaps via JSON-RPC batch.

Why: on Uniswap v4 the Swap event's `sender` (what we stored in `swaps.wallet`) is the
router/contract that called the PoolManager, NOT the trader. Correct wallet scoring needs
the transaction originator `tx.from`. This module is purely additive: it writes a
`tx_senders` table and leaves `swaps` and the running backfill untouched.

Usage:
    python -m indexer.resolve_senders --storage pg --dsn <dsn> --rpc <url> [--limit N] [--batch 100]
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request

DEFAULT_RPC = "https://rpc.mainnet.arc.io"


def _post(rpc_url: str, body, retries: int = 8, timeout: int = 60):
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(
            rpc_url, data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
        try:
            return json.load(urllib.request.urlopen(req, timeout=timeout))
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 403) and attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise
    if last:
        raise last


def resolve_batch(rpc_url: str, tx_hashes: list[str]) -> list[tuple]:
    """Return [(tx_hash, from_addr, to_addr, block_number)] for eth_getTransactionByHash."""
    body = [{"jsonrpc": "2.0", "id": i, "method": "eth_getTransactionByHash", "params": [t]}
            for i, t in enumerate(tx_hashes)]
    res = _post(rpc_url, body)
    by_id: dict[int, dict] = {}
    if isinstance(res, list):
        for item in res:
            if isinstance(item, dict) and item.get("id") is not None:
                by_id[item["id"]] = item.get("result")
    out = []
    for i, t in enumerate(tx_hashes):
        r = by_id.get(i) or {}
        bn = r.get("blockNumber")
        out.append((t, r.get("from"), r.get("to"), int(bn, 16) if bn else None))
    return out


def fetch_blocks(rpc_url: str, blocks: list[int]) -> dict[int, list[tuple]]:
    """Fetch full blocks in one JSON-RPC batch. Returns {block: [(tx,from,to), ...]}."""
    body = [{"jsonrpc": "2.0", "id": i, "method": "eth_getBlockByNumber",
             "params": [hex(int(b)), True]} for i, b in enumerate(blocks)]
    res = _post(rpc_url, body)
    out: dict[int, list[tuple]] = {}
    if isinstance(res, list):
        for item in res:
            if not isinstance(item, dict) or item.get("id") is None:
                continue
            b = blocks[item["id"]]
            r = item.get("result")
            if not r:
                continue  # error (e.g. rate limit): leave block unresolved for a later run
            out[b] = [(t.get("hash"), t.get("from"), t.get("to"))
                      for t in r.get("transactions", [])]
    return out


def run_blocks(storage, rpc_url: str = DEFAULT_RPC, batch: int = 5, limit: int | None = None,
               start: int | None = None, end: int | None = None, materialize_every: int = 0,
               max_attempts: int = 3, on_progress=None, fetcher=None) -> int:
    """Resolve tx.from per block. Idempotent/resumable; retries throttled (missing) blocks.

    Blocks not returned by the node (e.g. per-item rate-limit) are re-queued up to
    `max_attempts` passes, so a run converges instead of silently skipping.
    """
    fetcher = fetcher or (lambda url, blocks: fetch_blocks(url, blocks))
    done = storage.resolved_blocks()
    if (start is not None or end is not None) and hasattr(storage, "distinct_swap_blocks_range"):
        lo = int(start) if start is not None else 0
        hi = int(end) if end is not None else 2 ** 62
        candidates = storage.distinct_swap_blocks_range(lo, hi)
    else:
        candidates = storage.distinct_swap_blocks()
    pending = [b for b in candidates if b not in done]
    if limit:
        pending = pending[:limit]
    total_tx = 0
    can_mat = hasattr(storage, "materialize_traders_range")
    attempt = 0
    while pending and attempt < max_attempts:
        next_pending: list[int] = []
        for i, idx in enumerate(range(0, len(pending), batch)):
            chunk = pending[idx:idx + batch]
            blocks = fetcher(rpc_url, chunk)
            rows = [(tx, fr, to, b) for b, txs in blocks.items() for (tx, fr, to) in txs]
            storage.insert_tx_senders(rows)
            if blocks:
                storage.mark_blocks_resolved(list(blocks.keys()))
            total_tx += len(rows)
            next_pending.extend(b for b in chunk if b not in blocks)
            if can_mat and materialize_every and (i + 1) % materialize_every == 0 and blocks:
                storage.materialize_traders_range(min(chunk), max(chunk) + 1)
            if on_progress and i % 20 == 0:
                on_progress(idx + len(chunk), len(pending), total_tx)
        if on_progress:
            on_progress(len(pending), len(pending), total_tx)
        pending = next_pending
        attempt += 1
    if on_progress:
        on_progress(len(pending), len(pending), total_tx)
    return total_tx


def run(storage, rpc_url: str = DEFAULT_RPC, batch: int = 100, limit: int | None = None,
        on_progress=None, fetcher=None) -> int:
    """Resolve unresolved swap tx hashes in batches (per-tx mode). Idempotent/resumable."""
    fetcher = fetcher or (lambda url, hashes: resolve_batch(url, hashes))
    pending = [h for h in storage.distinct_swap_tx_hashes() if h not in storage.resolved_tx_hashes()]
    if limit:
        pending = pending[:limit]
    total = 0
    for start in range(0, len(pending), batch):
        chunk = pending[start:start + batch]
        rows = fetcher(rpc_url, chunk)
        total += storage.insert_tx_senders(rows)
        if on_progress and (start // batch) % 10 == 0:
            on_progress(total, len(pending))
    if on_progress:
        on_progress(total, len(pending))
    return total


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--storage", choices=["pg", "sqlite"], default="pg")
    ap.add_argument("--dsn", type=str)
    ap.add_argument("--db", type=str)
    ap.add_argument("--rpc", type=str, default=DEFAULT_RPC)
    ap.add_argument("--mode", choices=["block", "tx"], default="block",
                    help="block: one full-block call maps all txs (default, faster)")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--batch", type=int, default=None)
    ap.add_argument("--start-block", type=int, default=None)
    ap.add_argument("--end-block", type=int, default=None)
    ap.add_argument("--materialize-every", type=int, default=100,
                    help="materialize trader every N chunks (0=only at end)")
    ap.add_argument("--no-final-materialize", action="store_true",
                    help="skip the final materialization (for parallel workers)")
    ap.add_argument("--max-attempts", type=int, default=3,
                    help="retry passes over throttle-skipped blocks")
    args = ap.parse_args()
    if args.storage == "pg":
        from .pg_storage import PostgresStorage
        storage = PostgresStorage(args.dsn)
    else:
        from .storage import Storage
        storage = Storage(args.db or "arc_indexer.db")
    storage.migrate()
    if args.mode == "block":
        batch = args.batch or 5
        n = run_blocks(storage, args.rpc, batch=batch, limit=args.limit,
                       start=args.start_block, end=args.end_block,
                       materialize_every=args.materialize_every,
                       max_attempts=args.max_attempts,
                       on_progress=lambda done, total, txs: print(
                           f"blocks {done}/{total} txs={txs}", flush=True))
    else:
        batch = args.batch or 10
        n = run(storage, args.rpc, batch=batch, limit=args.limit,
                on_progress=lambda done, total: print(f"resolved {done}/{total}", flush=True))
    print(f"done resolved {n}")
    if args.storage == "pg" and not args.no_final_materialize:
        bounds = storage.swap_block_bounds()
        if bounds:
            mats = storage.materialize_traders_batched(
                bounds[0], bounds[1] + 1, step=50000,
                on_progress=lambda lo, hi, tot: print(f"materialized {tot} through block {hi}", flush=True))
            print(f"materialized traders {mats}")
    storage.close()


if __name__ == "__main__":
    main()
