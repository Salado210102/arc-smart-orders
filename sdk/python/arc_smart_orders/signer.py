"""Signing helpers (EIP-712) built on eth-account."""
from __future__ import annotations

from typing import Any, Dict, Tuple

from eth_account import Account
from eth_account.messages import _hash_eip191_message, encode_typed_data

from . import eip712


def owner_address(private_key: str) -> str:
    return Account.from_key(private_key).address


def sign_typed_data(private_key: str, full_message: Dict[str, Any]) -> str:
    """Sign an EIP-712 ``full_message`` and return a ``0x``-prefixed 65-byte signature."""
    signed = Account.sign_typed_data(private_key, full_message=full_message)
    sig = signed.signature.hex()
    return sig if sig.startswith("0x") else "0x" + sig


def digest(full_message: Dict[str, Any]) -> str:
    """The EIP-712 message hash (``keccak256('\\x19\\x01' || domainSeparator || hashStruct)``)."""
    return "0x" + _hash_eip191_message(encode_typed_data(full_message=full_message)).hex()


def sign_limit_order(
    private_key: str,
    *,
    chain_id: int,
    spender: str,
    token_in: str,
    token_out: str,
    amount_in: int,
    min_out: int,
    nonce: int,
    deadline: int,
) -> Tuple[str, Dict[str, Any]]:
    """Sign a one-shot LIMIT order (Permit2 witness). Returns ``(signature, typed_data)``."""
    full = eip712.typed_data(
        "PermitWitnessTransferFrom",
        eip712.permit2_domain(chain_id),
        eip712.WITNESS_TYPES,
        eip712.limit_message(token_in, amount_in, spender, nonce, deadline, token_out, min_out),
    )
    return sign_typed_data(private_key, full), full


def sign_twap_order(
    private_key: str,
    *,
    chain_id: int,
    spender: str,
    token_in: str,
    token_out: str,
    max_amount_in: int,
    min_rate: int,
    deadline: int,
    permit_nonce: int,
    sig_deadline: int,
) -> Tuple[str, str, Dict[str, Any], Dict[str, Any]]:
    """Sign the AllowanceTransfer permit + the recurring DcaIntent.

    Returns ``(permit_signature, intent_signature, permit_typed_data, intent_typed_data)``.
    """
    owner = owner_address(private_key)

    permit_full = eip712.typed_data(
        "PermitSingle",
        eip712.permit2_domain(chain_id),
        eip712.PERMIT_SINGLE_TYPES,
        eip712.permit_single_message(token_in, max_amount_in, deadline, permit_nonce, spender, sig_deadline),
    )
    intent_full = eip712.typed_data(
        "DcaIntent",
        eip712.intent_domain(chain_id, spender),
        eip712.DCA_INTENT_TYPES,
        eip712.dca_message(owner, token_in, token_out, max_amount_in, min_rate, deadline),
    )
    return (
        sign_typed_data(private_key, permit_full),
        sign_typed_data(private_key, intent_full),
        permit_full,
        intent_full,
    )
