"""Launchpad activity ranking (hook-implementation clustering), runnable on a schedule.

Because each Argus token has its own hook clone, we cluster hooks by their on-chain bytecode
(implementation) to approximate 'launchpad implementations', and rank them by recent swaps.
Results are persisted with a run timestamp so the ranking can be tracked over time.

Usage: python -m indexer.launchpad_rank --dsn <dsn> [--window 200000] [--top 60]
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request

DEFAULT_RPC = "https://rpc.mainnet.arc.io"


def _rpc(rpc_url: str, method: str, params: list, retries: int = 8):
    for a in range(retries):
        req = urllib.request.Request(
            rpc_url, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                                      "params": params}).encode(),
            headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
        try:
            return json.load(urllib.request.urlopen(req, timeout=30)).get("result")
        except urllib.error.HTTPError as e:
            if e.code in (429, 403) and a < retries - 1:
                time.sleep(2 * (a + 1))
                continue
            raise


def impl_key(code: str) -> str:
    if not code or code == "0x":
        return "empty"
    h = code[2:]
    if h.startswith("363d3d373d3d3d363d73") and len(h) >= 60:  # EIP-1167 minimal proxy
        return "proxy:" + h[20:60]
    return "code:" + h[:40]


def compute_ranking(storage, rpc_url: str = DEFAULT_RPC, window_blocks: int = 200000,
                    top_hooks: int = 60) -> list:
    conn = storage.pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT max(block) FROM legs")
            head = int(cur.fetchone()[0] or 0)
            cur.execute(
                "SELECT coalesce(p.hooks,'0x0') hook, count(*) swaps, sum(l.stable_value) vol "
                "FROM pools_v4 p JOIN legs l ON l.pool=p.pool_id "
                "WHERE l.block > %s AND coalesce(p.hooks,'0x0') <> %s "
                "GROUP BY 1 ORDER BY swaps DESC LIMIT %s",
                (head - int(window_blocks), "0x" + "0" * 40, int(top_hooks)))
            hooks = cur.fetchall()
    finally:
        storage.pool.putconn(conn)
    groups: dict = {}
    for hook, swaps, vol in hooks:
        key = impl_key(_rpc(rpc_url, "eth_getCode", [hook, "latest"]))
        g = groups.setdefault(key, {"impl": key, "hooks": 0, "swaps": 0, "volume": 0.0,
                                    "sample_hook": hook})
        g["hooks"] += 1
        g["swaps"] += int(swaps)
        g["volume"] += float(vol or 0)
    return sorted(groups.values(), key=lambda g: g["swaps"], reverse=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", type=str)
    ap.add_argument("--rpc", type=str, default=DEFAULT_RPC)
    ap.add_argument("--window", type=int, default=200000)
    ap.add_argument("--top", type=int, default=60)
    args = ap.parse_args()
    from .pg_storage import PostgresStorage
    storage = PostgresStorage(args.dsn)
    storage.migrate()
    rows = compute_ranking(storage, args.rpc, args.window, args.top)
    run_ts = int(time.time())
    n = storage.save_launchpad_rank(run_ts, rows)
    print({"run_ts": run_ts, "saved": n,
           "top": [{"impl": r["impl"][:24], "hooks": r["hooks"], "swaps": r["swaps"],
                    "sample_hook": r["sample_hook"]} for r in rows[:8]]})
    storage.close()


if __name__ == "__main__":
    main()
