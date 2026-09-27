"""Aggregate [PAPER] evaluation: does acting on an alert beat holding?

Same methodology for every signal (dev_sell, compound, volume_collapse): sell at alert+delay
vs hold to 1h/6h/24h. Reports median, mean, %positive and a bootstrap CI on the median
(small samples). Answers the product question, not the skill question.
"""
from __future__ import annotations

import argparse
import random
import statistics

from .alerts import (compound_alerts, dev_sell_alerts, load_creator_sells, load_volume_buckets,
                     volume_collapse_alerts)
from .paper import DEFAULT_DELAY_SECONDS, paper_outcome
from .stream_alerts import load_price_series

HORIZONS = ("1h", "6h", "24h")


def bootstrap_median_ci(values: list, iters: int = 2000, alpha: float = 0.05,
                        seed: int = 42) -> tuple:
    if not values:
        return None, None
    if len(values) == 1:
        return values[0], values[0]
    rng = random.Random(seed)
    n = len(values)
    meds = []
    for _ in range(iters):
        meds.append(statistics.median([values[rng.randrange(n)] for _ in range(n)]))
    meds.sort()
    lo = meds[int((alpha / 2) * iters)]
    hi = meds[int((1 - alpha / 2) * iters) - 1]
    return lo, hi


def _stats(outcomes: list, horizon: str) -> dict:
    real, instant, stale = [], [], 0
    for o in outcomes:
        h = o["horizons"].get(horizon) if isinstance(o, dict) else o["horizons"].get(horizon)
        if not h or h.get("benefit_delayed") is None:
            continue
        if h.get("stale"):
            stale += 1
            continue
        real.append(h["benefit_delayed"])
        if h.get("benefit_instant") is not None:
            instant.append(h["benefit_instant"])
    if not real:
        return {"n_real": 0, "n_stale": stale}
    lo, hi = bootstrap_median_ci(real)
    rs = sorted(real)
    p5 = rs[max(0, int(0.05 * len(rs)))]
    neg = [1.0 - x for x in real if x < 0]  # missed upside multiple (horizon/act)
    return {"n_real": len(real), "n_stale": stale,
            "median_delayed_pct": round(statistics.median(real) * 100, 2),
            "median_ci95_pct": [round(lo * 100, 2), round(hi * 100, 2)],
            "mean_delayed_pct": round(statistics.mean(real) * 100, 2),
            "pct_positive_delayed": round(sum(1 for x in real if x > 0) / len(real) * 100, 1),
            "worst5pct_delayed_pct": round(p5 * 100, 2),
            "max_missed_upside_x": round(max(neg), 2) if neg else None,
            "median_instant_pct": round(statistics.median(instant) * 100, 2) if instant else None}


def _outcomes_for(storage, alerts: list, delay_seconds: float, series_cache: dict) -> list:
    seen = set()
    out = []
    for a in alerts:
        key = (a.token, a.block)
        if key in seen:
            continue
        seen.add(key)
        if a.token not in series_cache:
            series_cache[a.token] = load_price_series(storage, a.token)
        out.append(paper_outcome(series_cache[a.token], a.block, delay_seconds=delay_seconds))
    return out


def evaluate(storage, delay_seconds: float = DEFAULT_DELAY_SECONDS, min_pct: float = 0.5,
             min_usdc: float = 100.0) -> dict:
    dev = dev_sell_alerts(load_creator_sells(storage), min_pct, min_usdc)
    collapse = volume_collapse_alerts(load_volume_buckets(storage, 600), z_threshold=-2.0)
    compound = compound_alerts(dev, collapse, 6000)
    series_cache: dict = {}
    report = {"delay_seconds": delay_seconds}
    for name, alerts in (("dev_sell", dev), ("compound", compound),
                         ("volume_collapse", collapse)):
        outcomes = _outcomes_for(storage, alerts, delay_seconds, series_cache)
        report[name] = {"n_alerts": len(outcomes),
                        "horizons": {h: _stats(outcomes, h) for h in HORIZONS}}
    return report


def persist_pending(storage, store, delay_seconds: float = DEFAULT_DELAY_SECONDS) -> int:
    """Compute + persist [PAPER] outcomes for detected alerts whose horizons now have data.

    Uses the SAME methodology as the offline evaluation (delay, horizons) so the live metric
    stays comparable over time.
    """
    import json
    import time
    from .paper import HORIZONS, blocks_for
    from .stream_alerts import max_leg_block
    head = max_leg_block(storage)
    ready = head - blocks_for(max(HORIZONS.values()))
    pending = store.list_pending_paper_alerts(ready, int(delay_seconds))
    cache: dict = {}
    n = 0
    for kind, token, block in pending:
        if token not in cache:
            cache[token] = load_price_series(storage, token)
        out = paper_outcome(cache[token], block, delay_seconds=delay_seconds)
        store.save_paper_outcome(kind, token, block, int(delay_seconds), int(time.time()),
                                 json.dumps(out["horizons"]))
        n += 1
    return n


def live_report(store, delay_seconds: float = DEFAULT_DELAY_SECONDS) -> dict:
    rows = store.list_paper_outcomes(int(delay_seconds))
    by: dict = {}
    for r in rows:
        by.setdefault(r["kind"], []).append({"horizons": r["horizons"]})
    return {kind: {"n_alerts": len(v), "horizons": {h: _stats(v, h) for h in HORIZONS}}
            for kind, v in by.items()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", type=str)
    ap.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS)
    args = ap.parse_args()
    from .pg_storage import PostgresStorage
    storage = PostgresStorage(args.dsn)
    print(evaluate(storage, delay_seconds=args.delay))
    storage.close()


if __name__ == "__main__":
    main()
