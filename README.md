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
- 📦 **Audit package (start here):** [`docs/AUDIT_PACKAGE.md`](docs/AUDIT_PACKAGE.md) — scope, sizes, test evidence, fork rehearsal, checklist
- 📄 **Launch writeup:** [`docs/LAUNCH.md`](docs/LAUNCH.md) · **Revenue model:** [`docs/REVENUE.md`](docs/REVENUE.md) · **Agent Launchpad:** [`docs/AGENT_LAUNCHPAD.md`](docs/AGENT_LAUNCHPAD.md) · **Mainnet treasury (Safe):** [`docs/SAFE_TREASURY.md`](docs/SAFE_TREASURY.md) · **Mainnet runbook:** [`docs/MAINNET_RUNBOOK.md`](docs/MAINNET_RUNBOOK.md) · **Audit scope:** [`docs/AUDIT_SCOPE.md`](docs/AUDIT_SCOPE.md) · **Python signing recipe:** [`examples/python/sign_limit_order.py`](examples/python/sign_limit_order.py) · **Deployments (tx tree):** [`DEPLOYMENTS.md`](DEPLOYMENTS.md)

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

### Fees (input-side)

`OrderExecutor` charges a platform fee on the **input token**, taken **before** the swap:

- `feeBps` (default **30** = 0.30%) and `feeRecipient` (your Safe/multisig), set at deploy or via
  `setFee(bps, recipient)` (**onlyOwner**, hard cap **1000 bps / 10%**).
- The fee is sent to `feeRecipient` in `tokenIn` (USDC/EURC) → stable, no price/slippage risk.
- The user's signed `minOut` (LIMIT) / `minRate` (TWAP) is measured on the **net** amount, so a fee
  increase can never push a fill below what the user signed — it simply reverts.
- If `feeRecipient == address(0)`, no fee is charged.

> Revenue has two separate rails: **(1)** this platform fee → your treasury, and
> **(2)** the keeper's ERC-8183 execution fee (`setBudget`) → the keeper wallet.
>
> Full model, projections and the mainnet treasury plan: **[`docs/REVENUE.md`](docs/REVENUE.md)**.

---

## Agent Launchpad (live on Arc mainnet)

A complete launchpad for AI agents, built on the same non-custodial primitives:

- **Identity** — ERC-8004 `register` on launch (`AgentFactory`).
- **Token + USDC bonding curve** — `AgentToken` (fixed supply, anti-sniper limits), `AgentBondingCurve`
  (virtual reserves `k = x·y`, 1% fee split 50/50 protocol/agent, sniper fee, graduation),
  `AgentFactory` (orchestrator).
- **Registry + graduation** — `AgentRegistry` (agentId ⟷ token ⟷ curve ⟷ creator), `GraduationModule`
  (pulls liquidity, seeds the DEX), `LiquidityLocker` (LP locked 365d → anti-rug).
- **Revenue + staking** — `RevenueSplitter` (agent USDC revenue → 70% stakers / 30% treasury),
  `AgentStakingVault` (ERC-4626-style, deposit the agent token, earn USDC yield).
- **UI** — Create · Trade (curve buy/sell) · **Staking & Yield** (stake/unstake/claim) with IPFS
  (Pinata) metadata, at **https://launchpad-neon-chi.vercel.app**.
- **Tests** — **34/34** Foundry (orders 17 · launchpad 8 · graduation 3 · staking 5 · revenue-wiring 1) **+ 1 mainnet-fork dry-run** (`test/DeployMainnetFork.t.sol`, [audit package](docs/AUDIT_PACKAGE.md) §4).

Addresses & tx hashes: [`DEPLOYMENTS.md`](DEPLOYMENTS.md). Architecture: [`docs/AGENT_LAUNCHPAD.md`](docs/AGENT_LAUNCHPAD.md).

**Revenue wiring:** an order filled by the keeper through `OrderExecutor v2` takes a **0.30% input-side
fee** which is sent to the agent's `RevenueSplitter`; calling `distributeBalance()` pushes **70% to the
staking vault** and 30% to the treasury. Verified by `test/RevenueWiring.t.sol`.

## Repo layout

