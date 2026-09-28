"""Copy-trading decisions (pure, testable).

Given a leader's indexed trade and the follower's budget config, decide what (if anything) to
mirror. Execution lives in `execution.copy_keeper` (custodial "Modo Maestro" bot wallet).

v1 rules:
- Copy BUYS with `min(leader_notional, max_per_trade, remaining_budget)`, ignoring dust.
- Copy SELLS by fully closing the follower's position in that token (simple, safe mirror).
- Never spend past `max_total`.
"""
from __future__ import annotations

from dataclasses import dataclass

MIN_COPY_USDC = 5.0          # ignore dust: a leader's $2 buy is not worth mirroring
DEFAULT_SLIPPAGE_PCT = 3.0


@dataclass
class CopyConfig:
    max_per_trade: float
    max_total: float
    spent: float = 0.0
    slippage_pct: float = DEFAULT_SLIPPAGE_PCT

    @property
    def remaining(self) -> float:
        return max(0.0, float(self.max_total) - float(self.spent))


def plan_buy(leader_value: float, cfg: CopyConfig) -> float:
    """USDC to spend copying a leader buy (0 => skip). Bounded by per-trade cap and budget."""
    v = float(leader_value or 0.0)
    if v < MIN_COPY_USDC:
        return 0.0
    if cfg.remaining <= 0:
        return 0.0
    return round(min(v, float(cfg.max_per_trade), cfg.remaining), 6)


def decide(trade: dict, cfg: CopyConfig, position_qty: float = 0.0) -> dict:
    """Pure decision for one leader trade. Returns {'action': 'buy'|'sell'|'skip', ...}."""
    side = str((trade or {}).get("side") or "").lower()
    value = float((trade or {}).get("stable_value") or 0.0)
    if side == "buy":
        usdc = plan_buy(value, cfg)
        if usdc <= 0:
            reason = "no_budget" if cfg.remaining <= 0 else "dust_or_cap"
            return {"action": "skip", "reason": reason}
        return {"action": "buy", "usdc": usdc}
    if side == "sell":
        if float(position_qty or 0.0) <= 0:
            return {"action": "skip", "reason": "no_position"}
        return {"action": "sell", "pct": 100.0}
    return {"action": "skip", "reason": "unknown_side"}
