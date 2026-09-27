"""Wallet tracking: for each linked (read-only) address, auto-follow the indexed tokens it holds.

Distinct from `execution.positions` (which only knows fills made through OUR executor): here the
user may have bought anywhere, so we query the token balance on-chain directly.

Privacy: only the public address is stored (never keys). `/unlink_wallet` removes the link and the
auto-generated subscriptions; manual subscriptions are left intact.
"""
from __future__ import annotations


def candidate_tokens(storage, address: str, limit: int = 200) -> list:
    """Indexed tokens this address has traded (bounded) — the set we check balances for."""
    conn = storage.pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT token FROM legs WHERE wallet=%s LIMIT %s",
                        (address.lower(), int(limit)))
            return [r[0] for r in cur.fetchall() if r[0]]
    except Exception:
        return []
    finally:
        storage.pool.putconn(conn)


def head_block(storage) -> int:
    conn = storage.pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT max(block) FROM legs")
            return int(cur.fetchone()[0] or 0)
    except Exception:
        return 0
    finally:
        storage.pool.putconn(conn)


def scan_wallets(storage, store, balance_fn=None, head: int | None = None,
                 max_tokens: int = 60) -> dict:
    """Auto-subscribe tokens held (>0); auto-unsubscribe tokens at 0. Never touches manual subs.
    A failed balance call (None) changes nothing."""
    from . import tokenmeta
    balance_fn = balance_fn or tokenmeta.erc20_balance_raw
    if head is None:
        head = head_block(storage)
    new = dropped = 0
    wallets = store.list_linked_wallets()
    for chat, addr in wallets:
        for tok in candidate_tokens(storage, addr)[:max_tokens]:
            bal = balance_fn(addr, tok)
            if bal is None:
                continue
            if bal > 0:
                if store.add_auto_sub(chat, tok, now_block=head):
                    new += 1
            else:
                if store.remove_auto_sub(chat, tok):
                    dropped += 1
    return {"wallets": len(wallets), "new_subs": new, "dropped_subs": dropped, "head": head}
