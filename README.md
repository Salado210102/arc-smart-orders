# Arc Smart Orders

**Non-custodial limit & TWAP orders for stablecoin FX on Arc (USDC ⇄ EURC).**

Users sign an order **off-chain** (Permit2 + EIP-712). A **keeper** executes it on-chain through a
verified executor contract that **enforces exactly what the user signed**. Funds never leave the
user's wallet until the fill, and the keeper can never redirect the output or fill below the signed
rate.

Built on the proven pattern from [basepump-smart-orders](https://github.com/Salado210102/basepump-smart-orders),
adapted to Arc's stablecoin-native model.

- Executor contract: [`contracts/src/OrderExecutor.sol`](contracts/src/OrderExecutor.sol)
- SDK (signing): [`sdk/src/index.ts`](sdk/src/index.ts)
- Keeper: [`keeper/src/index.ts`](keeper/src/index.ts)

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

## How it works

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

### Flow 1 — LIMIT (one-shot) → Permit2 SignatureTransfer **with a witness**

The user signs a Permit2 `PermitWitnessTransferFrom` whose **witness** commits the exact output and
a minimum:

```
PermitWitnessTransferFrom(TokenPermissions permitted,address spender,uint256 nonce,uint256 deadline,OrderIntent witness)
OrderIntent(address tokenOut, uint256 minOut)
TokenPermissions(address token, uint256 amount)
```

The executor **recomputes the witness on-chain** from the actual `tokenOut`/`minOut` it is about to
execute, so a keeper **cannot redirect the output nor fill below the signed minimum**.

```solidity
function executeOrder(
    IPermit2.PermitTransferFrom calldata permit,
    address orderOwner,
    bytes calldata permitSignature,
    address swapTarget,          // whitelisted router/venue
    bytes calldata swapData,     // pre-built swap calldata (output -> orderOwner)
    address tokenOut,
    uint256 minOut
) external onlyKeeper;
```

### Flow 2 — TWAP (recurring) → Permit2 AllowanceTransfer **+ a signed intent**

Permit2's AllowanceTransfer has **no witness variant** (one `permit` authorizes many transfers —
needed for TWAP). So we add our own EIP-712 intent, verified by the executor on **every** execution:

```
DcaIntent(address owner, address tokenIn, address tokenOut, uint256 maxAmountIn, uint256 minRate, uint256 deadline)
```

`minRate` = minimum `tokenOut` (base units) per `1e18` of `tokenIn` (base units) — i.e. the FX limit.
The contract requires `minOut >= partAmount * minRate / 1e18`, plus `owner`/`tokenIn`/`tokenOut`/
`maxAmountIn`/`deadline` checks. Signatures are verified for **EOA (ECDSA)** and **smart wallets
(EIP-1271)**.

Domain: `name="ArcSmartOrders", version="1", verifyingContract=executor` — must match
`OrderExecutor.EIP712_NAME_HASH` and `intentDomain()` in the SDK.

---

## Contract guarantees (`OrderExecutor`)

- **onlyKeeper** to execute; **onlyOwner** to change the keeper or the swap-target whitelist.
- **Whitelisted swap targets** (defense in depth against a malicious keeper).
- **Atomic**: pull → swap → refund leftover → verify `minOut`, all in one transaction.
- No funds held at rest; any leftover `tokenIn` is refunded to the user.
- Reentrancy guard; `TokenPermissions` / witness hashing pinned by a regression test.

---

## Repo layout

```
contracts/                        Foundry
  src/OrderExecutor.sol               the executor (witness + intent + whitelist)
  src/mocks/MockStableRouter.sol      fixed-rate USDC->EURC router for testnet/local
  src/agentic/IERC8004.sol            interfaces for the deployed ERC-8004 registries
  src/agentic/IAgenticCommerce.sol    interfaces for ERC-8183 + IACPHook
  test/OrderExecutor.t.sol            11 tests
  script/Deploy.s.sol                 deploy to Arc (+ optional mock router)
sdk/                              TypeScript (viem)
  src/index.ts                        EIP-712 domains/types, signLimitOrder/signTwapOrder, Permit2 approval
keeper/                           TypeScript (viem)
  src/index.ts                        executes ready orders, 20-gwei floor, USDC gas
  src/agentic.ts                      ERC-8004 identity/reputation + ERC-8183 job lifecycle
  src/setup-order.ts                  E2E: approve Permit2 + sign a LIMIT order
.env.example
```

---

## Testing

```bash
cd contracts
forge install foundry-rs/forge-std     # once
forge test -vv                         # 11 tests
```

Covers: atomic pull+swap, DCA parts, `minOut`/`minRate` reverts, whitelist, keeper/owner access,
**canonical Permit2 witness typehash**, and DcaIntent rejections (wrong `tokenOut`, low `minOut`,
foreign signature, expired).

Typecheck the TS:
```bash
cd sdk    && npm install && npx tsc --noEmit
cd keeper && npm install && npx tsc --noEmit
```

---

## Deploy & end-to-end on Arc Testnet

