"""Token Safety Score (0-100) + verdict (SAFE / WARN / DANGER).

Aggregates the pieces we already have into ONE number the user can trust: contract risk
(honeypot/mint/pause/tax/proxy/owner), creator reputation (rug history), liquidity, age,
thin-market and holder concentration. Pure + testable; holder concentration is best-effort (PG).
"""
from __future__ import annotations

ZERO = "0x" + "0" * 40


def safety_score(*, risk: dict | None = None, creator_rep: dict | None = None,
                 liquidity_usd: float = 0.0, age_blocks: int = 0, thin_market=None,
                 holders_top10_pct: float | None = None, lp_locked: bool | None = None) -> dict:
    risk = risk or {}
    rep = creator_rep or {}
    score = 100
    factors: list = []

    def cut(name, amount, detail=None):
        nonlocal score
        score -= int(amount)
        factors.append({"factor": name, "delta": -int(amount), "detail": detail})

    def add(name, amount, detail=None):
        nonlocal score
        score += int(amount)
        factors.append({"factor": name, "delta": int(amount), "detail": detail})

    #  Contract
    lvl = risk.get("level")
    reasons = risk.get("reasons") or []
    if lvl == "high":
        cut("contract_high", 45)
    elif lvl == "medium":
        cut("contract_medium", 20)
    if risk.get("honeypot_hint"):
        cut("honeypot", 15)
    if "upgradeable_proxy" in reasons:
        cut("upgradeable_proxy", 20)
    owner = (risk.get("owner") or "")
    if owner and owner.lower() != ZERO:
        cut("owner_active", 8)

    #  Creator reputation
    if rep.get("created") and rep.get("dumped"):
        rate = float(rep.get("rug_rate") or 0.0)
        cut("creator_dump", round(30 * rate), round(rate, 2))

    #  Liquidity
    liq = float(liquidity_usd or 0.0)
    if liq <= 0:
        cut("no_liquidity", 25)
    elif liq < 5000:
        cut("low_liquidity", 15, liq)
    elif liq < 20000:
        cut("thin_liquidity", 6, liq)

    #  Age / market
    if age_blocks and age_blocks < 3000:
        cut("very_new", 10)
    if thin_market:
        cut("thin_market", 20, thin_market)

    #  Holder concentration
    if holders_top10_pct is not None:
        if holders_top10_pct >= 80:
            cut("top10_concentration", 20, holders_top10_pct)
        elif holders_top10_pct >= 60:
            cut("top10_concentration", 10, holders_top10_pct)

    if lp_locked is True:
        add("lp_locked", 5)

    score = max(0, min(100, score))
    verdict = "SAFE" if score >= 70 else ("WARN" if score >= 40 else "DANGER")
    return {"score": score, "verdict": verdict, "factors": factors}


def holders_top10_pct(storage, token: str, total_supply: float) -> float | None:
    """Top-10 holders share of supply (%) from token_transfers. Best-effort (None on failure)."""
    token = (token or "").lower()
    if not total_supply or total_supply <= 0:
        return None
    conn = storage.pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT sum(d) FROM ("
                "  SELECT to_addr AS a, sum((value)::numeric) AS d FROM token_transfers "
                "   WHERE lower(token)=%s GROUP BY 1"
                "  UNION ALL"
                "  SELECT from_addr AS a, -sum((value)::numeric) AS d FROM token_transfers "
                "   WHERE lower(token)=%s GROUP BY 1) x GROUP BY a HAVING sum(d) > 0 "
                "ORDER BY 2 DESC LIMIT 10", (token, token))
            rows = [float(r[0] or 0) for r in cur.fetchall()]
        if not rows:
            return None
        return sum(rows) / float(total_supply) * 100.0
    except Exception:
        return None
    finally:
        storage.pool.putconn(conn)
