"""Custodial quick wallet (Modo Maestro/Banana).

The bot creates (or imports) a wallet per user and holds its key **encrypted at rest**; it trades
**instantly** on the user's behalf (no per-trade signature). The user can **withdraw** anytime.

⚠️ Trade-off: this is CUSTODIAL — whoever holds the key controls the funds. The key is encrypted
with `ARC_INTEL_SESSION_ENC_KEY` and never leaves the server, but a server compromise = fund loss.
"""
from __future__ import annotations

import os
import secrets

RPC_DEFAULT = "https://rpc.testnet.arc.io"


def _rpc(method, params, rpc=None):
    from indexer.token_risk import _jsonrpc
    return _jsonrpc(rpc or os.environ.get("ARC_RPC", RPC_DEFAULT), method, params, retries=2)


def chain_id() -> int:
    return int(os.environ.get("ARC_INTEL_CHAIN_ID", "5042002"))


def executor_addr() -> str:
    return os.environ.get("ARC_INTEL_EXECUTOR", "")


def _addr(a: str) -> str:
    return (a or "").lower().replace("0x", "").rjust(64, "0")


def _word(x) -> str:
    return format(int(x) & ((1 << 256) - 1), "064x")


def new_wallet() -> dict:
    from eth_account import Account
    a = Account.create()
    return {"address": a.address, "private_key": "0x" + a.key.hex().replace("0x", "")}


def address_of(private_key: str) -> str:
    from eth_account import Account
    return Account.from_key(private_key).address


def erc20_balance(token: str, addr: str, rpc=None) -> int:
    res = _rpc("eth_call", [{"to": token, "data": "0x70a08231" + _addr(addr)}, "latest"], rpc)
    try:
        return int(res, 16) if res and res != "0x" else 0
    except (TypeError, ValueError):
        return 0


def native_balance(addr: str, rpc=None) -> int:
    res = _rpc("eth_getBalance", [addr, "latest"], rpc)
    try:
        return int(res, 16) if res else 0
    except (TypeError, ValueError):
        return 0


def _send(pk: str, to: str, data: str, value: int = 0, gas: int = 300000, rpc=None) -> str:
    """Sign a tx with the custodied key and broadcast it (raw). Returns the tx hash."""
    from eth_account import Account
    rpc = rpc or os.environ.get("ARC_RPC", RPC_DEFAULT)
    acct = Account.from_key(pk)
    nonce = int(_rpc("eth_getTransactionCount", [acct.address, "pending"], rpc) or "0x0", 16)
    gp = int(_rpc("eth_gasPrice", [], rpc) or "0x0", 16) or 1_000_000_000
    tx = {"nonce": nonce, "gasPrice": gp, "gas": int(gas), "to": to, "value": int(value),
          "data": data, "chainId": chain_id()}
    signed = acct.sign_transaction(tx)
    raw = getattr(signed, "raw_transaction", None) or getattr(signed, "rawTransaction")
    if isinstance(raw, str):
        raw = bytes.fromhex(raw.replace("0x", ""))
    return _rpc("eth_sendRawTransaction", ["0x" + raw.hex()], rpc)


def approve_token(pk: str, token: str, spender: str, amount=None, rpc=None) -> str:
    from indexer.token_risk import selector
    amt = (1 << 256) - 1 if amount is None else int(amount)
    data = "0x" + selector("approve(address,uint256)")[2:] + _addr(spender) + _word(amt)
    return _send(pk, token, data, gas=80000, rpc=rpc)


def erc20_allowance(token: str, owner: str, spender: str, rpc=None) -> int:
    from indexer.token_risk import selector
    data = selector("allowance(address,address)")[2:] + _addr(owner) + _addr(spender)
    res = _rpc("eth_call", [{"to": token, "data": "0x" + data}, "latest"], rpc)
    try:
        return int(res, 16) if res and res != "0x" else 0
    except (TypeError, ValueError):
        return 0


def ensure_permit2_approval(pk: str, token: str, rpc=None) -> str | None:
    """Make sure the wallet approved Permit2 for `token` (needed before a swap)."""
    from execution.eip712 import PERMIT2
    owner = address_of(pk)
    if erc20_allowance(token, owner, PERMIT2, rpc) < (1 << 200):
        return approve_token(pk, token, PERMIT2, rpc=rpc)
    return None


def withdraw(pk: str, token: str, to: str, amount_raw: int, rpc=None) -> str:
    from indexer.token_risk import selector
    data = "0x" + selector("transfer(address,uint256)")[2:] + _addr(to) + _word(amount_raw)
    return _send(pk, token, data, gas=120000, rpc=rpc)


def withdraw_native(pk: str, to: str, amount_wei: int, rpc=None) -> str:
    return _send(pk, to, "0x", value=int(amount_wei), gas=21000, rpc=rpc)


def swap(pk: str, *, pool: dict, token_in: str, amount_in: int, min_out: int, recipient: str,
         order_nonce: int, deadline: int, permit_nonce: int | None = None, rpc=None) -> str:
    """Instant swap via ArcIntelExecutor.execute (the bot signs the Permit2 permit + the tx)."""
    from eth_account import Account
    from eth_account.messages import encode_typed_data
    from eth_abi import encode
    from indexer.token_risk import selector
    from execution.eip712 import order_typed_data, PERMIT2
    from execution.preorders import zero_for_one_for
    from execution.sessions import pool_id as compute_pool_id

    ex = executor_addr()
    if not ex:
        raise RuntimeError("no_executor")
    acct = Account.from_key(pk)
    token_in = token_in.lower()
    z4o = zero_for_one_for(token_in, pool["currency0"])
    permit_nonce = permit_nonce if permit_nonce is not None else secrets.randbits(48)
    pid = compute_pool_id(pool)

    # 1) sign the Permit2 permit+witness (EIP-712)
    td = order_typed_data(chain_id(), ex, token_in, int(amount_in), int(permit_nonce), int(deadline),
                          pid, z4o, int(min_out), recipient, int(order_nonce))
    sig = Account.sign_message(encode_typed_data(full_message=td), private_key=pk).signature
    if isinstance(sig, str):
        sig = bytes.fromhex(sig.replace("0x", ""))

    # 2) encode executor.execute(permit, user, order, signature)
    sigfn = ("execute(((address,uint256),uint256,uint256),address,"
             "((address,address,uint24,int24,address),bool,uint256,address,uint256,uint256),bytes)")
    permit = ((token_in, int(amount_in)), int(permit_nonce), int(deadline))
    order = ((pool["currency0"], pool["currency1"], int(pool["fee"]), int(pool["tick_spacing"]),
              pool["hooks"]), z4o, int(min_out), recipient, int(order_nonce), int(deadline))
    types = ["((address,uint256),uint256,uint256)", "address",
             "((address,address,uint24,int24,address),bool,uint256,address,uint256,uint256)", "bytes"]
    data = "0x" + selector(sigfn)[2:] + encode(types, [permit, acct.address, order, sig]).hex()
    return _send(pk, ex, data, gas=700000, rpc=rpc)
