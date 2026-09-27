"""Phase 3 — live exit signals & anti-rug (pure, testable).

Signals (all computed from already-indexed swaps/legs):
  - rolling volume z-score / volume collapse per token
  - smart-money exit (scored wallets selling a token in a window)
  - dev-sell (token creator selling)
  - per-token risk flags combining the above (launchpad-agnostic core; specific
    bonding-curve rules plug in as extra flags).

Inputs are generic "legs" dicts: {wallet, token, block, side, stable_value}.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable

SEVERITY = {"low": 1, "medium": 2, "high": 3}
DEFAULT_BUCKET_BLOCKS = 2000
DEFAULT_LOOKBACK = 12
DEFAULT_Z_THRESHOLD = -1.5
MIN_SCORED_TRADES = 8


def bucket_volumes(legs: list[dict], bucket_blocks: int = DEFAULT_BUCKET_BLOCKS) -> dict[str, list[tuple[int, float]]]:
    """Aggregate traded notional per token into fixed block buckets (sorted)."""
    series: dict[str, dict[int, float]] = defaultdict(lambda: defaultdict(float))
    for l in legs:
        token = (l.get("token") or "").lower()
        if not token:
            continue
        b = int(l.get("block") or 0) // bucket_blocks * bucket_blocks
        series[token][b] += float(l.get("stable_value") or 0.0)
    return {t: sorted(d.items()) for t, d in series.items()}


def rolling_zscore(series: list[tuple[int, float]], lookback: int = DEFAULT_LOOKBACK) -> list[tuple[int, float | None]]:
    """Z-score of each bucket vs the previous `lookback` buckets (exclusive)."""
    vals = [v for _, v in series]
    out: list[tuple[int, float | None]] = []
    for i, (b, v) in enumerate(series):
        window = vals[max(0, i - lookback):i]
        if len(window) < 3:
            out.append((b, None))
            continue
        m = sum(window) / len(window)
        var = sum((x - m) ** 2 for x in window) / len(window)
        sd = var ** 0.5
        out.append((b, 0.0 if sd == 0 else (v - m) / sd))
    return out


def volume_collapse(series: list[tuple[int, float]], lookback: int = DEFAULT_LOOKBACK,
                    z_threshold: float = DEFAULT_Z_THRESHOLD) -> dict | None:
    z = rolling_zscore(series, lookback)
    if not z or z[-1][1] is None:
        return None
    b, val = z[-1]
    if val <= z_threshold:
        return {"block": b, "z": round(val, 3)}
    return None


def smart_money_exit(legs: list[dict], smart_wallets: set[str], token: str,
                     from_block: int, to_block: int) -> dict:
    """Smart wallets selling `token` within [from_block, to_block]."""
    tok = token.lower()
    smart = {w.lower() for w in smart_wallets}
    sellers = {l["wallet"].lower() for l in legs
               if (l.get("token") or "").lower() == tok and l.get("side") == "sell"
               and (l.get("wallet") or "").lower() in smart
               and from_block <= int(l.get("block") or 0) <= to_block}
    return {"token": tok, "smart_sellers": len(sellers), "sellers": sorted(sellers)}


def dev_sell(legs: list[dict], creator: str | None, token: str) -> dict:
    """Creator sell activity in `token`."""
    c = (creator or "").lower()
    if not c:
        return {"creator": None, "dev_sells": 0, "first_block": None}
    sells = [int(l.get("block") or 0) for l in legs
             if (l.get("token") or "").lower() == token.lower()
             and (l.get("wallet") or "").lower() == c and l.get("side") == "sell"]
    return {"creator": c, "dev_sells": len(sells),
            "first_block": min(sells) if sells else None}


def anti_rug_report(legs: list[dict], creators_by_token: dict[str, str] | None = None,
                    smart_wallets: set[str] | None = None, bucket_blocks: int = DEFAULT_BUCKET_BLOCKS,
                    lookback: int = DEFAULT_LOOKBACK, z_threshold: float = DEFAULT_Z_THRESHOLD,
                    window_blocks: int = DEFAULT_BUCKET_BLOCKS * 6) -> dict[str, dict]:
    """Per-token risk flags. Launchpad-specific rules can extend the flag list."""
    creators_by_token = {k.lower(): v for k, v in (creators_by_token or {}).items()}
    smart_wallets = smart_wallets or set()
    series = bucket_volumes(legs, bucket_blocks)
    out: dict[str, dict] = {}
    for token, s in series.items():
        collapse = volume_collapse(s, lookback, z_threshold)
        dev = dev_sell(legs, creators_by_token.get(token), token)
        flags = []
        if collapse:
            flags.append("volume_collapse")
        if dev["dev_sells"] > 0:
            flags.append("dev_sell")
        last_block = s[-1][0] if s else 0
        sme = smart_money_exit(legs, smart_wallets, token, last_block - window_blocks, last_block + bucket_blocks)
        if sme["smart_sellers"] >= 1:
            flags.append("smart_money_exit")
        out[token] = {"volume_collapse": collapse, "dev_sell": dev,
                      "smart_money_exit": sme, "flags": flags,
                      "buckets": len(s), "last_bucket": last_block}
    return out


# --- launchpad-specific rule registry (config-driven; no invented mechanics) ---

@dataclass
class Rule:
    name: str
    severity: str
    predicate: Callable[[dict], bool]
    launchpads: tuple | None = None   # None = applies to all launchpads


RULES: list[Rule] = [
    Rule("dev_sell", "high", lambda t: t.get("dev_sell", {}).get("dev_sells", 0) > 0),
    Rule("smart_money_exit", "high", lambda t: t.get("smart_money_exit", {}).get("smart_sellers", 0) > 0),
    Rule("volume_collapse", "medium", lambda t: bool(t.get("volume_collapse"))),
]


def evaluate_rules(token_report: dict, launchpad: str | None = None,
                   rules: list[Rule] | None = None) -> list[Rule]:
    rules = rules if rules is not None else RULES
    return [r for r in rules
            if (r.launchpads is None or launchpad in r.launchpads) and r.predicate(token_report)]


def _describe(token: str, t: dict, fired: list[Rule]) -> str:
    parts = []
    for r in fired:
        if r.name == "dev_sell":
            parts.append(f"creator sold x{t['dev_sell']['dev_sells']}")
        elif r.name == "volume_collapse":
            parts.append(f"volume collapse z={t['volume_collapse']['z']}")
        elif r.name == "smart_money_exit":
            parts.append(f"{t['smart_money_exit']['smart_sellers']} smart wallet(s) exited")
        else:
            parts.append(r.name)
    return f"{token}: " + "; ".join(parts)


def build_alerts(report: dict[str, dict], launchpads_by_token: dict[str, str] | None = None,
                 rules: list[Rule] | None = None, min_severity: str = "low") -> list[dict]:
    """Turn per-token report into contextual alerts (reason + severity), highest first."""
    lp = {k.lower(): v for k, v in (launchpads_by_token or {}).items()}
    floor = SEVERITY.get(min_severity, 1)
    alerts = []
    for token, t in report.items():
        fired = evaluate_rules(t, lp.get(token), rules)
        if not fired:
            continue
        sev = max((r.severity for r in fired), key=lambda s: SEVERITY[s])
        if SEVERITY[sev] < floor:
            continue
        alerts.append({"token": token, "severity": sev,
                       "reasons": [{"rule": r.name, "severity": r.severity} for r in fired],
                       "message": _describe(token, t, fired)})
    alerts.sort(key=lambda a: SEVERITY[a["severity"]], reverse=True)
    return alerts


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--storage", default="pg")
    ap.add_argument("--dsn", type=str)
    ap.add_argument("--limit", type=int, default=500000)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--smart-min-score", type=float, default=0.0)
    ap.add_argument("--smart-min-trades", type=int, default=MIN_SCORED_TRADES)
    args = ap.parse_args()
    from .pg_storage import PostgresStorage
    from .pnl import collect_legs_pg
    from .scoring import load_insider_data_pg

    storage = PostgresStorage(args.dsn)
    legs = collect_legs_pg(storage, args.limit)
    creators, _dev = load_insider_data_pg(storage)
    smart = {r["wallet"] for r in storage.load_wallet_scores(args.smart_min_score, args.smart_min_trades)}
    storage.close()
    rep = anti_rug_report(legs, creators_by_token=creators, smart_wallets=smart)
    flagged = {t: d for t, d in rep.items() if d["flags"]}
    top = sorted(flagged.items(), key=lambda kv: len(kv[1]["flags"]), reverse=True)[: args.top]
    alerts = build_alerts(rep, min_severity="medium")
    print({"legs": len(legs), "tokens": len(rep), "flagged": len(flagged), "smart_wallets": len(smart),
           "by_flag": {
               "volume_collapse": sum(1 for d in rep.values() if "volume_collapse" in d["flags"]),
               "dev_sell": sum(1 for d in rep.values() if "dev_sell" in d["flags"]),
               "smart_money_exit": sum(1 for d in rep.values() if "smart_money_exit" in d["flags"])},
           "alerts": len(alerts),
           "top_alerts": alerts[:5],
           "top": [{"token": t, "flags": d["flags"], "dev_sells": d["dev_sell"]["dev_sells"],
                    "smart_sellers": d["smart_money_exit"]["smart_sellers"],
                    "vol_collapse_z": d["volume_collapse"]["z"] if d["volume_collapse"] else None}
                   for t, d in top]})


if __name__ == "__main__":
    main()
