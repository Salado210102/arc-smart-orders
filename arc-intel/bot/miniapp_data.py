"""PG-backed loaders for the Mini App read endpoints (thin glue over miniapp_api).

Mirrors the data gathering in `telegram.check_token` but returns structured data. PG is only
touched here; `miniapp_api` stays pure/testable.
"""
from __future__ import annotations

from . import miniapp_api, tokenmeta

BLOCKS_24H = 166153


def latest_price(storage, token) -> float:
    token = (token or "").lower()
    conn = storage.pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT price FROM legs WHERE token=%s ORDER BY block DESC LIMIT 1", (token,))
            r = cur.fetchone()
            return float(r[0]) if r and r[0] is not None else 0.0
    finally:
        storage.pool.putconn(conn)


def load_token_card(storage, token, head_block=None) -> dict:
    from indexer.alerts import is_thin_market
    token = (token or "").lower()
    conn = storage.pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT symbol,name,creator,launchpad,pool_id FROM tokens "
                        "WHERE address=%s LIMIT 1", (token,))
            row = cur.fetchone()
            symbol = name = creator = launchpad = None
            if row:
                symbol, name, creator, launchpad, _pool = row
            cur.execute("SELECT block_number, topics FROM launchpad_events "
                        "WHERE event_name='TokenCreated' AND token=%s LIMIT 1", (token,))
            ev = cur.fetchone()
            created_block = int(ev[0]) if ev else None
            if ev and not creator and ev[1]:
                parts = ev[1].split(",")
                if len(parts) >= 3:
                    creator = "0x" + parts[2][-40:]
            cur.execute("SELECT count(*), count(DISTINCT wallet), min(block), max(block) "
                        "FROM legs WHERE token=%s", (token,))
            n, w, first_blk, _last = cur.fetchone()
            cur.execute("SELECT max(block) FROM legs")
            head = int(cur.fetchone()[0] or 0) if head_block is None else int(head_block)
            cur.execute("SELECT coalesce(sum(stable_value),0) FROM legs "
                        "WHERE token=%s AND block >= %s", (token, head - BLOCKS_24H))
            vol24 = float(cur.fetchone()[0] or 0)
    finally:
        storage.pool.putconn(conn)

    n = int(n or 0)
    w = int(w or 0)
    if not symbol:
        symbol = tokenmeta.rpc_symbol(token) or ""
    supply = tokenmeta.rpc_total_supply(token)
    dec = tokenmeta.rpc_decimals(token)
    supply_h = supply / (10 ** dec) if supply else 0.0
    price = latest_price(storage, token)
    first = int(first_blk) if first_blk else None
    ob = created_block or first
    age = (head - ob) if ob else 0
    thin = is_thin_market(n, w, age, no_trade_blocks=100000) if ob else None
    rep = {}
    if creator:
        try:
            from indexer.creator_rep import creator_report
            rep = creator_report(storage, creator)
        except Exception:
            rep = {}
    return miniapp_api.build_token_card(
        address=token, symbol=symbol or "", name=name or "", launchpad=launchpad or "",
        creator=creator or "", created_block=created_block, head_block=head, swaps=n, wallets=w,
        vol24=vol24, price=price, supply=supply_h, thin_reason=thin, creator_rep=rep)


def load_pool(storage, token) -> dict | None:
    """The v4 pool whose currency0 or currency1 is `token`, or None."""
    token = (token or "").lower()
    conn = storage.pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pool_id, currency0, currency1, fee, tick_spacing, hooks "
                        "FROM pools_v4 WHERE lower(currency0)=%s OR lower(currency1)=%s LIMIT 1",
                        (token, token))
            r = cur.fetchone()
            if not r:
                return None
            return {"pool_id": r[0], "currency0": (r[1] or "").lower(),
                    "currency1": (r[2] or "").lower(), "fee": int(r[3]),
                    "tick_spacing": int(r[4]), "hooks": (r[5] or "").lower()}
    finally:
        storage.pool.putconn(conn)


def price_fn(storage):
    return lambda token: latest_price(storage, token)


def balance_fn_for(holder: str):
    """On-chain token balance (float) for `holder`, or None on RPC failure."""
    def _bal(token):
        dec = tokenmeta.rpc_decimals(token)
        raw = tokenmeta.erc20_balance_raw(holder, token)
        if raw is None:
            return None
        return raw / (10 ** dec)
    return _bal
