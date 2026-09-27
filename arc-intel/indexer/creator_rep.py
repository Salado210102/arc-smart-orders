"""Creator on-chain reputation: has this wallet rugged tokens before?

Uses data we already index (tokens.creator + legs where the creator sold). No external APIs.
A high `rug_rate` (share of a creator's tokens where they dumped) is a strong red flag shown
BEFORE buying — a differentiator the custodial bots don't offer.
"""
from __future__ import annotations


def creator_report(storage, creator: str) -> dict:
    creator = (creator or "").strip().lower()
    if not creator or creator == "0x" + "0" * 40:
        return {}
    conn = storage.pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM tokens WHERE lower(creator)=%s", (creator,))
            created = int(cur.fetchone()[0] or 0)
            if created == 0:
                return {"created": 0, "dumped": 0, "rug_rate": 0.0, "dumped_value": 0.0}
            cur.execute(
                "SELECT count(DISTINCT l.token), coalesce(sum(l.stable_value),0) "
                "FROM legs l JOIN tokens t ON l.token = t.address "
                "WHERE lower(t.creator)=%s AND l.side='sell' AND lower(l.wallet)=%s",
                (creator, creator))
            dumped, dumped_value = cur.fetchone()
    finally:
        storage.pool.putconn(conn)
    dumped = int(dumped or 0)
    dumped_value = float(dumped_value or 0.0)
    return {"created": created, "dumped": dumped,
            "rug_rate": (dumped / created) if created else 0.0,
            "dumped_value": dumped_value}