> Chain **5042002**, RPC `https://rpc.testnet.arc.io`, faucet <https://faucet.circle.com> (select **Arc Testnet** for USDC + EURC).

```bash
cd contracts
export EXECUTOR_KEEPER=<keeper EOA address>
export DEPLOY_MOCK_ROUTER=1                     # deploys MockStableRouter(USDC, EURC) and whitelists it
forge script script/Deploy.s.sol --rpc-url https://rpc.testnet.arc.io --broadcast
# → prints OrderExecutor + MockStableRouter addresses
```

Then:

1. **Fund the MockStableRouter with testnet EURC** (it must hold EURC to pay swaps):
   send some testnet EURC to the router address.
2. **Approve Permit2 for USDC once** from the user wallet:
   ```ts
   await ensurePermit2Approval(publicClient, wallet, USDC);
   ```
3. **Create a LIMIT order** (sign it, put it in `keeper/orders.json`):
   ```ts
   const signature = await signLimitOrder(wallet, {
     tokenIn: USDC, tokenOut: EURC.testnet,
     amountIn: 1_000_000n,        // 1 USDC (6 dec)
     minOut: 920_000n,            // ≥0.92 EURC
     spender: EXECUTOR, nonce: 1n, deadline: BigInt(now + 3600), chainId: 5042002,
   });
   ```
4. **Run the keeper**:
   ```bash
   cd keeper && cp ../.env.example .env   # KEEPER_PK, EXECUTOR, ROUTER
   npm install && npm start
   ```

The executor pulls exactly `amountIn` USDC via Permit2, swaps to EURC through the whitelisted
router, and sends the EURC to the user — reverting entirely if the outcome is below `minOut`.

---

## Agentic track — ERC-8004 identity + ERC-8183 job escrow

Arc already deploys the **canonical agent standards**, so we **do not redeploy them** — we integrate.
In `contracts/` we only add **interfaces** (so our contracts *can* call them); the real integration
lives in `keeper/src/agentic.ts`.

| Standard | Contract (Arc testnet) | Address |
|---|---|---|
| ERC-8004 | IdentityRegistry | `0x8004A818BFB912233c491871b3d84c89A494BD9e` |
| ERC-8004 | ReputationRegistry | `0x8004B663056A597Dffe9eCcC1965A193B7388713` |
| ERC-8004 | ValidationRegistry | `0x8004Cb1BF31DAf7788923b405b754f57acEB4272` |
| ERC-8183 | AgenticCommerce (jobs) | `0x0747EEf0706327138c69792bF28Cd525089e4583` |

### "Agentic Smart Orders" lifecycle
1. **Register the keeper agent** — `IdentityRegistry.register(metadataURI)` (ERC-8004).
2. **Create a job** — the client/agent calls `AgenticCommerce.createJob(provider=keeper, evaluator=client, expiredAt, desc, hook=0)`.
3. **Set the fee** — the keeper calls `setBudget(jobId, feeUSDC)`.
4. **Fund escrow** — the client approves USDC and calls `fund(jobId)`.
5. **Execute** — the keeper runs the signed intent through `OrderExecutor` → gets the fill tx hash.
6. **Submit** — the keeper calls `submit(jobId, keccak256(fillTxHash))`.
7. **Complete** — the evaluator calls `complete(jobId, reason)` → escrow released to the keeper.
8. **Reputation** — a validator records feedback via `ReputationRegistry.giveFeedback(...)`.

`keeper/src/agentic.ts` implements every step (`registerAgent`, `createJob`, `setBudget`, `fundJob`,
`submitDeliverable`, `completeJob`, `giveReputation`).

### Notes / boundaries
- **ACP = payment/escrow; ERC-8004 = identity/reputation.** Interop is by calling registries and
  (optionally) emitting/indexing events.
- **ERC-8183 `hook` must be whitelisted** by the ACP admin (`setHookWhitelist`). We therefore use the
  **non-hooked path** (`hook = address(0)`) and link job↔fill **off-chain** via the `deliverable` hash.
  `IACPHook` is included in `contracts/src/agentic/` for a future whitelisted hook.
- The ACP contract is **upgradeable + role-gated**; its admin/fee config is owned by the deployment
  team (Arc/Circle) for the reference implementation.

---

## Roadmap

1. **Wire the real swap venue.** The swap leg is a pluggable `swapTarget` (owner-whitelisted). On
   testnet we use `MockStableRouter`. For production, authorize the real venue (Circle **App Kit
   Swap** router / **StableFX** `FxEscrow`) via `setAllowedTarget`.
   → *Main open question: identify the public on-chain router/venue address.*
2. **Off-chain readiness.** Replace the manual `ready` flag with a real FX price source (App Kit
   quote / StableFX / oracle) compared against the signed `minOut` / `minRate`.
3. **Agentic track (ERC-8004 identity + ERC-8183 jobs).** Let AI agents register and run these
   orders / settle jobs in USDC — Arc's headline use case.
4. **API + UI** for creating/cancelling orders.

## Status

Reference implementation — **not audited**. Testnet first.

## License

MIT
