"""EIP-712 domains and type definitions — must match the OrderExecutor / TS SDK byte-for-byte.

Two order shapes:

* LIMIT   — a one-shot Permit2 ``PermitWitnessTransferFrom`` whose witness commits ``(tokenOut, minOut)``.
* TWAP    — a Permit2 ``PermitSingle`` (AllowanceTransfer) **plus** a signed ``DcaIntent``.
"""
from __future__ import annotations

from typing import Any, Dict

from .constants import PERMIT2


# --------------------------------------------------------------------- Permit2 domain
def permit2_domain(chain_id: int) -> Dict[str, Any]:
    return {"name": "Permit2", "chainId": chain_id, "verifyingContract": PERMIT2}


# --------------------------------------------------------------------- LIMIT (witness)
WITNESS_TYPES: Dict[str, Any] = {
    "PermitWitnessTransferFrom": [
        {"name": "permitted", "type": "TokenPermissions"},
        {"name": "spender", "type": "address"},
        {"name": "nonce", "type": "uint256"},
        {"name": "deadline", "type": "uint256"},
        {"name": "witness", "type": "OrderIntent"},
    ],
    "TokenPermissions": [
        {"name": "token", "type": "address"},
        {"name": "amount", "type": "uint256"},
    ],
    "OrderIntent": [
        {"name": "tokenOut", "type": "address"},
        {"name": "minOut", "type": "uint256"},
    ],
}


def limit_message(
    token_in: str, amount_in: int, spender: str, nonce: int, deadline: int, token_out: str, min_out: int
) -> Dict[str, Any]:
    return {
        "permitted": {"token": token_in, "amount": int(amount_in)},
        "spender": spender,
        "nonce": int(nonce),
        "deadline": int(deadline),
        "witness": {"tokenOut": token_out, "minOut": int(min_out)},
    }


# --------------------------------------------------------------------- TWAP (intent)
def intent_domain(chain_id: int, executor: str) -> Dict[str, Any]:
    """Our own EIP-712 domain for the recurring DcaIntent."""
    return {"name": "ArcSmartOrders", "version": "1", "chainId": chain_id, "verifyingContract": executor}


DCA_INTENT_TYPES: Dict[str, Any] = {
    "DcaIntent": [
        {"name": "owner", "type": "address"},
        {"name": "tokenIn", "type": "address"},
        {"name": "tokenOut", "type": "address"},
        {"name": "maxAmountIn", "type": "uint256"},
        {"name": "minRate", "type": "uint256"},
        {"name": "deadline", "type": "uint256"},
    ],
}

PERMIT_SINGLE_TYPES: Dict[str, Any] = {
    "PermitSingle": [
        {"name": "details", "type": "PermitDetails"},
        {"name": "spender", "type": "address"},
        {"name": "sigDeadline", "type": "uint256"},
    ],
    "PermitDetails": [
        {"name": "token", "type": "address"},
        {"name": "amount", "type": "uint160"},
        {"name": "expiration", "type": "uint48"},
        {"name": "nonce", "type": "uint48"},
    ],
}


def dca_message(
    owner: str, token_in: str, token_out: str, max_amount_in: int, min_rate: int, deadline: int
) -> Dict[str, Any]:
    return {
        "owner": owner,
        "tokenIn": token_in,
        "tokenOut": token_out,
        "maxAmountIn": int(max_amount_in),
        "minRate": int(min_rate),
        "deadline": int(deadline),
    }


def permit_single_message(token: str, amount: int, expiration: int, nonce: int, spender: str, sig_deadline: int) -> Dict[str, Any]:
    return {
        "details": {"token": token, "amount": int(amount), "expiration": int(expiration), "nonce": int(nonce)},
        "spender": spender,
        "sigDeadline": int(sig_deadline),
    }


def typed_data(primary_type: str, domain: Dict[str, Any], types: Dict[str, Any], message: Dict[str, Any]) -> Dict[str, Any]:
    """Assemble the ``full_message`` dict accepted by eth_account's ``encode_typed_data``."""
    return {"primaryType": primary_type, "domain": domain, "types": types, "message": message}
