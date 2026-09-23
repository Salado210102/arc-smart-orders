# Python SDK — `arc-smart-orders`

Lightweight Python client to **build & sign** Arc Smart Orders (EIP-712 / Permit2) and **submit** them to
the keeper API. Built for quantitative developers: `eth-account` for signing, stdlib for RPC/HTTP (no
`web3.py`).

- Code: [`sdk/python/`](../sdk/python/) · Package: `arc_smart_orders`
- Example: [`sdk/python/examples/submit_limit_order.py`](../sdk/python/examples/submit_limit_order.py)
- Tests: [`sdk/python/tests/test_signing.py`](../sdk/python/tests/test_signing.py)

## Install
```bash
pip install -e ./sdk/python            # from the repo root
# or, standalone:
pip install eth-account
```

## Quick recipe
```python
import os
from arc_smart_orders import ArcSmartOrdersClient, to_units

client = ArcSmartOrdersClient(
    private_key=os.environ["ARC_PK"],
    # chain_id=5042002,                      # Arc testnet (default: mainnet 5042)
    # keeper_url=os.environ.get("KEEPER_API")# default http://127.0.0.1:8788
)

# 1) one-time, costs gas: allow Permit2 to pull USDC from your wallet
client.ensure_permit2_approval()

# 2) sign (0 gas) + submit a LIMIT order: sell 1 USDC for >= 0.90 EURC
resp = client.submit_limit_order(amount_in=to_units("1"), min_out=to_units("0.90"))
order_id = resp["order"]["id"]

# 3) follow the lifecycle until FILLED
final = client.wait_for_fill(order_id)
print(final["status"], final.get("fill_tx"))
```

## Run the tests (verifies signing matches the on-chain types)
```bash
python sdk/python/tests/test_signing.py
# PASS test_digest_is_deterministic
# PASS test_limit_signature_recovers_owner
# PASS test_twap_signatures_recover_owner
```
The tests sign with a known key and **recover the owner** from the signature, so a mismatch in the
EIP-712 domain/types/message will fail loudly.

## Run the example
```bash
export ARC_PK=0x...
export KEEPER_API=https://api.basepump.dev/arc-keeper        # or the testnet endpoint
python sdk/python/examples/submit_limit_order.py --amount 1 --min-out 0.90 --approve
# add --testnet for Arc testnet, --no-submit to build + sign only
```

## Networks

| Network | chain_id | executor | keeper API |
|---|---|---|---|
| **Arc mainnet** | `5042` | `0x9b3a990d1a31Ff5E01ddB8702e10F2529811FDb7` | `https://api.basepump.dev/arc-keeper` |
| **Arc testnet** | `5042002` | `0xB19F1193BcC50c2aC0fdD9f1a28F95f7493f6Ee3` | `https://api.basepump.dev/arc-keeper-testnet` |

- **Mainnet is Beta (dry-run):** no FX venue yet, so a submitted order is accepted but stays `PENDING`
  then `EXPIRED` — no funds move.
- **Testnet is live:** the keeper fills on-chain against the whitelisted `MockStableRouter` → the order
  reaches `FILLED` with a `fill_tx`.

## Order types
- **LIMIT** — one-shot Permit2 `PermitWitnessTransferFrom`; the witness commits `(tokenOut, minOut)`. The
  executor recomputes the witness on-chain, so the keeper can neither redirect the output nor under-fill.
- **TWAP** — Permit2 `PermitSingle` + a signed `DcaIntent` (`minRate` per `1e18`). Use
  `sign_twap_order(...)`.

## Keeper API
- `POST /v1/orders` — body: `{ maker, tokenIn, tokenOut, amountIn, minOut, nonce, deadline, signature }`
- `GET /v1/orders/:id` — returns the order (`status`, `fill_tx`, …)
