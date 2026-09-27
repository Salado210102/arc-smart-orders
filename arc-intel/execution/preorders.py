"""Build the exact payload the user's wallet signs to arm a protective pre-order.

Given the pool (from `pools_v4`) and the amount to sell, this produces:
- the Permit2 permit (token/amount/nonce/deadline),
- the ArcIntelExecutor Order (poolKey, zeroForOne, minOut, recipient, orderNonce, deadline),
- the EIP-712 typed data (via execution.eip712) the wallet signs with eth_signTypedData_v4.

The signature + payload are stored with the pre-order; the keeper later submits
executor.execute(permit, user, order, signature).
"""
from __future__ import annotations

import json
import os
import subprocess

from .eip712 import PERMIT2, order_typed_data

CAST = os.environ.get("ARC_INTEL_CAST", "cast")
EXECUTE_SIGFN = (
    "execute(((address,uint256),uint256,uint256),address,"
    "((address,address,uint24,int24,address),bool,uint256,address,uint256,uint256),bytes)"
)


def zero_for_one_for(token_in: str, currency0: str) -> bool:
    """Selling `token_in`: input side is currency0 -> zeroForOne=true."""
    return (token_in or "").lower() == (currency0 or "").lower()


def build_sign_payload(*, chain_id: int, executor: str, pool_id: str, currency0: str,
                       currency1: str, fee: int, tick_spacing: int, hooks: str, token_in: str,
                       amount_in: int, min_out: int, recipient: str, order_nonce: int,
                       permit_nonce: int, deadline: int) -> dict:
    z4o = zero_for_one_for(token_in, currency0)
    td = order_typed_data(chain_id, executor, token_in, amount_in, permit_nonce, deadline,
                          pool_id, z4o, min_out, recipient, order_nonce)
    return {
        "chainId": int(chain_id),
        "executor": executor,
        "permit2": PERMIT2,
        "poolKey": {"currency0": currency0, "currency1": currency1, "fee": int(fee),
                    "tickSpacing": int(tick_spacing), "hooks": hooks},
        "zeroForOne": z4o,
        "order": {"minOut": int(min_out), "recipient": recipient, "orderNonce": int(order_nonce),
                  "deadline": int(deadline)},
        "permit": {"token": token_in, "amount": int(amount_in), "nonce": int(permit_nonce),
                   "deadline": int(deadline)},
        "typedData": td,
    }


def executor_call_args(preorder: dict) -> tuple:
    """Build the (permit_arg, order_arg) strings for `executor.execute(...)` from a pre-order."""
    p = preorder["sig_payload"]
    if isinstance(p, str):
        p = json.loads(p)
    k, o, pm = p["poolKey"], p["order"], p["permit"]
    z4o = "true" if p["zeroForOne"] else "false"
    permit_arg = f"(({pm['token']},{pm['amount']}),{pm['nonce']},{pm['deadline']})"
    order_arg = (f"(({k['currency0']},{k['currency1']},{k['fee']},{k['tickSpacing']},{k['hooks']}),"
                 f"{z4o},{o['minOut']},{o['recipient']},{o['orderNonce']},{o['deadline']})")
    return permit_arg, order_arg


def submit_execute(preorder: dict, executor: str, rpc: str, relayer_key: str) -> str:
    """Submit the signed order on-chain via the keeper/relayer. Returns the tx hash."""
    if not preorder.get("signature"):
        raise RuntimeError("no_signature")
    permit_arg, order_arg = executor_call_args(preorder)
    r = subprocess.run(
        [CAST, "send", executor, EXECUTE_SIGFN, permit_arg, preorder["user"], order_arg,
         preorder["signature"], "--rpc-url", rpc, "--private-key", relayer_key],
        capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-200:])
    for line in r.stdout.splitlines():
        if line.strip().startswith("transactionHash"):
            return line.split()[-1]
    return ""
