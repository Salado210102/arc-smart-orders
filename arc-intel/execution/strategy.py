"""Phase 5 — exit strategy logic (TP / SL / trailing / scale-out). Pure, testable.

Capital protection first (stop-loss), then trailing-stop, then take-profit, then scale-out.
No execution/signing here: it only decides the action given a position and a price.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ExitPlan:
    take_profit_pct: float | None = None    # e.g. 0.5 => +50%
    stop_loss_pct: float | None = None      # e.g. 0.2 => -20%
    trailing_stop_pct: float | None = None  # e.g. 0.25 => 25% off the high-water mark
    scale_out: list = field(default_factory=list)  # [(price_multiple, fraction), ...]


@dataclass
class Position:
    entry_price: float
    size: float
    high_water: float = 0.0


def pnl_pct(pos: Position, price: float) -> float:
    if pos.entry_price <= 0:
        return 0.0
    return (price - pos.entry_price) / pos.entry_price


def update_high_water(pos: Position, price: float) -> float:
    if price > pos.high_water:
        pos.high_water = price
    return pos.high_water


def evaluate_exit(pos: Position, price: float, plan: ExitPlan) -> dict:
    """Return {'action': ..., 'reason': ..., 'fraction': ...} without mutating position."""
    update_high_water(pos, price)

    if plan.stop_loss_pct is not None and pnl_pct(pos, price) <= -abs(plan.stop_loss_pct):
        return {"action": "stop_loss", "reason": f"price <= entry*(1-{plan.stop_loss_pct})",
                "fraction": 1.0}

    if (plan.trailing_stop_pct is not None and pos.high_water > pos.entry_price
            and price <= pos.high_water * (1 - abs(plan.trailing_stop_pct))):
        return {"action": "trailing_stop",
                "reason": f"price <= high_water*(1-{plan.trailing_stop_pct})", "fraction": 1.0}

    if plan.take_profit_pct is not None and pnl_pct(pos, price) >= abs(plan.take_profit_pct):
        return {"action": "take_profit", "reason": f"price >= entry*(1+{plan.take_profit_pct})",
                "fraction": 1.0}

    for multiple, fraction in plan.scale_out:
        if price >= pos.entry_price * multiple:
            return {"action": "scale_out", "reason": f"price >= entry*{multiple}",
                    "fraction": float(fraction)}

    return {"action": "hold", "reason": "no_trigger", "fraction": 0.0}
