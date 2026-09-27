"""Wallet scoring engine (Phase 2): filters, metrics, decay, explainable score, PIT, walk-forward.

Pure functions operate on a generic event/metrics model so they are testable and
backend-agnostic. A CLI (`python -m indexer.scoring --storage pg --dsn ...`) runs it on
real indexed data and prints explainable examples.

Spec separation: filtering happens BEFORE any score. Insiders (creators / dev-buy
recipients) are excluded per token; likely MEV wallets are excluded from the
"conviction" score; Sybil clusters are collapsed to one entity for scoring.
"""
from __future__ import annotations

import argparse
import math
from dataclasses import dataclass, field

WEIGHTS_VERSION = "v1"
WEIGHTS = {"activity": 0.30, "frequency": 0.20, "diversity": 0.30, "volume": 0.20}
MIN_CLOSED_TRADES = 8
MEV_MIN_HOLDING_SECONDS = 60
MEV_MIN_OCCURRENCES = 3
MEV_ROUNDTRIP_FRACTION = 0.5
SYBIL_WINDOW_SECONDS = 3600
DEFAULT_HALF_LIFE_DAYS = 30.0
SECONDS_PER_BLOCK = 0.52  # Arc measured mean

CONFIDENCE_LEVELS = [("insuficiente", 0), ("baja", MIN_CLOSED_TRADES), ("media", 20), ("alta", 50)]


@dataclass
class WalletEvent:
    wallet: str
    token: str | None
    pool: str | None
    block_number: int
    ts: int | None
    amount_in: str
    amount_out: str
    side: str = "unknown"

    @property
    def time(self) -> int:
        return self.ts if self.ts is not None else int(self.block_number * SECONDS_PER_BLOCK)


def confidence_for(n: int) -> str:
    label = "insuficiente"
    for name, threshold in CONFIDENCE_LEVELS:
        if n >= threshold:
            label = name
    return label


# --- 1. Filters (run BEFORE scoring) ---

def insider_wallets(creators_by_token: dict[str, str], dev_buy_recipients: dict[str, set[str]]) -> dict[str, set[str]]:
    """token -> set of insider wallets (creator + dev-buy recipients)."""
    insiders: dict[str, set[str]] = {}
    for token, creator in creators_by_token.items():
        insiders.setdefault(token, set()).add(creator.lower())
    for token, wallets in dev_buy_recipients.items():
        for w in wallets:
            insiders.setdefault(token, set()).add(w.lower())
    return insiders


def is_insider(insiders: dict[str, set[str]], wallet: str, token: str | None) -> bool:
    if token is None:
        return False
    return wallet.lower() in insiders.get(token.lower(), set())


