"""Session keys (Opción 3): generate, encrypt-at-rest, and sign scoped orders.

The user authorizes a session key once (on-chain, via ArcIntelExecutorV2.authorizeSession). The
keeper then signs `ArcIntelSessionOrder`s with that key so buys/sells need **no per-order user
signature**. The key is stored **encrypted** (Fernet); it is a scoped hot key, never a master key.

Mirrors `ArcIntelExecutorV2` byte-for-byte for the EIP-712 domain/types.
"""
from __future__ import annotations

import os

DOMAIN_NAME = "ArcIntelExecutor"
DOMAIN_VERSION = "2"

TYPES = {
    "EIP712Domain": [
        {"name": "name", "type": "string"},
        {"name": "version", "type": "string"},
        {"name": "chainId", "type": "uint256"},
        {"name": "verifyingContract", "type": "address"},
    ],
    "PoolKey": [
        {"name": "currency0", "type": "address"},
        {"name": "currency1", "type": "address"},
        {"name": "fee", "type": "uint24"},
        {"name": "tickSpacing", "type": "int24"},
        {"name": "hooks", "type": "address"},
    ],
    "ArcIntelSessionOrder": [
        {"name": "user", "type": "address"},
        {"name": "key", "type": "PoolKey"},
        {"name": "zeroForOne", "type": "bool"},
        {"name": "amountIn", "type": "uint256"},
        {"name": "minOut", "type": "uint256"},
        {"name": "recipient", "type": "address"},
        {"name": "orderNonce", "type": "uint256"},
        {"name": "deadline", "type": "uint256"},
    ],
}


def new_session_key() -> dict:
    """Fresh session keypair: {'address', 'private_key'}."""
    from eth_account import Account
    acct = Account.create()
    return {"address": acct.address, "private_key": "0x" + acct.key.hex().replace("0x", "")}


def session_order_typed_data(*, chain_id: int, executor: str, user: str, key: dict, zero_for_one: bool,
                             amount_in: int, min_out: int, recipient: str, order_nonce: int,
                             deadline: int) -> dict:
    """EIP-712 typed data the session key signs (matches ArcIntelExecutorV2)."""
    return {
        "types": TYPES,
        "primaryType": "ArcIntelSessionOrder",
        "domain": {"name": DOMAIN_NAME, "version": DOMAIN_VERSION, "chainId": int(chain_id),
                   "verifyingContract": executor},
        "message": {
            "user": user,
            "key": {"currency0": key["currency0"], "currency1": key["currency1"],
                    "fee": int(key["fee"]), "tickSpacing": int(key["tick_spacing"]),
                    "hooks": key["hooks"]},
            "zeroForOne": bool(zero_for_one),
            "amountIn": int(amount_in),
            "minOut": int(min_out),
            "recipient": recipient,
            "orderNonce": int(order_nonce),
            "deadline": int(deadline),
        },
    }


def sign_session_order(private_key: str, typed_data: dict) -> str:
    """Sign the typed data with the session key; returns a 0x signature."""
    from eth_account import Account
    from eth_account.messages import encode_typed_data
    signable = encode_typed_data(full_message=typed_data)
    signed = Account.sign_message(signable, private_key=private_key)
    sig = signed.signature
    if isinstance(sig, (bytes, bytearray)):
        return "0x" + sig.hex()
    return sig if str(sig).startswith("0x") else "0x" + str(sig)


def recover_session_signer(typed_data: dict, signature: str) -> str:
    """Recover the signer address (test/verification helper)."""
    from eth_account import Account
    from eth_account.messages import encode_typed_data
    signable = encode_typed_data(full_message=typed_data)
    return Account.recover_message(signable, signature=signature)


# --- encryption at rest (Fernet) -----------------------------------------------------------------

def new_enc_key() -> str:
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()


def encrypt_secret(plaintext: str, key: str | None = None) -> str:
    from cryptography.fernet import Fernet
    key = key or enc_key()
    return Fernet(key.encode()).encrypt(plaintext.encode()).decode()


def decrypt_secret(token: str, key: str | None = None) -> str:
    from cryptography.fernet import Fernet
    key = key or enc_key()
    return Fernet(key.encode()).decrypt(token.encode()).decode()


def enc_key() -> str:
    k = os.environ.get("ARC_INTEL_SESSION_ENC_KEY")
    if not k:
        raise RuntimeError("no_enc_key")
    return k


# --- ABI calldata for the one-time setup txs (the wallet sends these) ----------------------------

def _word(x) -> str:
    return format(int(x) & ((1 << 256) - 1), "064x")


def _addr(a) -> str:
    return (a or "").lower().replace("0x", "").rjust(64, "0")


def _b32(h) -> str:
    return (h or "").lower().replace("0x", "").rjust(64, "0")


def pool_id(key: dict) -> str:
    """keccak256(abi.encode(PoolKey)) — matches keccak256(abi.encode(order.key))."""
    from indexer.token_risk import keccak256
    enc = bytes.fromhex(_addr(key["currency0"]) + _addr(key["currency1"]) + _word(key["fee"])
                        + _word(key["tick_spacing"]) + _addr(key["hooks"]))
    return "0x" + keccak256(enc).hex()


def calldata_approve(spender: str, amount: int) -> str:
    from indexer.token_risk import selector
    return selector("approve(address,uint256)") + _addr(spender) + _word(amount)


def calldata_permit2_approve(token: str, spender: str, amount: int, expiration: int) -> str:
    from indexer.token_risk import selector
    return (selector("approve(address,address,uint160,uint48)") + _addr(token) + _addr(spender)
            + _word(amount) + _word(expiration))


def calldata_authorize_session(session_key: str, pid: str, token_in: str, max_per_order: int,
                               max_total: int, min_out_floor: int, expiry: int) -> str:
    from indexer.token_risk import selector
    return (selector("authorizeSession(address,bytes32,address,uint256,uint256,uint256,uint64)")
            + _addr(session_key) + _b32(pid) + _addr(token_in) + _word(max_per_order)
            + _word(max_total) + _word(min_out_floor) + _word(expiry))


def calldata_revoke_session(session_key: str) -> str:
    from indexer.token_risk import selector
    return selector("revokeSession(address)") + _addr(session_key)
