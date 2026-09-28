"""Fee tiers (pure): welcome discount for referred users + VIP levels by 30-day volume.

Economics (docs/ARC_AI_ECONOMIC_MODEL.md):
- Standard fee: 1.00%.
- Welcome: referred users pay 0.90% for their first `WELCOME_DAYS` (default 30).
- VIP (by 30-day traded volume): VIP1 $10k → 0.80%, VIP2 $50k → 0.70%, VIP3 $250k → 0.65% (floor).
A discount is never summed with another: VIP overrides welcome.
"""
from __future__ import annotations

STANDARD_BPS = 100
WELCOME_BPS = 90
WELCOME_DAYS = 30
FLOOR_BPS = 65
VIP_TIERS = ((250_000, 65, "VIP3"), (50_000, 70, "VIP2"), (10_000, 80, "VIP1"))


def vip_tier(volume_30d: float) -> dict:
    v = float(volume_30d or 0.0)
    for thr, bps, name in VIP_TIERS:
        if v >= thr:
            return {"level": name, "fee_bps": bps, "threshold": thr}
    return {"level": "", "fee_bps": STANDARD_BPS, "threshold": 0}


def welcome_active(joined_ts, now, days: int = WELCOME_DAYS) -> bool:
    return bool(joined_ts) and (int(now) - int(joined_ts)) < int(days) * 86400


def fee_bps_for(*, joined_ts, now, referred: bool, volume_30d: float,
                welcome_days: int = WELCOME_DAYS) -> dict:
    """Resolve the effective fee: VIP > welcome (referred) > standard."""
    vip = vip_tier(volume_30d)
    if vip["level"]:
        return vip
    if referred and welcome_active(joined_ts, now, welcome_days):
        return {"level": "WELCOME", "fee_bps": WELCOME_BPS, "threshold": 0}
    return {"level": "STANDARD", "fee_bps": STANDARD_BPS, "threshold": 0}
