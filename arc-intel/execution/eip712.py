"""EIP-712 typed data for the ArcIntelExecutor order (Permit2 witness).

The user signs ONE message of type `PermitWitnessTransferFrom` whose `witness` commits the order
(poolId, zeroForOne, minOut, recipient, orderNonce). This module is the single source of truth for
the type definitions so the signing UX (Mini App / WalletConnect), the tests and the keeper all
agree byte-for-byte with the on-chain verifier.
"""
from __future__ import annotations

import secrets

PERMIT2 = "0x000000000022D473030F116dDEE9F6B43aC78BA3"

# Must equal ArcIntelExecutor.WITNESS_TYPE_STRING byte-for-byte.
WITNESS_TYPE_STRING = (
    "ArcIntelOrder witness)ArcIntelOrder(bytes32 poolId,bool zeroForOne,uint256 minOut,"
    "address recipient,uint256 orderNonce)TokenPermissions(address token,uint256 amount)"
)

TYPES = {
    "PermitWitnessTransferFrom": [
        {"name": "permitted", "type": "TokenPermissions"},
        {"name": "spender", "type": "address"},
        {"name": "nonce", "type": "uint256"},
        {"name": "deadline", "type": "uint256"},
        {"name": "witness", "type": "ArcIntelOrder"},
    ],
    "TokenPermissions": [
        {"name": "token", "type": "address"},
        {"name": "amount", "type": "uint256"},
    ],
    "ArcIntelOrder": [
        {"name": "poolId", "type": "bytes32"},
        {"name": "zeroForOne", "type": "bool"},
        {"name": "minOut", "type": "uint256"},
        {"name": "recipient", "type": "address"},
        {"name": "orderNonce", "type": "uint256"},
    ],
}

#  Permit2's EIP-712 domain (no `version`); chainId + verifyingContract bind the signature.
DOMAIN_NAME = "Permit2"


def new_nonce() -> int:
    return secrets.randbits(62)  # fits a signed 64-bit SQLite INTEGER; unique enough per user


def min_out_from_floor(price: float, qty: float, floor_pct: float) -> int:
    """Worst acceptable output. floor_pct = accepted drop vs current price (30 => -30%).
    For 'exit at any price' pass a very large floor_pct (e.g. 99)."""
    if price <= 0 or qty <= 0:
        raise ValueError("bad_price_or_qty")
    return int(qty * price * max(0.0, 1.0 - float(floor_pct) / 100.0))


def order_typed_data(chain_id: int, executor: str, token_in: str, amount_in: int,
                     permit_nonce: int, deadline: int, pool_id: str, zero_for_one: bool,
                     min_out: int, recipient: str, order_nonce: int) -> dict:
    """The exact payload a wallet signs with eth_signTypedData_v4."""
    return {
        "types": TYPES,
        "primaryType": "PermitWitnessTransferFrom",
        "domain": {"name": DOMAIN_NAME, "chainId": int(chain_id), "verifyingContract": PERMIT2},
        "message": {
            "permitted": {"token": token_in, "amount": int(amount_in)},
            "spender": executor,
            "nonce": int(permit_nonce),
            "deadline": int(deadline),
            "witness": {
                "poolId": pool_id,
                "zeroForOne": bool(zero_for_one),
                "minOut": int(min_out),
                "recipient": recipient,
                "orderNonce": int(order_nonce),
            },
        },
    }