def detect_likely_mev(events: list[WalletEvent], min_holding_seconds: int = MEV_MIN_HOLDING_SECONDS,
                      min_occurrences: int = MEV_MIN_OCCURRENCES,
                      roundtrip_fraction: float = MEV_ROUNDTRIP_FRACTION) -> set[str]:
    """Flag wallets with consistent same-block round-trips or sub-threshold holding time."""
    by_wallet: dict[str, list[WalletEvent]] = {}
    for e in events:
        by_wallet.setdefault(e.wallet.lower(), []).append(e)
    flagged: set[str] = set()
    for wallet, evs in by_wallet.items():
        if len(evs) < min_occurrences:
            continue
        # a block with >=2 events for the same wallet is a same-block round-trip
        blocks: dict[int, int] = {}
        for e in evs:
            blocks[e.block_number] = blocks.get(e.block_number, 0) + 1
        roundtrips = sum(1 for c in blocks.values() if c >= 2)
        fraction = roundtrips / len(blocks) if blocks else 0.0
        if fraction >= roundtrip_fraction:
            flagged.add(wallet)
            continue
        # holding time: median gap between consecutive events
        ordered = sorted(evs, key=lambda x: (x.block_number, x.time))
        gaps = [ordered[i].time - ordered[i - 1].time for i in range(1, len(ordered))]
        gaps = [g for g in gaps if g >= 0]
        if gaps:
            gaps.sort()
            median = gaps[len(gaps) // 2]
            if median < min_holding_seconds:
                flagged.add(wallet)
    return flagged


def sybil_clusters(funding_edges: list[tuple[str, str, int]],
                   window_seconds: int = SYBIL_WINDOW_SECONDS) -> dict[str, int]:
    """Union-find over wallets sharing the same funding tx within a window.

    funding_edges: (wallet, funder_or_tx, ts). Wallets sharing a funder within the window
    are grouped; returns wallet -> cluster_id.
    """
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

    by_funder: dict[str, list[tuple[str, int]]] = {}
    for wallet, funder, ts in funding_edges:
        find(wallet.lower())
        by_funder.setdefault(funder, []).append((wallet.lower(), ts))
    for funder, entries in by_funder.items():
        entries.sort(key=lambda x: x[1])
        for i in range(1, len(entries)):
            w_prev, t_prev = entries[i - 1]
            w_cur, t_cur = entries[i]
            find(w_prev)
            find(w_cur)
            if t_cur - t_prev <= window_seconds:
                union(w_prev, w_cur)
    cluster_of: dict[str, int] = {}
    roots: dict[str, int] = {}
    for w in parent:
        r = find(w)
        if r not in roots:
            roots[r] = len(roots)
        cluster_of[w] = roots[r]
    return cluster_of


def collapse_sybil(events: list[WalletEvent], cluster_of: dict[str, int]) -> list[WalletEvent]:
    """Reassign wallet id to its cluster representative for scoring."""
    out = []
    for e in events:
        rep = cluster_of.get(e.wallet.lower())
        if rep is None:
            out.append(e)
        else:
            e2 = WalletEvent(e.wallet, e.token, e.pool, e.block_number, e.ts, e.amount_in, e.amount_out, e.side)
            e2.wallet = f"cluster:{rep}"
            out.append(e2)
    return out


# --- 2. Metrics ---

@dataclass
class WalletMetrics:
    wallet: str
    swaps: int = 0
    tokens: set = field(default_factory=set)
    pools: set = field(default_factory=set)
    volume_in: float = 0.0
    volume_out: float = 0.0
    first_block: int | None = None
    last_block: int | None = None
    activity: float = 0.0            # decay-weighted event count
    volume_weighted: float = 0.0     # decay-weighted notional

    @property
    def active_days(self) -> float:
        if self.first_block is None or self.last_block is None:
            return 0.0
        return max(0.0, (self.last_block - self.first_block) * SECONDS_PER_BLOCK / 86400.0)

    @property
    def frequency(self) -> float:
        # swaps per active day; a wallet active in a single block gets its raw count
        days = self.active_days
        return float(self.swaps) if days == 0 else self.swaps / days


def _notional(e: WalletEvent) -> float:
    try:
        return abs(float(e.amount_in)) + abs(float(e.amount_out))
    except (TypeError, ValueError):
        return 0.0


def base_metrics(events: list[WalletEvent]) -> dict[str, WalletMetrics]:
    out: dict[str, WalletMetrics] = {}
    per_wallet: dict[str, list[tuple[int, float]]] = {}
    now = 0
    for e in events:
        w = e.wallet.lower()
        m = out.setdefault(w, WalletMetrics(wallet=w))
        m.swaps += 1
        if e.token:
            m.tokens.add(e.token.lower())
        if e.pool:
            m.pools.add(e.pool.lower())
        try:
            m.volume_in += abs(float(e.amount_in))
            m.volume_out += abs(float(e.amount_out))
        except (TypeError, ValueError):
            pass
        if m.first_block is None or e.block_number < m.first_block:
            m.first_block = e.block_number
        if m.last_block is None or e.block_number > m.last_block:
            m.last_block = e.block_number
        t = e.time
        now = max(now, t)
        per_wallet.setdefault(w, []).append((t, _notional(e)))
    for w, pairs in per_wallet.items():
        m = out[w]
        m.activity = sum(decay_weight(now - t) for t, _ in pairs)
        m.volume_weighted = sum(decay_weight(now - t) * vol for t, vol in pairs)
    return out


def decay_weight(age_seconds: float, half_life_days: float = DEFAULT_HALF_LIFE_DAYS) -> float:
    if age_seconds <= 0:
        return 1.0
    return 0.5 ** (age_seconds / (half_life_days * 86400.0))


def pit_filter(events: list[WalletEvent], as_of_time: int) -> list[WalletEvent]:
    return [e for e in events if e.time <= as_of_time]


# --- 4. Explainable score ---

def _percentiles(values: list[float]) -> list[float]:
    n = len(values)
    if n == 0:
        return []
    order = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0
        pr = avg / (n - 1) if n > 1 else 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = pr
        i = j + 1
    return ranks


def _components(metrics: dict[str, WalletMetrics]) -> dict[str, list[float]]:
    wallets = list(metrics)
    return {
        "activity": _percentiles([metrics[w].activity for w in wallets]),
        "frequency": _percentiles([metrics[w].frequency for w in wallets]),
        "diversity": _percentiles([len(metrics[w].tokens) + len(metrics[w].pools) for w in wallets]),
        "volume": _percentiles([metrics[w].volume_weighted for w in wallets]),
    }


def score_wallets(metrics: dict[str, WalletMetrics], weights: dict[str, float] = None,
                  weights_version: str = WEIGHTS_VERSION) -> dict[str, dict]:
    weights = weights or WEIGHTS
    wallets = list(metrics)
    if not wallets:
        return {}
    comp = _components(metrics)
    out: dict[str, dict] = {}
    for i, w in enumerate(wallets):
        breakdown = {k: round(weights[k] * comp[k][i], 4) for k in weights}
        score = round(sum(breakdown.values()), 4)
        out[w] = {
            "wallet": w,
            "score": score,
            "confidence": confidence_for(metrics[w].swaps),
            "n": metrics[w].swaps,
            "weights_version": weights_version,
            "breakdown": breakdown,
        }
    return out


# --- 5. Walk-forward validation (PIT-safe) vs shuffled baseline ---

def pearson(x: list[float], y: list[float]) -> float | None:
    n = len(x)
    if n < 2 or n != len(y):
        return None
    mx = sum(x) / n
    my = sum(y) / n
    num = sum((x[i] - mx) * (y[i] - my) for i in range(n))
    dx = math.sqrt(sum((x[i] - mx) ** 2 for i in range(n)))
    dy = math.sqrt(sum((y[i] - my) ** 2 for i in range(n)))
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def walk_forward(pairs: list[tuple[float, float]], seed: int = 42) -> dict:
    """pairs: (score_at_T, performance_T_plus_h). Compares real vs shuffled baseline."""
    import random
    if len(pairs) < 5:
        return {"status": "INSUFFICIENT_SAMPLE", "n": len(pairs)}
    scores = [p[0] for p in pairs]
    perf = [p[1] for p in pairs]
    real = pearson(scores, perf)
    rng = random.Random(seed)
    shuffled = perf[:]
    rng.shuffle(shuffled)
    base = pearson(scores, shuffled)
    return {"status": "OK", "n": len(pairs), "real_corr": real, "shuffled_corr": base}


def walk_forward_trades(trades: list, split_block: int, horizon_blocks: int,
                        min_train: int = MIN_CLOSED_TRADES, seed: int = 42) -> dict:
    """PIT walk-forward: signal from trades closed <= split_block predicts realized PnL
    of the same wallets in (split_block, split_block+horizon_blocks]. Compares vs shuffle."""
    from collections import defaultdict
    train: dict[str, list] = defaultdict(list)
    test: dict[str, list] = defaultdict(list)
    for t in trades:
        if t.exit_block <= split_block:
            train[t.wallet].append(t.realized)
        elif split_block < t.exit_block <= split_block + horizon_blocks:
            test[t.wallet].append(t.realized)
    pairs = []
    for w, rs in train.items():
        if len(rs) < min_train or w not in test:
            continue
        pairs.append((sum(rs) / len(rs), sum(test[w])))
    res = walk_forward(pairs, seed=seed)
    res.update({"split_block": split_block, "horizon_blocks": horizon_blocks,
                "candidates": len(pairs)})
    return res


def _make_storage(args):
    if args.storage == "pg":
        from .pg_storage import PostgresStorage
        return PostgresStorage(args.dsn)
    from .storage import Storage
    return Storage(args.db or "arc_indexer.db")


# --- 4b. Composite confidence score (Phase 2): PnL + timing, explainable ---

COMPOSITE_WEIGHTS = {"win_rate": 0.35, "exit_multiple": 0.25, "entry_timing": 0.20, "consistency": 0.20}
COMPOSITE_VERSION = "v3"


def combine_scores(pnl_stats: dict, entry: dict, weights: dict = None,
                   min_trades: int = MIN_CLOSED_TRADES, version: str = COMPOSITE_VERSION) -> dict[str, dict]:
    """Combine closed-trade PnL stats into a continuous, explainable confidence score.

    Only wallets with closed_trades >= min_trades are eligible (min-sample rule).
    Components are cross-sectional percentiles; consistency = 1/(1+variance).
    """
    weights = weights or COMPOSITE_WEIGHTS
    wallets = [w for w, s in pnl_stats.items() if s.closed_trades >= min_trades]
    if not wallets:
        return {}
    comp = {
        "win_rate": _percentiles([pnl_stats[w].win_rate for w in wallets]),
        "exit_multiple": _percentiles([pnl_stats[w].avg_exit_multiple for w in wallets]),
        "entry_timing": _percentiles([entry.get(w, 0.0) for w in wallets]),
        "consistency": _percentiles([1.0 / (1.0 + pnl_stats[w].return_variance) for w in wallets]),
    }
    out: dict[str, dict] = {}
    for i, w in enumerate(wallets):
        s = pnl_stats[w]
        breakdown = {k: round(weights[k] * comp[k][i], 4) for k in weights}
        score = round(sum(breakdown.values()), 4)
        out[w] = {
            "wallet": w, "score": score, "version": version,
            "trades": s.closed_trades, "win_rate": round(s.win_rate, 3),
            "avg_mult": round(s.avg_exit_multiple, 3), "pnl": round(s.realized_pnl, 3),
            "variance": round(s.return_variance, 3), "entry_pct": round(entry.get(w, 0.0), 3),
            "confidence": confidence_for(s.closed_trades), "breakdown": breakdown,
        }
    return out


def load_events_pg(storage, limit: int = 500000, only_resolved: bool = False) -> list[WalletEvent]:
    conn = storage.pool.getconn()
    try:
        with conn.cursor() as cur:
            where = "s.trader IS NOT NULL" if only_resolved else "COALESCE(s.trader, s.wallet) IS NOT NULL"
            sql = ("SELECT COALESCE(s.trader, s.wallet) AS wallet, s.pool, s.block_number, "
                   "s.amount_in, s.amount_out, p.currency0, p.currency1 "
                   "FROM swaps s LEFT JOIN pools_v4 p ON s.pool = p.pool_id "
                   f"WHERE {where} ORDER BY s.block_number DESC")
            if limit and limit > 0:
                cur.execute(sql + " LIMIT %s", (limit,))
            else:
                cur.execute(sql)
            events = []
            for w, pool, block, ain, aout, c0, c1 in cur.fetchall():
                token = c0 if c0 and c0 != "0x0000000000000000000000000000000000000000" else c1
                events.append(WalletEvent(wallet=w, token=token, pool=pool, block_number=int(block or 0),
                                          ts=None, amount_in=str(ain), amount_out=str(aout)))
            return events
    finally:
        storage.pool.putconn(conn)


def resolution_stats_pg(storage) -> dict:
    conn = storage.pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT (SELECT COUNT(DISTINCT tx_hash) FROM swaps), "
                        "(SELECT COUNT(*) FROM tx_senders)")
            tx_total, resolved = cur.fetchone()
            return {"swap_tx_hashes": int(tx_total or 0), "resolved": int(resolved or 0)}
    finally:
        storage.pool.putconn(conn)


