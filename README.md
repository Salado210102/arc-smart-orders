# Arc Smart Orders

**Non-custodial limit & TWAP orders for stablecoin FX on Arc (USDC ⇄ EURC).**

Users sign an order **off-chain** (Permit2 + EIP-712). A **keeper** executes it on-chain through a
verified executor contract that **enforces exactly what the user signed**. Funds never leave the
user's wallet until the fill, and the keeper can never redirect the output or fill below the signed
rate.

Built on the proven pattern from [basepump-smart-orders](https://github.com/Salado210102/basepump-smart-orders),
adapted to Arc's stablecoin-native model.

---

## Why Arc fits this

- **USDC is the gas token** → a keeper pays ~\$0.001/tx in USDC, no volatile gas exposure.
- **Instant deterministic finality** → the keeper confirms with a single confirmation.
- **Permit2 is deployed** at the canonical address `0x000000000022D473030F116dDEE9F6B43aC78BA3`.
- **USDC/EURC are the native FX pair** → limit orders and TWAPs on a pegged pair are a natural fit.

## Arc gotchas (baked into this repo)

| Gotcha | What we do |
|---|---|
| **USDC has two interfaces / one balance**: native (18 dec, gas) + ERC-20 (6 dec) at `0x3600…0000` | All Permit2 flows use the **ERC-20 interface (6 decimals)**. Never mix with `msg.value`. |
| **Min base fee 20 gwei**; txs below are **silently dropped** | Keeper sets `maxFeePerGas = max(suggested, 20 gwei)`. |
| `address(0)` value sends revert; blocklist enforced at runtime; reverted value tx still costs gas | We only move **ERC-20** balances, no raw value sends. |
| `PREVRANDAO == 0` (no on-chain randomness) | No randomness assumptions. |
| `block.timestamp` non-decreasing, 1s granularity | Ordering by block number, not timestamp. |
| EIP-7708: native sends emit `Transfer` logs from a system emitter | Indexers must avoid double-counting (18-dec vs 6-dec). |

---

## Architecture

```
   USER (browser/SDK)                     KEEPER (Node)                       ARC
   ─────────────────                      ─────────────                       ───
   sign LIMIT order  ──┐
   (Permit2 + witness) │                  poll ready orders
   sign TWAP order   ──┼──►  order store ─► build swapData ──► OrderExecutor.executeOrder / executeDca
   (PermitSingle +     │      (API/JSON)      (router calldata)        │
    DcaIntent)         │                                              ├─ Permit2 pull (USDC, exact amount)
                       │                                              ├─ call whitelisted swapTarget
                       │                                              ├─ refund leftover to user
                       └─────────────────────────────────────────────┤─ verify minOut / minRate
                                                                      └─ output to user's wallet
```

### Two signing flows
1. **LIMIT (one-shot)** → Permit2 `permitWitnessTransferFrom` with witness `OrderIntent{tokenOut,minOut}`.
   The executor recomputes the witness on-chain → keeper can't redirect or under-fill.
2. **TWAP (recurring)** → Permit2 `AllowanceTransfer` (`PermitSingle`, one signature, many pulls) **plus**
   a signed `DcaIntent{owner, tokenIn, tokenOut, maxAmountIn, minRate, deadline}` verified on **every** part.

The `DcaIntent` domain is `name="ArcSmartOrders", version="1", verifyingContract=executor` — this must
match `OrderExecutor.EIP712_NAME_HASH` / `intentDomain()` in the SDK.

---

## Repo layout

```
contracts/                 Foundry
  src/OrderExecutor.sol        the executor (witness + intent + whitelist)
  src/mocks/MockStableRouter.sol  fixed-rate USDC->EURC router for testnet/local
  test/OrderExecutor.t.sol     11 tests
  script/Deploy.s.sol          deploy to Arc
sdk/                       TypeScript (viem)
  src/index.ts               EIP-712 domains/types + signLimitOrder / signTwapOrder
keeper/                    TypeScript (viem)
  src/index.ts               executes ready orders, 20-gwei floor, USDC gas
.env.example
```

---

## Quickstart

```bash
# 1) Contracts
cd contracts
forge install foundry-rs/forge-std
forge test -vv            # 11 tests

# 2) Deploy on Arc testnet (fund the deployer with testnet USDC: https://faucet.circle.com)
export EXECUTOR_KEEPER=<keeper address>
export EXECUTOR_TARGET=<mock router address, optional>
forge script script/Deploy.s.sol --rpc-url https://rpc.testnet.arc.io --broadcast

# 3) Keeper
cd ../keeper
cp ../.env.example .env   # set KEEPER_PK, EXECUTOR, ROUTER
npm install
npm start
```

Request testnet USDC/EURC at <https://faucet.circle.com> (select **Arc Testnet**).

---

## Roadmap

1. **Wire the real swap venue.** Today the swap leg is a pluggable `swapTarget` (whitelisted by the
   owner). On testnet we use `MockStableRouter`. For production, authorize the real venue
   (Circle **App Kit Swap** router / **StableFX** FxEscrow) via `setAllowedTarget`.
   → *This is the main open question: identify the public on-chain router/venue address.*
2. **Off-chain readiness.** Replace the manual `ready` flag with a real FX price source
   (App Kit quote / StableFX / an oracle) compared against the signed `minOut` / `minRate`.
3. **Agentic track (ERC-8004 identity + ERC-8183 jobs).** Let AI agents register and run these
   orders / settle jobs in USDC — Arc's headline use case.
4. **API + UI** for creating/cancelling orders (like BasePump's order panel).

## Status

Reference implementation — **not audited**. Testnet first.
