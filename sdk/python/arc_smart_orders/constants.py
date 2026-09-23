"""Arc Smart Orders — constants (chains, tokens, executors).

All token amounts are **base units** (USDC/EURC are 6 decimals on Arc).
"""
from __future__ import annotations

ARC_MAINNET_CHAIN_ID = 5042
ARC_TESTNET_CHAIN_ID = 5042002

# Canonical Permit2 (same address across chains).
PERMIT2 = "0x000000000022D473030F116dDEE9F6B43aC78BA3"

# USDC ERC-20 interface (6 decimals) — the native gas asset shares the same balance.
USDC = "0x3600000000000000000000000000000000000000"
EURC = {
    "mainnet": "0xbEf5f6d51CB62b58e6A8f77868681825C6fe21c1",
    "testnet": "0x89B50855Aa3bE2F677cD6303Cec089B5F319D72a",
}

# OrderExecutor (the Permit2 `spender` the user authorizes).
EXECUTOR = {
    "mainnet": "0x9b3a990d1a31Ff5E01ddB8702e10F2529811FDb7",
    "testnet": "0xB19F1193BcC50c2aC0fdD9f1a28F95f7493f6Ee3",
}

RPC = {
    "mainnet": "https://rpc.mainnet.arc.io",
    "testnet": "https://rpc.testnet.arc.io",
}

# Keeper order API (POST /v1/orders, GET /v1/orders/:id).
KEEPER_API = {
    "mainnet": "http://127.0.0.1:8788",
    "testnet": "http://127.0.0.1:8789",
}


def executor_for(chain_id: int) -> str:
    return EXECUTOR["mainnet" if chain_id == ARC_MAINNET_CHAIN_ID else "testnet"]


def eurc_for(chain_id: int) -> str:
    return EURC["mainnet" if chain_id == ARC_MAINNET_CHAIN_ID else "testnet"]


def rpc_for(chain_id: int) -> str:
    return RPC["mainnet" if chain_id == ARC_MAINNET_CHAIN_ID else "testnet"]
