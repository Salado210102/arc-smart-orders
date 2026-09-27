"""CLI entrypoint for the Arc indexer (read-only)."""
from __future__ import annotations

import argparse
import json

from .config import load_config
from .processor import EventProcessor
from .service import IndexerService, setup_logging
from .sources import RpcEventSource
from .storage import Storage


def make_rpc_token_resolver(rpc_url: str):
    import json as _json
    import urllib.request

    cache: dict[str, tuple[str, str] | None] = {}

    def call(to: str, data: str) -> str:
        body = _json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                            "params": [{"to": to, "data": data}, "latest"]}).encode()
        req = urllib.request.Request(rpc_url, data=body, headers={
            "content-type": "application/json",
            "accept": "application/json",
            "User-Agent": "arc-intel-indexer/0.1 (read-only)",
        })
        with urllib.request.urlopen(req, timeout=20) as resp:
            return _json.loads(resp.read().decode()).get("result", "0x")

    def resolver(pool: str):
        if pool in cache:
            return cache[pool]
        try:
            t0 = "0x" + call(pool, "0x0dfe1681")[-40:]
            t1 = "0x" + call(pool, "0xd21220a7")[-40:]
            cache[pool] = (t0.lower(), t1.lower())
        except Exception:
            cache[pool] = None
        return cache[pool]

    return resolver


def main() -> None:
    ap = argparse.ArgumentParser(description="Arc read-only event indexer (Phase 1).")
    ap.add_argument("--start", type=int, required=True, help="start block")
    ap.add_argument("--ticks", type=int, default=1, help="number of polling ticks")
    ap.add_argument("--range", type=int, default=200, help="max blocks per tick")
    ap.add_argument("--db", type=str, default=None)
    ap.add_argument("--log", type=str, default=None)
    ap.add_argument("--resolve-tokens", action="store_true", help="resolve pool token0/token1 via RPC")
    ap.add_argument("--max-errors", type=int, default=6)
    ap.add_argument("--event-delay-ms", type=int, default=0, help="test hook: delay per event")
    ap.add_argument("--report", action="store_true", help="print counts and samples as JSON")
    args = ap.parse_args()

    cfg = load_config()
    db = args.db or cfg.db_path
    log = args.log or cfg.log_path
    logger = setup_logging(log)
    storage = Storage(db)
    storage.migrate()
    source = RpcEventSource(cfg.rpc_url, cfg.launchpads)
    resolver = make_rpc_token_resolver(cfg.rpc_url) if args.resolve_tokens else None
    processor = EventProcessor(storage, cfg.launchpads, token_resolver=resolver)
    service = IndexerService(source, processor, storage, logger,
                             poll_seconds=cfg.poll_seconds, max_range_blocks=args.range,
                             event_delay_seconds=args.event_delay_ms / 1000.0)
    service.run(start_block=args.start, max_ticks=args.ticks, stop_when_synced=True,
                max_consecutive_errors=args.max_errors)

    if args.report:
        out = {
            "db": db,
            "counts": storage.counts(),
            "dev_buys_inferred_sample": storage.query_dev_buys_inferred(86400, 5),
            "processed_total": service.processed_total,
            "duplicates_total": service.duplicates_total,
            "samples": {t: storage.sample(t, 3) for t in ("tokens", "swaps", "dev_buys", "launchpad_events")},
        }
        print(json.dumps(out, indent=2, default=str))
    storage.close()


if __name__ == "__main__":
    main()
