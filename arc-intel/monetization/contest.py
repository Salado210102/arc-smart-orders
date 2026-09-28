"""Volume contest (pure): 2 rounds/day (UTC), trader + affiliate rankings, merit by volume.

No lottery (no randomness): whoever moves the most volume in the round wins. The prize pool
("pozo") of each round = 10% of that round's fees (5% trader + 5% affiliate), split 50/50.
Winners are published 1h after the round closes.

See `docs/ARC_AI_ECONOMIC_MODEL.md` (calendario + anti-abuso).
"""
from __future__ import annotations

ROUND_HOURS = 12
FEE_BPS = 100            # 1% standard fee
POZO_BPS = 1000          # 10% of the round's fees -> prize pool
PUBLISH_DELAY_S = 3600   # winners published 1h after close


def round_index(ts: float, round_hours: int = ROUND_HOURS) -> int:
    return int(float(ts) // (round_hours * 3600))


def round_window(ts: float, round_hours: int = ROUND_HOURS) -> dict:
    secs = int(round_hours) * 3600
    start = int(float(ts) // secs) * secs
    end = start + secs
    return {"id": start, "start": start, "end": end,
            "seconds_left": max(0, end - int(ts)), "round_hours": int(round_hours)}


def volume_to_fee(volume_usdc: float, fee_bps: int = FEE_BPS) -> float:
    return float(volume_usdc or 0.0) * fee_bps / 10_000.0


def pozo(volume_usdc: float, fee_bps: int = FEE_BPS, pozo_bps: int = POZO_BPS) -> float:
    return round(volume_to_fee(volume_usdc, fee_bps) * pozo_bps / 10_000.0, 6)


def split_prize(pozo_usdc: float) -> dict:
    half = round(float(pozo_usdc) / 2.0, 6)
    return {"trader": half, "affiliate": half}


def leaderboard(volume_by_user: dict, top: int = 10) -> list:
    rows = sorted(((str(u), float(v)) for u, v in (volume_by_user or {}).items() if float(v) > 0),
                  key=lambda kv: (-kv[1], kv[0]))
    return [{"rank": i, "user": u, "volume": v} for i, (u, v) in enumerate(rows[:max(1, int(top))], 1)]


def standings(trader_vol: dict, affiliate_vol: dict | None = None, *, top: int = 10,
              fee_bps: int = FEE_BPS) -> dict:
    """Compute the round's total volume, pozo, prize split and both leaderboards."""
    affiliate_vol = affiliate_vol or {}
    total = sum(float(v) for v in (trader_vol or {}).values())
    p = pozo(total, fee_bps)
    return {"total_volume": total, "pozo": p, "prize": split_prize(p),
            "trader_top": leaderboard(trader_vol, top),
            "affiliate_top": leaderboard(affiliate_vol, top)}


def previous_round(now: float, round_hours: int = ROUND_HOURS) -> dict:
    """The round that just closed (the one before the current one)."""
    cur = round_window(now, round_hours)
    secs = cur["end"] - cur["start"]
    return {"id": cur["start"] - secs, "start": cur["start"] - secs, "end": cur["start"]}


def winner(volume_by_user: dict) -> dict | None:
    lb = leaderboard(volume_by_user, top=1)
    return lb[0] if lb else None


def settle(trader_vol: dict, affiliate_vol: dict, fee_bps: int = FEE_BPS) -> dict:
    """Final results of a closed round: who won each category and the prize each takes."""
    total = sum(float(v) for v in (trader_vol or {}).values())
    p = pozo(total, fee_bps)
    pr = split_prize(p)
    return {"total_volume": total, "pozo": p, "prize": pr,
            "trader": winner(trader_vol), "affiliate": winner(affiliate_vol)}


def rank_of(volume_by_user: dict, user: str) -> dict:
    """The given user's rank (1-based) and volume, or rank 0 if not on the board."""
    lb = leaderboard(volume_by_user, top=10_000)
    u = str(user)
    for row in lb:
        if row["user"] == u:
            return {"rank": row["rank"], "volume": row["volume"]}
    return {"rank": 0, "volume": float((volume_by_user or {}).get(u, 0.0))}


def mask_user(user: str) -> str:
    u = str(user)
    return u if len(u) <= 5 else (u[:2] + "\u2026" + u[-2:])
