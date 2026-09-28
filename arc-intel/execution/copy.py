"""Copy-trading decisions (pure, testable) — multi-wallet + global filters.

The follower tracks any number of leader wallets. Filters apply to every tracked wallet:
- `min_buy_usdc`: only copy leader buys at least this big (0 = all).
- `max_open`: cap on the number of open copied positions (0 = unlimited).
- `sizing`: "flat" (a fixed USDC amount per copy) or "proportional" (mirror the leader's size).
- `mirror_sells`: mirror the leader's sells (close the follower's position).
- protection defaults (TP/SL/trailing/dump guard) are attached to every copied fill.

Execution lives in `execution.copy_keeper` (custodial "Modo Maestro" bot wallet).
"""
from __future__ import annotations

from dataclasses import dataclass, replace

DEFAULT_FLAT_USDC = 25.0
SIZING_FLAT = "flat"
SIZING_PROPORTIONAL = "proportional"


@dataclass
class CopySettings:
    min_buy_usdc: float = 0.0
    max_open: int = 0
    sizing: str = SIZING_FLAT
    flat_usdc: float = DEFAULT_FLAT_USDC
    mirror_sells: bool = True
    tp_pct: float = 0.0
    sl_pct: float = 0.0
    trailing_pct: float = 0.0
    dump_guard: bool = True

    @classmethod
    def from_row(cls, row: dict | None) -> "CopySettings":
        if not row:
            return cls()
        return cls(
            min_buy_usdc=float(row.get("min_buy_usdc") or 0.0),
            max_open=int(row.get("max_open") or 0),
            sizing=(row.get("sizing") or SIZING_FLAT),
            flat_usdc=float(row.get("flat_usdc") if row.get("flat_usdc") is not None
                            else DEFAULT_FLAT_USDC),
            mirror_sells=bool(row.get("mirror_sells", True)),
            tp_pct=float(row.get("tp_pct") or 0.0),
            sl_pct=float(row.get("sl_pct") or 0.0),
            trailing_pct=float(row.get("trailing_pct") or 0.0),
            dump_guard=bool(row.get("dump_guard", True)))

    def with_flat(self, flat_usdc) -> "CopySettings":
        """Per-wallet flat override (None keeps the global value)."""
        if flat_usdc is None:
            return self
        return replace(self, flat_usdc=float(flat_usdc))


def plan_size(leader_value: float, settings: CopySettings) -> float:
    if settings.sizing == SIZING_PROPORTIONAL:
        return round(float(leader_value or 0.0), 6)
    return round(float(settings.flat_usdc or 0.0), 6)


def decide(trade: dict, settings: CopySettings, position_qty: float = 0.0,
           open_positions: int = 0, holding: bool = False) -> dict:
    """Pure decision for one leader trade. Returns {'action': 'buy'|'sell'|'skip', ...}."""
    side = str((trade or {}).get("side") or "").lower()
    value = float((trade or {}).get("stable_value") or 0.0)
    if side == "buy":
        if value < float(settings.min_buy_usdc or 0.0):
            return {"action": "skip", "reason": "below_min"}
        if settings.max_open and int(open_positions) >= int(settings.max_open) and not holding:
            return {"action": "skip", "reason": "max_open"}
        usdc = plan_size(value, settings)
        if usdc <= 0:
            return {"action": "skip", "reason": "no_size"}
        return {"action": "buy", "usdc": usdc}
    if side == "sell":
        if not settings.mirror_sells:
            return {"action": "skip", "reason": "mirror_off"}
        if float(position_qty or 0.0) <= 0:
            return {"action": "skip", "reason": "no_position"}
        return {"action": "sell", "pct": 100.0}
    return {"action": "skip", "reason": "unknown_side"}
