"""Order keeper: submit signed orders on-chain. **Dormant unless configured.**

The executor is permissionless: submitting a user-signed order can never steal or alter its terms
(the signature binds poolId, direction, minOut, recipient and nonce). So the worst a keeper can do
is *not* submit.

Scope:
- BUY orders (`kind='buy'`): submitted as soon as they are signed (they are market/limit buys).
- SELL / protect orders (`kind='sell'`): remain **trigger-driven** (`bot.commands.fire_preorders`).

Requires `ARC_INTEL_EXECUTOR` + `ARC_INTEL_RELAYER_KEY` (a relayer with gas). Without them it is a
no-op, so nothing is ever sent by accident.
"""
from __future__ import annotations

DEFAULT_RPC = "https://rpc.mainnet.arc.io"


def run_keeper(store, *, submit=None, now=None, limit: int = 50, logger=None, on_executed=None,
               executor=None, relayer=None, rpc=None) -> dict:
    """Submit due BUY orders once each. Returns {'skipped'|'submitted'|'failed'}."""
    import os
    import time
    if now is None:
        now = int(time.time())
    executor = executor or os.environ.get("ARC_INTEL_EXECUTOR")
    relayer = relayer or os.environ.get("ARC_INTEL_RELAYER_KEY")
    rpc = rpc or os.environ.get("ARC_RPC", DEFAULT_RPC)
    if not (executor and relayer):
        return {"skipped": "not_configured", "submitted": 0, "failed": 0}
    if submit is None:
        from execution.preorders import submit_execute

        def submit(po):
            return submit_execute(po, executor, rpc, relayer)

    submitted = failed = 0
    for po in store.orders_due("buy", now, limit=limit):
        if not store.claim_order(po["id"]):
            continue  # another keeper already took it
        try:
            txh = submit(po) or ""
            store.mark_executed(po["id"], txh)
            submitted += 1
            if logger:
                logger({"keeper": "executed", "id": po["id"], "tx": txh})
            if on_executed:
                try:
                    on_executed(po, txh)
                except Exception:
                    pass
        except Exception as e:  # revert / RPC error -> back to 'signed' for a later retry
            store.set_preorder_status(po["id"], "signed")
            store.bump_attempt(po["id"])
            failed += 1
            if logger:
                logger({"keeper": "failed", "id": po["id"], "err": str(e)[:160]})
    return {"submitted": submitted, "failed": failed}
