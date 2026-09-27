"""Real position tracking (average-cost), reusing the PnL discipline from indexer/pnl.py.

One position per (user, token). Each CONFIRMED on-chain fill updates it:
- buy:  qty += token_qty ; cost += usdc_value
- sell: COGS = avg_cost * sold_qty ; realized += proceeds - COGS ; qty -= sold_qty ; cost -= COGS

Idempotency: the store keys fills by a unique fill id (tx_hash:log_index), so reprocessing
the same event never counts twice. Reconciliation against the real on-chain balance is a
separate check (see reconcile()).
"""
from __future__ import annotations

from dataclasses import dataclass


class PositionError(ValueError):
    pass


@dataclass
class Position:
    token: str = ""
    qty: float = 0.0
    cost: float = 0.0        # total USDC cost of the CURRENT qty
    realized: float = 0.0
    last_block: int = 0

    @property
    def avg_cost(self) -> float:
        return self.cost / self.qty if self.qty > 0 else 0.0


def apply_fill(pos: Position, side: str, token_qty: float, usdc_value: float,
               block: int = 0) -> Position:
    """Average-cost update in place (mirrors pnl.closed_trades)."""
    try:
        token_qty = float(token_qty)
        usdc_value = float(usdc_value)
    except (TypeError, ValueError):
        raise PositionError("bad_numbers")
    if token_qty <= 0:
        raise PositionError("token_qty_must_be_positive")
    if side == "buy":
        pos.qty += token_qty
        pos.cost += usdc_value
    elif side == "sell":
        if pos.qty <= 0:
            raise PositionError("no_position_to_sell")
        sold = min(token_qty, pos.qty)
        cogs = pos.avg_cost * sold
        proceeds = usdc_value * (sold / token_qty)
        pos.realized += proceeds - cogs
        pos.qty -= sold
        pos.cost -= cogs
        if pos.qty <= 1e-18:
            pos.qty = 0.0
            pos.cost = 0.0
    else:
        raise PositionError(f"invalid_side:{side}")
    pos.last_block = int(block)
    return pos


def sell_quantity(pos: Position | None, pct: float, has_pending: bool = False) -> float:
    """X% of the CURRENT tracked position.

    Refuses (PositionError) if there is a pending unconfirmed operation, if there is no
    real position yet, or if pct is out of (0, 1]. Never computes a % over a position that
    does not exist.
    """
    if has_pending:
        raise PositionError("pending_operation")
    if pos is None or pos.qty <= 0:
        raise PositionError("no_position")
    if not (0 < pct <= 1):
        raise PositionError("invalid_pct")
    return pos.qty * pct


def reconcile(pos: Position | None, onchain_qty: float, tol: float = 1e-6) -> tuple[bool, float]:
    """Compare our computed qty with the real on-chain balance. Mismatch = alarm."""
    computed = pos.qty if pos else 0.0
    diff = computed - float(onchain_qty)
    scale = max(abs(computed), abs(float(onchain_qty)), 1.0)
    return (abs(diff) / scale <= tol), diff
