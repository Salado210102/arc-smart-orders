"""Publish the closed contest round's winners to the official channel (best-effort, once per round).

Dormant unless `ARC_INTEL_CHANNEL` is set. A round settles `PUBLISH_DELAY_S` (1h) after it closes;
until `mark_contest_round` runs, a failed send is retried on the next loop cycle.
"""
from __future__ import annotations

from monetization import contest as CT


def display_name(store, user: str) -> str:
    """Public alias if we captured the @username, else a masked chat id."""
    name = store.get_state(f"name:{user}", "")
    return name or CT.mask_user(user)


def publish_round(store, transport, now, channel, *, logger=None, round_hours: int = CT.ROUND_HOURS,
                  delay_s: int = CT.PUBLISH_DELAY_S) -> dict | None:
    if not channel:
        return None
    prev = CT.previous_round(now, round_hours)
    if now < prev["end"] + delay_s:
        return None
    if store.contest_round_published(prev["id"]):
        return None
    trader = store.volume_by_user_between(prev["start"], prev["end"])
    aff = store.referred_volume_between(prev["start"], prev["end"])
    s = CT.settle(trader, aff)
    lines = ["\U0001F3C6 <b>Volume contest \u2014 round results</b>",
             f"Pool: <b>${s['pozo']:.2f}</b>", ""]
    rows = []
    for cat, label, key in (("trader", "\U0001F7E2 Trader", "trader"),
                            ("affiliate", "\U0001F465 Affiliate", "affiliate")):
        w = s[key]
        prize = s["prize"][key]
        if w:
            nm = display_name(store, w["user"])
            lines.append(f"{label} champion: <b>{nm}</b> \u2014 ${w['volume']:,.0f} "
                         f"(wins <b>${prize:.2f}</b>)")
            rows.append((cat, nm, w["volume"], prize))
        else:
            lines.append(f"{label}: no volume")
    try:
        transport.send(channel, "\n".join(lines), parse_mode="HTML")
    except Exception as e:
        if logger:
            logger({"contest_publish_failed": str(e)[:120]})
        return None
    store.mark_contest_round(prev["id"], int(now))
    for cat, nm, vol, prize in rows:
        store.record_contest_winner(prev["id"], cat, nm, vol, prize)
    if logger:
        logger({"contest_published": prev["id"], "winners": len(rows)})
    return {"round": prev["id"], "pozo": s["pozo"], "winners": len(rows)}