```
contracts/                          Foundry — solc 0.8.26, via-ir, optimizer 200, bytecode_hash=none
  src/OrderExecutor.sol               executor (Permit2 witness + DcaIntent + input-side fee + whitelist)
  src/agentic/IERC8004.sol            interfaces for the deployed ERC-8004 registries
  src/agentic/IAgenticCommerce.sol    interfaces for ERC-8183 + IACPHook
  src/launchpad/AgentToken.sol        ERC-20 (fixed supply, anti-sniper limits)
  src/launchpad/AgentBondingCurve.sol USDC bonding curve (virtual reserves, fees, graduation)
  src/launchpad/AgentFactory.sol      launch orchestrator (token + curve + ERC-8004 identity)
  src/launchpad/AgentRegistry.sol     on-chain agent index
  src/launchpad/GraduationModule.sol  seeds DEX liquidity + locks LP
  src/launchpad/LiquidityLocker.sol   LP lock (anti-rug, 365d)
  src/launchpad/RevenueSplitter.sol   agent USDC revenue -> 70% stakers / 30% treasury
  src/launchpad/AgentStakingVault.sol ERC-4626-style USDC-yield vault
  src/launchpad/mocks/MockDEX.sol     test AMM + LP token
  src/mocks/MockStableRouter.sol      fixed-rate USDC->EURC router for testnet/local
  test/OrderExecutor.t.sol            17 tests (witness, DCA, fee, access, whitelist)
  test/Launchpad.t.sol                8 tests  (curve, fee split, anti-sniper, limits)
  test/LaunchpadGraduation.t.sol      3 tests  (graduation + LP lock)
  test/Staking.t.sol                  5 tests  (revenue split -> staking yield)
  test/RevenueWiring.t.sol            1 test   (order fee -> splitter -> vault)
  test/Permit2WitnessFork.t.sol       fork test vs the real Permit2
  test/DeployMainnetFork.t.sol        mainnet-fork dry-run of the deploy script
  script/Deploy.s.sol                 deploy OrderExecutor (+ optional mock router)
  script/DeployLaunchpad.s.sol        deploy the launchpad (P1/P2)
  script/DeployStaking.s.sol          deploy RevenueSplitter + vault (P3)
  script/DeployMainnet.s.sol          deterministic MAINNET deploy (env-validated + Safe)
  script/CreateSafe.s.sol             create the 2/2 Safe on Arc
sdk/                                TypeScript (viem)
  src/index.ts                        EIP-712 domains/types, signLimitOrder/signTwapOrder, Permit2 approval
keeper/                             TypeScript (viem)
  src/{server,worker,db,agentic,events}.ts  persistent keeper: HTTP API + WebSocket + SQLite worker
  src/agentic.ts                      ERC-8004 identity/reputation + ERC-8183 job lifecycle
  src/setup-order.ts                  E2E: approve Permit2 + sign a LIMIT order
apps/launchpad/                     Vite + React + Tailwind launchpad UI (Vercel)
ops/                                ops tooling (Safe execTransaction signer, reminder bot)
examples/python/sign_limit_order.py Python EIP-712 signing recipe (verified to match the TS SDK)
docs/                               LAUNCH · REVENUE · AGENT_LAUNCHPAD · SAFE_TREASURY · AUDIT_SCOPE · AUDIT_PACKAGE · MAINNET_RUNBOOK · UFSF_AUDIT_PROPOSAL
```

---

## Testing

```bash
cd contracts
forge install foundry-rs/forge-std     # once
forge test -vv                         # 34/34 unit+integration (fork test skipped unless env is set)
```

Covers: atomic pull+swap, DCA parts, `minOut`/`minRate` reverts, whitelist, keeper/owner access,
**canonical Permit2 witness typehash**, `DcaIntent` rejections (wrong `tokenOut`, low `minOut`, foreign
signature, expired), the bonding-curve invariants (fee split, anti-sniper, max wallet/tx, graduation +
LP lock), the revenue split → staking yield, and the order fee → splitter → vault wiring.

**Mainnet-fork rehearsal** (see [`docs/AUDIT_PACKAGE.md`](docs/AUDIT_PACKAGE.md) §4):
```bash
CONFIRM_MAINNET=1 USDC_MAINNET=0x3600…0000 DEX_ROUTER=0x…D3 ERC8004_REGISTRY=0x8004A818…BD9e \
ERC8183_ESCROW=0x0747…4583 ORDERS_KEEPER=0x327f…50bC LAUNCHPAD_OWNER=0x0FBFAF…7e93 \
forge test --match-test test_FullDeployOnFork -vv
```

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

## Persistent keeper (24/7)

`keeper/` runs an **HTTP API + a worker loop** (no external DB engine — `node:sqlite`):

- **`POST /v1/orders`** — a signed order (Permit2 witness) is validated **off-chain**: EIP-712
  signature (`spender = executor`), maker **balance**, **Permit2 allowance** and deadline. Persisted
  to **SQLite** (`data/orders.db`).
- **`GET /v1/orders?maker=` · `/v1/orders/:id` · `/v1/mempool` · `/health`**.
- **Worker loop** (every `LOOP_MS`): expires overdue orders, reads `PENDING`, checks the on-chain
  rate vs the signed `minOut`, builds the swap for the **net** (gross − fee), calls
  `OrderExecutor.executeOrder`, marks **FILLED** with the `fillTxHash`, and — when the order is
  linked to an **ERC-8183 job** (`jobId`) — submits `keccak256(fillTxHash)` as the deliverable.

```bash
cd keeper
cp .env.example .env     # KEEPER_PK, EXECUTOR, ROUTER, PORT, DB_PATH
npm install
npm start                # API on :8788 + worker loop
```

**Deploy on a VPS (Ubuntu):**
```bash
# systemd (recommended)
cp keeper/arc-keeper.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now arc-keeper
# or pm2
cd keeper && npm i -g pm2 && pm2 start ecosystem.config.cjs && pm2 save
```

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

**Pre-audit freeze:** `pre-audit-v2` (previous: [`pre-audit-v1`](https://github.com/Salado210102/arc-smart-orders/tree/pre-audit-v1)).
**Live on Arc mainnet (5042)** — Safe-owned deploy (see [`DEPLOYMENTS.md`](DEPLOYMENTS.md)): OrderExecutor,
AgentFactory, AgentRegistry, GraduationModule, LiquidityLocker. Graduation is **gated** (no module wired) and
ERC-8004 is **skipped** until the registries ship on mainnet; the swap venue (StableFX) is pending. **Not yet
audited** — see [`docs/AUDIT_PACKAGE.md`](docs/AUDIT_PACKAGE.md).

## License

MIT
