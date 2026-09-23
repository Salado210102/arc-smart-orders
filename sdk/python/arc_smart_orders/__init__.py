"""arc_smart_orders — lightweight Python SDK for Arc Smart Orders.

Build & sign EIP-712 / Permit2 limit and TWAP orders and submit them to the keeper API.
"""
from __future__ import annotations

from .constants import (
    ARC_MAINNET_CHAIN_ID,
    ARC_TESTNET_CHAIN_ID,
    EURC,
    EXECUTOR,
    KEEPER_API,
    PERMIT2,
    RPC,
    USDC,
    executor_for,
    eurc_for,
    rpc_for,
)
from .client import ArcSmartOrdersClient, from_units, to_units
from .eip712 import (
    DCA_INTENT_TYPES,
    PERMIT_SINGLE_TYPES,
    WITNESS_TYPES,
    dca_message,
    intent_domain,
    limit_message,
    permit2_domain,
    permit_single_message,
    typed_data,
)
from .signer import digest, owner_address, sign_limit_order, sign_twap_order

__version__ = "0.1.0"

__all__ = [
    "ArcSmartOrdersClient",
    "to_units",
    "from_units",
    "ARC_MAINNET_CHAIN_ID",
    "ARC_TESTNET_CHAIN_ID",
    "USDC",
    "EURC",
    "PERMIT2",
    "EXECUTOR",
    "RPC",
    "KEEPER_API",
    "executor_for",
    "eurc_for",
    "rpc_for",
    "WITNESS_TYPES",
    "DCA_INTENT_TYPES",
    "PERMIT_SINGLE_TYPES",
    "permit2_domain",
    "intent_domain",
    "limit_message",
    "dca_message",
    "permit_single_message",
    "typed_data",
    "sign_limit_order",
    "sign_twap_order",
    "owner_address",
    "digest",
]
