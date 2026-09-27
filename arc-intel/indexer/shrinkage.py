"""Small-sample correction for win-rate / proportions.

Raw win_rate ranks a 8/8 wallet above a 40/45 one; with tiny n the estimate is unreliable.
We provide two standard estimators:
  - Wilson score lower bound (default): an interval bound that penalizes small n.
  - Empirical-Bayes shrinkage toward the population mean with strength k.
"""
from __future__ import annotations

import math

DEFAULT_Z = 1.96


def wilson_lower_bound(wins: int, n: int, z: float = DEFAULT_Z) -> float:
    if n <= 0:
        return 0.0
    p = wins / n
    denom = 1.0 + z * z / n
    centre = p + z * z / (2 * n)
    spread = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (centre - spread) / denom)


def eb_shrink_win_rate(wins: int, n: int, prior_mean: float, prior_strength: float = 10.0) -> float:
    if n + prior_strength <= 0:
        return prior_mean
    return (wins + prior_mean * prior_strength) / (n + prior_strength)


def population_win_rate(wallet_rows: list[dict]) -> float:
    """Aggregate win rate across wallets given rows with win_rate and trades."""
    w = sum(float(r.get("win_rate", 0.0)) * int(r.get("trades", 0)) for r in wallet_rows)
    n = sum(int(r.get("trades", 0)) for r in wallet_rows)
    return (w / n) if n else 0.0