def load_insider_data_pg(storage) -> tuple[dict, dict]:
    creators: dict[str, str] = {}
    dev_recips: dict[str, set] = {}
    conn = storage.pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT address, creator FROM tokens WHERE creator IS NOT NULL")
            for addr, creator in cur.fetchall():
                if creator:
                    creators[str(addr).lower()] = str(creator)
            cur.execute("SELECT token, creator_wallet FROM dev_buys "
                        "WHERE token IS NOT NULL AND creator_wallet IS NOT NULL")
            for token, w in cur.fetchall():
                dev_recips.setdefault(str(token).lower(), set()).add(str(w))
    finally:
        storage.pool.putconn(conn)
    return creators, dev_recips


def _wallet_detail(m: WalletMetrics) -> dict:
    return {
        "swaps": m.swaps, "tokens": len(m.tokens), "pools": len(m.pools),
        "volume_in": round(m.volume_in, 2), "volume_out": round(m.volume_out, 2),
        "active_days": round(m.active_days, 3), "activity_decayed": round(m.activity, 3),
        "volume_weighted": round(m.volume_weighted, 2),
        "first_block": m.first_block, "last_block": m.last_block,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--storage", choices=["sqlite", "pg"], default="pg")
    ap.add_argument("--dsn", type=str)
    ap.add_argument("--db", type=str)
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--limit", type=int, default=500000)
    ap.add_argument("--only-resolved", action="store_true",
                    help="score only swaps whose tx.from (real trader) is resolved")
    ap.add_argument("--mode", choices=["activity", "composite", "walkforward", "rerank"], default="activity")
    ap.add_argument("--min-trades", type=int, default=MIN_CLOSED_TRADES)
    ap.add_argument("--split-block", type=int)
    ap.add_argument("--horizon", type=int)
    args = ap.parse_args()
    storage = _make_storage(args)
    storage.migrate()

    if args.mode == "walkforward":
        if args.storage != "pg" or not args.split_block or not args.horizon:
            print({"error": "walkforward requires --storage pg --split-block N --horizon M"})
            storage.close()
            return
        from .pnl import stream_pnl_pg
        rep = stream_pnl_pg(storage, min_trades=1, limit=args.limit, collect_trades=True)
        res = walk_forward_trades(rep["trades"], args.split_block, args.horizon,
                                  min_train=args.min_trades)
        print({"mode": "walkforward", "version": COMPOSITE_VERSION,
               "closed_trades": len(rep["trades"]), **res})
        storage.close()
        return

    if args.mode == "rerank":
        if args.storage != "pg":
            print({"error": "rerank requires --storage pg"})
            storage.close()
            return
        from .shrinkage import wilson_lower_bound, eb_shrink_win_rate, population_win_rate
        rows = storage.load_wallet_scores(0.0, 0)
        pop = population_win_rate(rows)
        for r in rows:
            n = int(r.get("trades") or 0)
            wins = round(float(r.get("win_rate") or 0.0) * n)
            r["wins"] = wins
            r["wilson"] = round(wilson_lower_bound(wins, n), 4)
            r["eb"] = round(eb_shrink_win_rate(wins, n, pop, 10.0), 4)
        rows.sort(key=lambda r: r["wilson"], reverse=True)
        print({"mode": "rerank", "scored": len(rows),
               "population_win_rate": round(pop, 4),
               "top": [{k: r.get(k) for k in ("wallet", "trades", "win_rate", "wilson", "eb", "pnl")}
                       for r in rows[: args.top]]})
        storage.close()
        return

    if args.mode == "composite":
        if args.storage != "pg":
            print({"error": "composite mode requires --storage pg"})
            storage.close()
            return
        from .pnl import stream_pnl_pg, coordinated_clusters
        rep = stream_pnl_pg(storage, min_trades=1, limit=args.limit)
        pnl_stats = rep["stats"]
        entry = rep["entry"]

        creators, dev_recips = load_insider_data_pg(storage)
        insider_set = {str(c).lower() for c in creators.values()}
        insider_set |= {str(w).lower() for ws in dev_recips.values() for w in ws}

        ev_limit = args.limit if args.limit and args.limit > 0 else 400000
        events = load_events_pg(storage, limit=ev_limit, only_resolved=True)
        mev = detect_likely_mev(events)
        sybil = coordinated_clusters(rep.get("first_buy", {}), min_wallets=5)
        excluded = insider_set | mev | set(sybil)
        filtered = {w: s for w, s in pnl_stats.items() if w not in excluded}
        scores = combine_scores(filtered, entry, min_trades=args.min_trades)
        try:
            storage.save_wallet_scores(list(scores.values()))
        except Exception:
            pass
        ranked = sorted(scores.values(), key=lambda d: d["score"], reverse=True)[: args.top]
        print({"mode": "composite", "version": COMPOSITE_VERSION,
               "swaps": rep["swaps"], "closed_trades": rep["closed"],
               "wallets_with_pnl": len(pnl_stats),
               "filters": {"mev": len(mev), "insider_wallets": len(insider_set),
                           "sybil_proxy": len(sybil), "excluded_total": len(excluded)},
               "scored": len(scores), "min_trades": args.min_trades, "top": ranked})
        storage.close()
        return

    if args.storage == "pg":
        events = load_events_pg(storage, limit=args.limit, only_resolved=args.only_resolved)
        resolution = resolution_stats_pg(storage)
    else:
        events = []  # sqlite demo path not wired here
        resolution = {"swap_tx_hashes": 0, "resolved": 0}

    mev = detect_likely_mev(events)
    clean = [e for e in events if e.wallet.lower() not in mev]

    insider_report: dict = {"status": "NOT_AVAILABLE", "reason": "tokens.creator / dev_buys empty"}
    try:
        creators, dev_recips = load_insider_data_pg(storage)
        insiders = insider_wallets(creators, dev_recips)
        if insiders:
            excluded = sum(1 for e in clean if is_insider(insiders, e.wallet, e.token))
            insider_report = {"status": "OK", "creator_tokens": len(creators),
                              "tokens_with_insiders": len(insiders), "excluded_events": excluded}
    except Exception as exc:  # schema absent / partial
        insider_report = {"status": "NOT_AVAILABLE", "reason": type(exc).__name__}

    sybil_report: dict = {"status": "NOT_AVAILABLE",
                          "reason": "native funding graph not indexed on v4 path"}

    metrics = base_metrics(clean)
    scores = score_wallets(metrics)
    ranked = sorted(scores.values(), key=lambda d: d["score"], reverse=True)[: args.top]

    examples: dict = {}
    if ranked:
        top_w = ranked[0]["wallet"]
        examples["top_wallet_detail"] = {"wallet": top_w, "metrics": _wallet_detail(metrics[top_w])}
    if mev:
        counts: dict[str, int] = {}
        for e in events:
            if e.wallet.lower() in mev:
                counts[e.wallet.lower()] = counts.get(e.wallet.lower(), 0) + 1
        mx = max(counts, key=counts.get)
        blocks = sorted({e.block_number for e in events if e.wallet.lower() == mx})
        examples["mev_exclusion"] = {"wallet": mx, "events": counts[mx],
                                     "reason": "same-block round-trips / sub-60s median holding",
                                     "blocks": blocks[:5]}

    print({"events": len(events), "mev_flagged": len(mev), "wallets_scored": len(metrics),
           "trader_attribution": resolution,
           "filters": {"insider": insider_report, "mev": {"flagged": len(mev)}, "sybil": sybil_report},
           "top": ranked, "examples": examples, "weights_version": WEIGHTS_VERSION})
    storage.close()


if __name__ == "__main__":
    main()
