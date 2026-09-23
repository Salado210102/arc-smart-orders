#!/usr/bin/env python3
"""
Arc Smart Orders — Python signing recipe (verified: produces the SAME signature as the TS SDK).

Signs a one-shot LIMIT order: a Permit2 `PermitWitnessTransferFrom` whose witness commits
`(tokenOut, minOut)`. The OrderExecutor recomputes this witness on-chain, so the keeper cannot
redirect the output or under-fill.

Install:
    pip install eth-account

The signed `signature` is what you pass to the keeper (or to `OrderExecutor.executeOrder`).
"""
from eth_account import Account

# --- inputs ---
PRIVATE_KEY = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"  # owner (user)
CHAIN_ID = 5042002  # Arc testnet (mainnet = 5042)
PERMIT2 = "0x000000000022D473030F116dDEE9F6B43aC78BA3"
USDC = "0x3600000000000000000000000000000000000000"  # ERC-20, 6 decimals
EURC = "0x89B50855Aa3bE2F677cD6303Cec089B5F319D72a"  # 6 decimals
EXECUTOR = "0x9cb011A46A1127202Bc92F48f70Bf7010F1f9B6C"  # the spender the user authorizes

amount_in = 1_000_000  # 1 USDC
min_out = 900_000     # 0.90 EURC (the limit)
nonce = 2
deadline = 1_790_000_000

# --- EIP-712 (must match the OrderExecutor / TS SDK exactly) ---
domain = {"name": "Permit2", "chainId": CHAIN_ID, "verifyingContract": PERMIT2}
types = {
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
message = {
    "permitted": {"token": USDC, "amount": amount_in},
    "spender": EXECUTOR,
    "nonce": nonce,
    "deadline": deadline,
    "witness": {"tokenOut": EURC, "minOut": min_out},
}

full_message = {
    "types": types,
    "primaryType": "PermitWitnessTransferFrom",
    "domain": domain,
    "message": message,
}

signed = Account.sign_typed_data(PRIVATE_KEY, full_message=full_message)
print("owner    :", Account.from_key(PRIVATE_KEY).address)
print("signature:", "0x" + signed.signature.hex())
