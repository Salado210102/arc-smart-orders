"""Session keeper (Opción 3): execute armed buy intents with the user's authorized session key.

Dormant unless ARC_INTEL_EXECUTOR + ARC_INTEL_RELAYER_KEY + ARC_INTEL_SESSION_ENC_KEY are set. The
user authorized the session once; here the keeper signs an `ArcIntelSessionOrder` with the decrypted
session key and submits `executeWithSession` — **no per-order user signature**.
"""
from __future__ import annotations

EXECUTE_SESSION_SIGFN = (
    "executeWithSession((address,(address,address,uint24,int24,address),bool,uint256,uint256,"
    "address,uint256,uint256),bytes)"
)


def session_order_arg(order: dict, sig: str) -> str:
    k = order["key"]
    z4o = "true" if order["zero_for_one"] else "false"
    return (f"(({order['user']},({k['currency0']},{k['currency1']},{k['fee']},{k['tick_spacing']},"
            f"{k['hooks']}),{z4o},{order['amount_in']},{order['min_out']},{order['recipient']},"
            f"{order['order_nonce']},{order['deadline']}),{sig})")


def _default_submit(po, intent, sig, executor, rpc, relayer) -> str:
    import os
    import subprocess
    order = {
        "user": po["user"], "key": intent["key"], "zero_for_one": intent["zero_for_one"],
        "amount_in": intent["amount_in"], "min_out": intent["min_out"],
        "recipient": intent["recipient"], "order_nonce": po["order_nonce"], "deadline": po["deadline"],
    }
    arg = session_order_arg(order, sig)
    cast = os.environ.get("ARC_INTEL_CAST", "cast")
    r = subprocess.run(
        [cast, "send", executor, EXECUTE_SESSION_SIGFN, arg, "--rpc-url", rpc,
         "--private-key", relayer],
        capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-200:])
    for line in r.stdout.splitlines():
        if line.strip().startswith("transactionHash"):
            return line.split()[-1]
    return ""


def run_session_keeper(store, *, submit=None, now=None, enc_key=None, executor=None, relayer=None,
                       rpc=None, chain_id=None, logger=None, limit: int = 50) -> dict:
    import json
    import os
    import time
    from execution import sessions as S
    if now is None:
        now = int(time.time())
    executor = executor or os.environ.get("ARC_INTEL_EXECUTOR")
    relayer = relayer or os.environ.get("ARC_INTEL_RELAYER_KEY")
    rpc = rpc or os.environ.get("ARC_RPC", "https://rpc.mainnet.arc.io")
    chain_id = int(chain_id or os.environ.get("ARC_INTEL_CHAIN_ID", "5042"))
    enc_key = enc_key or os.environ.get("ARC_INTEL_SESSION_ENC_KEY")
    if not (executor and relayer and enc_key):
        return {"skipped": "not_configured", "submitted": 0, "failed": 0}
    submit = submit or _default_submit
    submitted = failed = 0
    for po in store.armed_orders("session", now, limit=limit):
        try:
            intent = json.loads(po.get("sig_payload") or "{}")
        except ValueError:
            continue
        if intent.get("mode") != "session":
            continue
        sess = store.get_session(po["chat"], intent.get("pool_id", ""), intent.get("token_in", ""))
        if not sess:
            continue
        try:
            pk = S.decrypt_secret(sess["enc_secret"], enc_key)
            td = S.session_order_typed_data(
                chain_id=chain_id, executor=executor, user=po["user"], key=intent["key"],
                zero_for_one=intent["zero_for_one"], amount_in=int(intent["amount_in"]),
                min_out=int(intent["min_out"]), recipient=intent["recipient"],
                order_nonce=int(po["order_nonce"]), deadline=int(po["deadline"]))
            sig = S.sign_session_order(pk, td)
            txh = submit(po, intent, sig, executor, rpc, relayer) or ""
            store.mark_executed(po["id"], txh)
            submitted += 1
            if logger:
                logger({"session_keeper": "executed", "id": po["id"], "tx": txh})
        except Exception as e:
            store.bump_attempt(po["id"])
            failed += 1
            if logger:
                logger({"session_keeper": "failed", "id": po["id"], "err": str(e)[:160]})
    return {"submitted": submitted, "failed": failed}
