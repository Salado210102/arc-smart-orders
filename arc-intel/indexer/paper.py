"""Phase 4 — [PAPER] execution + counterfactual outcome. NO funds, NO signing.

Counterfactual (explicit): when a dev-sell alert fires at block B, a user either
  - ACT:   sell at the price at B + simulated_delay (realistic reaction/slippage), or
  - HOLD:  keep the position to a horizon (1h/6h/24h).
benefit = (act_price - horizon_price) / act_price  (>0 => selling avoided a drop).
The delay is simulated (default 45s) to avoid the optimistic "instant perfect fill" bias;
we also compute the instant variant to show how much the delay changes the result.

Every user-facing string is prefixed with [PAPER].
"""
from __future__ import annotations

import bisect

SECONDS_PER_BLOCK = 0.52
DEFAULT_DELAY_SECONDS = 45
HORIZONS = {"1h": 3600, "6h": 21600, "24h": 86400}
PAPER_TAG = "[PAPER]"


def blocks_for(seconds: float) -> int:
    return max(1, int(round(seconds / SECONDS_PER_BLOCK)))


def last_trade_at(series: list, block: int):
    """Return (source_block, price) for the last trade with block <= `block`, or (None, None)."""
    if not series:
        return None, None
    blocks = [b for b, _ in series]
    i = bisect.bisect_right(blocks, block) - 1
    return (series[i][0], series[i][1]) if i >= 0 else (None, None)


def price_at(series: list, block: int):
    """series: sorted list[(block, price)]. Return last price with its block <= `block`."""
    return last_trade_at(series, block)[1]


def paper_outcome(series: list, alert_block: int, delay_seconds: float = DEFAULT_DELAY_SECONDS,
                  horizons: dict | None = None) -> dict:
    horizons = horizons or HORIZONS
    delay_blocks = blocks_for(delay_seconds)
    act_block = alert_block + delay_blocks
    act_delayed = price_at(series, act_block)
    act_instant = price_at(series, alert_block)
    out = {}
    for name, sec in horizons.items():
        hb = alert_block + blocks_for(sec)
        src_block, hp = last_trade_at(series, hb)
        if hp is None:
            continue
        # stale = no trade after we acted => price is frozen, NOT a real horizon outcome
        stale = src_block is None or src_block <= act_block
        bd = (act_delayed - hp) / act_delayed if act_delayed else None
        bi = (act_instant - hp) / act_instant if act_instant else None
        out[name] = {"horizon_block": hb, "source_block": src_block, "stale": stale, "price": hp,
                     "benefit_delayed": bd, "benefit_instant": bi}
    return {"alert_block": alert_block, "act_block": act_block,
            "act_price_delayed": act_delayed, "act_price_instant": act_instant,
            "horizons": out}


def paper_message(token: str, outcome: dict) -> str:
    lines = [f"{PAPER_TAG} simulated outcome for {token} (dev-sell counterfactual):",
             f"  acted (sell) at block {outcome['act_block']} @ {outcome['act_price_delayed']}"]
    for name, h in outcome["horizons"].items():
        bd = h["benefit_delayed"]
        bi = h["benefit_instant"]
        if bd is None:
            continue
        lines.append(f"  {name}: benefit vs hold {bd * 100:+.1f}% "
                     f"(instant-fill variant {bi * 100:+.1f}%)" if bi is not None else
                     f"  {name}: benefit vs hold {bd * 100:+.1f}%")
    lines.append("  (simulated, not financial advice; no funds involved)")
    return "\n".join(lines)
