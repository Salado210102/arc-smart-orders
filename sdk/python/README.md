# arc-smart-orders · Python SDK

Lightweight Python client for **Arc Smart Orders** — build & sign **EIP-712 / Permit2** limit and TWAP
orders and submit them to the keeper's `POST /v1/orders` API. Designed for quantitative developers.

- **Signing**: `eth-account` (EIP-712; no `web3.py` required).
- **RPC / HTTP**: stdlib only (`urllib`) — read balances/allowance and send the one-time Permit2 approve.
- **No private keys leave your machine** — the keeper only ever receives the signed order + signature.

> Token amounts are **base units** (USDC/EURC are 6 decimals on Arc). Use `to_units("1.5")`.

## Install
```bash
pip install -e ./sdk/python            # from the repo root
# or, standalone:
pip install eth-account
```

## Quickstart
```python
import os
from arc_smart_orders import ArcSmartOrdersClient, to_units

client = ArcSmartOrdersClient(
    private_key=os.environ["ARC_PK"],          # Arc mainnet (5042)
    # keeper_url=os.environ.get("KEEPER_API"),  # default http://127.0.0.1:8788
)

# 1) one-time, costs gas: allow Permit2 to pull USDC
client.ensure_permit2_approval()

# 2) sign (0 gas) + submit a LIMIT order: sell 1 USDC for >= 0.90 EURC
resp = client.submit_limit_order(amount_in=to_units("1"), min_out=to_units("0.90"))
order_id = resp["order"]["id"]

# 3) follow the lifecycle
final = client.wait_for_fill(order_id)
print(final["status"], final.get("fill_tx"))
```

Run the example:
```bash
export ARC_PK=0x...
export KEEPER_API=http://127.0.0.1:8788
python sdk/python/examples/submit_limit_order.py --amount 1 --min-out 0.90 --approve
```

## API

`ArcSmartOrdersClient(private_key, *, chain_id=5042, rpc_url=None, keeper_url=None, executor=None, token_in=USDC, token_out=EURC)`

| Method | Description |
|---|---|
| `usdc_balance()` / `erc20_balance(token)` | ERC-20 balance (base units) |
| `permit2_allowance()` | current Permit2 allowance |
| `ensure_permit2_approval()` | one-time `approve(Permit2, max)`; returns tx hash or `None` |
| `sign_limit_order(amount_in, min_out, nonce=?, deadline=?)` | EIP-712 signature + typed data |
| `submit_order(payload)` | `POST /v1/orders` |
| `submit_limit_order(amount_in, min_out, ...)` | validate (balance + allowance) → sign → POST |
| `get_order(id)` | `GET /v1/orders/:id` |
| `wait_for_fill(id, timeout=180)` | poll until `FILLED` / `FAILED` / `EXPIRED` |

Low-level building blocks are exported too: `WITNESS_TYPES`, `permit2_domain`, `intent_domain`,
`DCA_INTENT_TYPES`, `sign_limit_order`, `sign_twap_order`, `digest`.

## Order types

- **LIMIT** — one-shot Permit2 `PermitWitnessTransferFrom`; the witness commits `(tokenOut, minOut)`.
  The executor recomputes the witness on-chain, so the keeper cannot redirect the output or under-fill.
- **TWAP** — Permit2 `PermitSingle` (AllowanceTransfer) + a signed `DcaIntent` (`minRate` per `1e18`).
  Use `sign_twap_order(...)`.

The EIP-712 domain/types match the on-chain `OrderExecutor` and the TypeScript SDK byte-for-byte
(verified by `sdk/python/tests/test_signing.py`).

## Status
The order engine runs in **dry-run** on Arc mainnet (no FX venue yet): submitted orders are accepted and
stored by the keeper but only fill once a swap venue is wired. On **testnet** fills are live.

## License
MIT
