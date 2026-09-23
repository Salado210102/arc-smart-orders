# Arc Testnet — deployments & E2E

**Chain ID** 5042002 · **RPC** https://rpc.testnet.arc.io · **Explorer** https://explorer.testnet.arc.io

## Contracts
| Contract | Address |
|---|---|
| **OrderExecutor** | [`0x9cb011A46A1127202Bc92F48f70Bf7010F1f9B6C`](https://explorer.testnet.arc.io/address/0x9cb011A46A1127202Bc92F48f70Bf7010F1f9B6C) |
| **MockStableRouter** (fixed-rate USDC→EURC, test-only) | [`0xcDeA0D5BcD78dB86D7A5f4E976976400a5b4dffc`](https://explorer.testnet.arc.io/address/0xcDeA0D5BcD78dB86D7A5f4E976976400a5b4dffc) |

- `owner` = `keeper` = `0x3df362854B3981b1367aC2DFa41533386628c977`
- Whitelisted `swapTarget` = MockStableRouter
- Permit2 = `0x000000000022D473030F116dDEE9F6B43aC78BA3` (canonical)
- USDC (ERC-20, 6 dec) = `0x3600000000000000000000000000000000000000`
- EURC (6 dec) = `0x89B50855Aa3bE2F677cD6303Cec089B5F319D72a`

## End-to-end run (2026-09-22)
| Step | Tx |
|---|---|
| Fund MockStableRouter with 10 EURC | [`0x035bdf2c65fa67a0c5748790a0c030cae18999b74ca93b1323c1477c79493184`](https://explorer.testnet.arc.io/tx/0x035bdf2c65fa67a0c5748790a0c030cae18999b74ca93b1323c1477c79493184) |
| Approve Permit2 for USDC (one-time) | [`0x9de71bd86f741476fcd48c54d3e3931e8aba35dad2ca82677c786395bd14f4fc`](https://explorer.testnet.arc.io/tx/0x9de71bd86f741476fcd48c54d3e3931e8aba35dad2ca82677c786395bd14f4fc) |
| **Fill LIMIT 1 USDC → minOut 0.92 EURC** | [`0x98f8459b8635037b64470eb92ace36446f88e5dcbf7232bb9b98dbfcc9c1ca2d`](https://explorer.testnet.arc.io/tx/0x98f8459b8635037b64470eb92ace36446f88e5dcbf7232bb9b98dbfcc9c1ca2d) |

**Result (verified on-chain):** user USDC 20 → 18.941775 · user EURC 10 → 10.92 · router USDC 0 → 1 · router EURC 10 → 9.08
(1 USDC swapped to 0.92 EURC; gas paid in USDC.)

### What the fill proves
- The keeper pulled the **exact** signed amount of USDC from the user via `Permit2.permitWitnessTransferFrom`,
  **enforcing the witness (`tokenOut=EURC`, `minOut`)** — the keeper cannot redirect or under-fill.
- Atomic: pull → swap (whitelisted target) → output to the user, in one transaction.
