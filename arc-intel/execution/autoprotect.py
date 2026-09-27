"""Auto-Protect: when a RISK alert fires for a token a user HOLDS (in the bot wallet) and the user
has auto-protect ON, sell it automatically. Reuses the custodial quick wallet (bot signs).

Dormant unless a custody wallet + ARC_INTEL_SESSION_ENC_KEY (+ RPC) are configured.
"""
from __future__ import annotations

RISK = ("dev_sell", "compound", "liquidity_removal")


def sell_for_holders(store, storage, token, *, pct: float = 100.0, floor_pct: float = 30.0,
                     enc_key=None, rpc=None, logger=None) -> int:
    import os
    import time
    from execution import custody as C
    from execution.eip712 import new_nonce
    from execution.sessions import decrypt_secret
    from bot import tokenmeta
    from bot.miniapp_data import load_pool, latest_price

    token = (token or "").lower()
    enc_key = enc_key or os.environ.get("ARC_INTEL_SESSION_ENC_KEY")
    rpc = rpc or os.environ.get("ARC_RPC")
    if not (token and enc_key):
        return 0
    pool = load_pool(storage, token)
    if not pool:
        return 0
    price = latest_price(storage, token)
    dec = tokenmeta.rpc_decimals(token)
    sold = 0
    for s in store.list():
        chat = s["chat_id"]
        try:
            if store.get_state(f"autoprotect:{chat}", "1") != "1":
                continue
            if token not in store.list_holdings(chat):
                continue
            c = store.get_custody(chat)
            if not c:
                continue
            bal = C.erc20_balance(token, c["address"])
            if bal <= 0:
                continue
            amount_in = int(bal) if pct >= 100 else int(bal * pct / 100.0)
            min_out = 0
            if price > 0:
                min_out = int((amount_in / (10 ** dec)) * price
                              * max(0.0, 1.0 - floor_pct / 100.0) * 1e6)
            pk = decrypt_secret(c["enc_secret"], enc_key)
            C.ensure_permit2_approval(pk, token)
            txh = C.swap(pk, pool=pool, token_in=token, amount_in=amount_in, min_out=min_out,
                         recipient=c["address"], order_nonce=new_nonce(),
                         deadline=int(time.time()) + 300, rpc=rpc)
            sold += 1
            if logger:
                logger({"autoprotect": "sold", "chat": chat, "token": token, "tx": txh})
        except Exception as e:
            if logger:
                logger({"autoprotect": "failed", "chat": chat, "token": token, "err": str(e)[:120]})
    return sold


def on_alerts(store, storage, alerts, *, logger=None) -> int:
    total = 0
    for a in alerts:
        kind = getattr(a, "kind", None) or (a.get("kind") if isinstance(a, dict) else None)
        token = getattr(a, "token", None) or (a.get("token") if isinstance(a, dict) else None)
        if kind in RISK and token:
            total += sell_for_holders(store, storage, token, logger=logger)
    return total
