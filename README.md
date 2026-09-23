# Arc Smart Orders

[![CI](https://github.com/Salado210102/arc-smart-orders/actions/workflows/ci.yml/badge.svg)](https://github.com/Salado210102/arc-smart-orders/actions/workflows/ci.yml)

**Non-custodial limit & TWAP orders for stablecoin FX on Arc (USDC ⇄ EURC).**

> ⚠️ **Reference implementation — not audited.** On Arc mainnet today: **launching agents, bonding-curve
> trading and smart-order fills are live** (fills execute on Uniswap v3). **Graduation** and **ERC-8004
> identity** are pending (AMM config + the registries). See [Status & transparency](#status--transparency).

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
- 📄 **Launch writeup:** [`docs/LAUNCH.md`](docs/LAUNCH.md) · **Revenue model:** [`docs/REVENUE.md`](docs/REVENUE.md) · **Agent Launchpad:** [`docs/AGENT_LAUNCHPAD.md`](docs/AGENT_LAUNCHPAD.md) · **Mainnet treasury (Safe):** [`docs/SAFE_TREASURY.md`](docs/SAFE_TREASURY.md) · **Safe mainnet ops:** [`docs/SAFE_MAINNET.md`](docs/SAFE_MAINNET.md) · **Mainnet runbook:** [`docs/MAINNET_RUNBOOK.md`](docs/MAINNET_RUNBOOK.md) · **Audit scope:** [`docs/AUDIT_SCOPE.md`](docs/AUDIT_SCOPE.md) · **Python signing recipe:** [`examples/python/sign_limit_order.py`](examples/python/sign_limit_order.py) · **Deployments (tx tree):** [`DEPLOYMENTS.md`](DEPLOYMENTS.md)

---

## Modules

Three layers, one repo:

| Layer | What | Where | State |
|---|---|---|---|
| **1 · Core protocol** | Smart orders (Permit2 witness + EIP-712 **intent engine**) + **Agent Launchpad** | `contracts/src/OrderExecutor.sol`, `contracts/src/launchpad/*` | ✅ **live on Arc mainnet** |
| **1b · Cross-chain orders** | Sign an intent on a **source** chain, fill it **atomically on Arc** (interop/CCTP delivery) | `contracts/src/CrossChainOrderExecutor.sol` | 🧪 draft (not deployed) |
| **2 · Monetization & agentic credit** | **`AgentCreditPool`** (peer-to-contract USDC micro-loans), **`RevenueSplitter`** + **`AgentStakingVault`** (ERC-4626 yield accumulator) | `contracts/src/credit/*`, `contracts/src/launchpad/*` | 🧪 Phase 2 (draft, not deployed) |
| **3 · Agent SDK** | **`arc-agent-treasury`** — check balance / borrow / repay from an AI agent | `sdk-python/` | 🧪 Phase 2 |

- **Smart Orders** → [`contracts/src/OrderExecutor.sol`](contracts/src/OrderExecutor.sol) · [SDK](sdk/src/index.ts) · [Keeper](keeper/src/index.ts)
- **Agent Launchpad** → [`docs/AGENT_LAUNCHPAD.md`](docs/AGENT_LAUNCHPAD.md)
- **Agent Credit Pool** → [`contracts/src/credit/AgentCreditPool.sol`](contracts/src/credit/AgentCreditPool.sol) · [`docs/AGENT_CREDIT_POOL.md`](docs/AGENT_CREDIT_POOL.md)
- **Cross-chain orders (draft)** → [`contracts/src/CrossChainOrderExecutor.sol`](contracts/src/CrossChainOrderExecutor.sol) · [`docs/CROSS_CHAIN_ORDERS.md`](docs/CROSS_CHAIN_ORDERS.md)
- **Python SDK** → [`sdk-python/`](sdk-python/)

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

## Cross-chain orders (draft)

Sign an order on a **source** chain, fill it **atomically on Arc**. The input USDC is delivered to
[`CrossChainOrderExecutor`](contracts/src/CrossChainOrderExecutor.sol) by an interop/CCTP message, and
the swap runs on arrival, paying the output to the user's wallet.

- **Not Permit2** — Permit2 signatures are chain-bound; the order is a signed `CrossChainIntent` with a
  **standard 4-field EIP-712 domain** (`chainId` = destination) so viem/wallets can sign it.
- **Anti-replay** — domain `chainId` = destination + signed `sourceChainId`/`destinationChainId` +
  single-use nonce.
- **Guarantees** — onlyKeeper (optionally onlyInterop), whitelisted `swapTarget`, 0.30% input-side fee
  retained before the swap, `minOut` enforced on the **net**, ECDSA + EIP-1271, reentrancy guard.
- **Builder** — [`keeper/src/crosschain-builder.ts`](keeper/src/crosschain-builder.ts)
  (`signCrossChainIntent` + `buildExecuteCrossChainData`).

Draft — not deployed; see [`docs/CROSS_CHAIN_ORDERS.md`](docs/CROSS_CHAIN_ORDERS.md).

---

## Agent Launchpad

A complete launchpad for AI agents, built on the same non-custodial primitives.

> **Mainnet status:** **launching an agent + trading on its USDC bonding curve are live** on Arc mainnet
> today. **ERC-8004 identity, DEX graduation and LP locking are pending** (the registries and a public DEX
> venue are not live on Arc mainnet yet) — they are proven on testnet and marked as such below.

- **Identity** — ERC-8004 `register` on launch (`AgentFactory`) *(skipped on mainnet until the registry ships)*.
- **Token + USDC bonding curve** — `AgentToken` (fixed supply, anti-sniper limits), `AgentBondingCurve`
  (virtual reserves `k = x·y`, 1% fee split 50/50 protocol/agent, sniper fee, graduation),
  `AgentFactory` (orchestrator).
- **Registry + graduation** — `AgentRegistry` (agentId ⟷ token ⟷ curve ⟷ creator), `GraduationModule`
  (pulls liquidity, seeds the DEX), `LiquidityLocker` (LP locked 365d → anti-rug) *(graduation is **gated**
  on mainnet — no module is wired until a real DEX exists)*.
- **Revenue + staking** — `RevenueSplitter` (agent USDC revenue → 70% stakers / 30% treasury),
  `AgentStakingVault` (ERC-4626-style, deposit the agent token, earn USDC yield).
- **UI** — Create · Trade (curve buy/sell) · **Smart Swap** (sign 0-gas limit orders; **Testnet = live
  fills**, Mainnet = Beta dry-run) · **Staking & Yield** (stake/unstake/claim) with IPFS
  (Pinata) metadata, at **https://arc.basepump.dev**.
- **Tests** — **34/34** Foundry (orders 17 · launchpad 8 · graduation 3 · staking 5 · revenue-wiring 1) **+ 1 mainnet-fork dry-run** (`test/DeployMainnetFork.t.sol`, [audit package](docs/AUDIT_PACKAGE.md) §4).

Addresses & tx hashes: [`DEPLOYMENTS.md`](DEPLOYMENTS.md). Architecture: [`docs/AGENT_LAUNCHPAD.md`](docs/AGENT_LAUNCHPAD.md).

**Revenue wiring:** an order filled by the keeper through `OrderExecutor v2` takes a **0.30% input-side
fee** which is sent to the agent's `RevenueSplitter`; calling `distributeBalance()` pushes **70% to the
staking vault** and 30% to the treasury. Verified by `test/RevenueWiring.t.sol`.

## Phase 2 — Agentic credit & monetization

### `AgentCreditPool` — peer-to-contract USDC micro-credit
- **Invite-only** (whitelisted LPs + agents). LPs deposit USDC to earn yield; approved agents take
  **short micro-loans ($5–$50)** to pay for API/gas.
- **Risk, layered:** whitelist → **per-agent & per-epoch caps** → **max utilization** (LPs can always
  withdraw) → **first-loss reserve** → **hybrid bond** (min USDC bond on-chain + ERC-8004 reputation
  off-chain, slashed on default) → owner **pause**.
- **Fees:** flat per-loan interest; **15% performance fee → Safe treasury**, a slice → reserve, the rest
  → LPs.
- **Auto-repay:** the keeper settles the loan from the **ERC-8183 job escrow** (`repayFrom`) as soon as
  the deliverable is validated.

### `RevenueSplitter` + `AgentStakingVault` (ERC-4626 yield accumulator)
- `RevenueSplitter` splits an agent's USDC revenue **70% → stakers / 30% → treasury**.
- `AgentStakingVault` is an **ERC-4626-style** vault; the stakers' share streams in as yield.

### `RevenueRouter` — repay-before-split guarantee
`RevenueRouter.route(agent, revenue)` calls `pool.repayOnBehalf(agent, …)` **before** forwarding the
remainder to the `RevenueSplitter`, in the **same transaction** — so the pool is settled first and
dividends are computed only on **net** revenue. (`contracts/src/credit/RevenueRouter.sol`)

### cirBTC collateral & yield vault (draft)
- **cirBTC collateral** in `AgentCreditPool`: agents post **cirBTC** (Arc mainnet `0x171A…bAA0`, 8 dec) to
  borrow USDC — **LTV ≤ 70%**, liquidation at **80%**, **5% penalty → treasury**; `liquidate()` is
  permissionless. Prices come from an **`IPriceOracle`**; **no public Arc oracle exists yet** → a real
  Pyth/Chainlink feed is wired via `setCollateralConfig` (`MockPriceOracle` in tests).
- **`AgentYieldVault`** (ERC-4626, asset = cirBTC) with a pluggable **`IYieldStrategy`** (Uniswap v4 / Arc
  AMM concentrated liquidity when available; `MockYieldStrategy` until then). Draft — **not deployed**.

### Unified economic flow
Credit is returned to the pool **before** any dividend is distributed:

```
   AI agent needs gas/API
          │  borrow ($5–$50)
          ▼
   AgentCreditPool ──────────────► AI agent
        ▲                             │  does a job (ERC-8183 escrow)
        │  repayOnBehalf (auto)       ▼
        └───────────────  RevenueRouter.route(agent, revenue)
              │              (1) repay debt to the pool FIRST
              │              (2) forward the remainder
              │                     ▼
              └────────────  RevenueSplitter
                                 ├─ 70% ─► AgentStakingVault (stakers earn USDC)
                                 └─ 30% ─► Safe treasury
```

When an ERC-8183 job completes, the escrow pays out; the **keeper immediately repays the outstanding
loan** to the pool (`repayFrom`), and only **then** does the remaining revenue flow through the
`RevenueSplitter` (70% stakers / 30% treasury). LPs are made whole first → no double-spend of the agent's
income.

## Repo layout

```
contracts/                          Foundry — solc 0.8.26, via-ir, optimizer 200, bytecode_hash=none
  src/OrderExecutor.sol               executor (Permit2 witness + DcaIntent + input-side fee + whitelist)
  src/CrossChainOrderExecutor.sol     cross-chain intent executor (sign on source chain, fill on Arc) — DRAFT
  src/agentic/IERC8004.sol            interfaces for the deployed ERC-8004 registries
  src/agentic/IAgenticCommerce.sol    interfaces for ERC-8183 + IACPHook
  src/credit/AgentCreditPool.sol      peer-to-contract USDC micro-credit (LP shares, bond, caps, first-loss reserve)
  src/credit/RevenueRouter.sol        repay-before-split router (settles pool debt, then forwards to the splitter)
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
  test/CrossChainOrderExecutor.t.sol  6 tests  (cross-chain fill, source/dest chain, replay, signature, access)
  test/Permit2WitnessFork.t.sol       fork test vs the real Permit2
  test/DeployMainnetFork.t.sol        mainnet-fork dry-run of the deploy script
  test/AgentCreditPool.t.sol          21 tests (credit pool: shares, whitelist, bond, caps, repay split, default, pause)
  test/RevenueRouter.t.sol            integration: repay debt before splitting revenue
  script/Deploy.s.sol                 deploy OrderExecutor (+ optional mock router)
  script/DeployLaunchpad.s.sol        deploy the launchpad (P1/P2)
  script/DeployStaking.s.sol          deploy RevenueSplitter + vault (P3)
  script/DeployMainnet.s.sol          deterministic MAINNET deploy (env-validated + Safe)
  script/DeployCreditPool.s.sol       deploy AgentCreditPool (env-validated, Safe-owned)
  script/CreateSafe.s.sol             create the 2/2 Safe on Arc
sdk/                                TypeScript (viem)
  src/index.ts                        EIP-712 domains/types, signLimitOrder/signTwapOrder, Permit2 approval
sdk-python/                         Python SDK — arc-agent-treasury (PyPI-ready)
  arc_agent_treasury/{__init__,client}.py  AgentTreasuryClient: usdc_balance / ensure_credit / request_credit / repay
sdk/python/                         Python SDK — arc-smart-orders (EIP-712 sign + keeper submit)
  arc_smart_orders/{__init__,client,signer,eip712,rpc,constants}.py  ArcSmartOrdersClient (eth-account, stdlib RPC)
  tests/test_signing.py               signature/recovery tests (must match the on-chain types)
  examples/submit_limit_order.py      sign + POST /v1/orders + poll
keeper/                             TypeScript (viem)
  src/{server,worker,db,agentic,events}.ts  persistent keeper: HTTP API + WebSocket + SQLite worker
  src/agentic.ts                      ERC-8004 identity/reputation + ERC-8183 job lifecycle
  src/setup-order.ts                  E2E: approve Permit2 + sign a LIMIT order
  src/crosschain-builder.ts           sign a CrossChainIntent + encode executeCrossChain (draft)
apps/launchpad/                     Vite + React + Tailwind launchpad UI (Vercel) — incl. "Smart Swap" (sign 0-gas orders)
ops/                                ops tooling (Safe execTransaction signer, alerts + metrics bots, keeper funding)
examples/python/sign_limit_order.py Python EIP-712 signing recipe (verified to match the TS SDK)
scripts/backtest_gex_signals.py     GEX (Call/Put Wall, Zero Gamma) signal backtest -> EIP-712 intents
docs/                               LAUNCH · REVENUE · AGENT_LAUNCHPAD · AGENT_CREDIT_POOL · PHASE2_ARCHITECTURE · CROSS_CHAIN_ORDERS · GEX_AGENT_SPEC · PYTHON_SDK · SDK_INTEGRATION · SAFE_TREASURY · SAFE_MAINNET · AUDIT_SCOPE · AUDIT_PACKAGE · ARC_CIRCLE_AUDIT_PROPOSAL · ARC_CIRCLE_AUDIT_EMAIL · MAINNET_RUNBOOK · UFSF_AUDIT_PROPOSAL · DEV_COMMUNITY_POST · DEMO_SCRIPT · ALERTS_BOT · KEEPER_SETUP
```

---

## Quick start

### Python SDK (`arc-agent-treasury`)
```bash
pip install -e ./sdk-python            # or: pip install arc-agent-treasury (once published)
```
```python
from arc_agent_treasury import ArcAgentTreasury

tr = ArcAgentTreasury(
    rpc_url="https://rpc.mainnet.arc.io",
    pool_address="0x…AgentCreditPool",
    agent_address="0x…myAgent",
    private_key=os.environ["AGENT_PK"],
)
tx = tr.ensure_credit(min_balance=1_000_000, amount=10_000_000)  # borrow only if < 1 USDC
```

### Smart Orders Python SDK (`arc-smart-orders`)
Sign EIP-712 / Permit2 limit & TWAP orders and submit them to the keeper API — for quant developers.
```bash
pip install -e ./sdk/python            # or: pip install eth-account
```
```python
import os
from arc_smart_orders import ArcSmartOrdersClient, to_units

client = ArcSmartOrdersClient(private_key=os.environ["ARC_PK"], keeper_url=os.environ.get("KEEPER_API"))
client.ensure_permit2_approval()                                          # one-time (gas)
resp = client.submit_limit_order(amount_in=to_units("1"), min_out=to_units("0.90"))  # 0 gas
final = client.wait_for_fill(resp["order"]["id"])                         # -> FILLED + fill_tx
```
- `sdk/python/` · example [`sdk/python/examples/submit_limit_order.py`](sdk/python/examples/submit_limit_order.py) · [README](sdk/python/README.md) · full guide [`docs/PYTHON_SDK.md`](docs/PYTHON_SDK.md)
- Tests: `python sdk/python/tests/test_signing.py` (recovers the owner from the signature → fails on any type mismatch)

### GEX signal backtest
```bash
python scripts/backtest_gex_signals.py --steps 600 --seed 7 --out /tmp/gex.json
# simulates GEX (Call/Put Wall, Zero Gamma) signals -> EIP-712 LIMIT intents with minOut + expected return
```

### Smart Swap widget (dashboard)
The **Smart Swap** tab at <https://arc.basepump.dev> signs a 0-gas limit order and follows it to `FILLED`.
A **network selector** switches between:
- **Arc Testnet (Live fills)** → keeper `…/arc-keeper-testnet` (`0xB19F…6Ee3`), fills on-chain vs the mock router.
- **Arc Mainnet (Live fills)** → keeper `…/arc-keeper`, fills on-chain via **Uniswap v3** (`SwapRouter02`, USDC/EURC pool).

Build-time env (Vite): `VITE_KEEPER_API` and `VITE_KEEPER_TESTNET_API` — see [`apps/launchpad/.env.example`](apps/launchpad/.env.example).

### Contracts — Foundry
```bash
cd contracts
forge install foundry-rs/forge-std     # once
forge test -vv                         # core: 34/34 (+1 fork skipped unless env set)
forge test --match-contract AgentCreditPoolTest -vvv   # Phase 2: 21 credit-pool tests
forge test --match-contract RevenueRouterTest -vvv     # Phase 2: 3 repay-before-split tests
forge test --match-contract CrossChainOrderExecutorTest -vvv   # cross-chain: 6 intent-executor tests
```
> CI runs all of this on every push — see the **CI badge** at the top (`.github/workflows/ci.yml`).

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
   testnet we use `MockStableRouter`. **Update (2026-09-23): Uniswap v3 + v4 are live on Arc mainnet**
   with a liquid **USDC/EURC pool** (fee 0.05%, `liquidity ≈ 7.76e11`). StableFX stays permissioned and
   App Kit Swap is not an on-chain router, but Uniswap **unblocks mainnet fills**: whitelist
   `SwapRouter02 0x53BF…6F77` via the Safe and set keeper `DRY=0`. See
   [`docs/VENUE_INTEGRATION.md`](docs/VENUE_INTEGRATION.md).
2. **Off-chain readiness.** Replace the manual `ready` flag with a real FX price source (App Kit
   quote / StableFX / oracle) compared against the signed `minOut` / `minRate`.
3. **Agentic track (ERC-8004 identity + ERC-8183 jobs).** Let AI agents register and run these
   orders / settle jobs in USDC — Arc's headline use case.
4. **API + UI** for creating/cancelling orders.
5. **Phase 2 — agentic credit.** Audit the `AgentCreditPool`, run an **invite-only pilot**, wire the
   **ERC-8183 auto-repay** through the keeper, and publish the **Python SDK** to PyPI.

## Infrastructure — VPS services (PM2)

Both keepers + the alerts bot run on the same VPS, isolated by port (see [`docs/KEEPER_SETUP.md`](docs/KEEPER_SETUP.md), [`docs/ALERTS_BOT.md`](docs/ALERTS_BOT.md)):

| PM2 process | Role | Port | Network |
|---|---|---|---|
| `arc-keeper` | order keeper — **live fills on mainnet via Uniswap v3** (`DRY=0`) | `8788` | Arc **5042** (mainnet) |
| `arc-keeper-testnet` | order keeper — **live fills** | `8789` | Arc **5042002** (testnet) |
| `arc-alerts` | Telegram alerts: new agents + **keeper low-gas** (mainnet & testnet) | — | Arc 5042 / 5042002 |
| `pm2-logrotate` | log rotation (`max_size 10M`, `retain 7`, compressed) | — | — |

`pm2 save` + `pm2 startup` (systemd) → all services persist across reboots.

## Status & transparency

| | |
|---|---|
| **Live on Arc mainnet (5042)** | `OrderExecutor`, `AgentFactory`, `AgentRegistry`, `GraduationModule`, `LiquidityLocker` — all **Safe-owned** (see [`DEPLOYMENTS.md`](DEPLOYMENTS.md)) |
| **Works today** | launching an agent, trading on its USDC bonding curve, and **live smart-order fills via Uniswap v3** (non-custodial) |
| **Pending (external, not bugs)** | **graduation** config (AMM adapter) + **ERC-8004** identity (registry not on mainnet yet) |
| **Not deployed / draft** | Phase 2 `AgentCreditPool` (credit) — **unaudited**, not deployed |
| **Not audited** | the whole codebase — see [`docs/AUDIT_PACKAGE.md`](docs/AUDIT_PACKAGE.md) |

Pre-audit freeze: tag `pre-audit-v2` (previous [`pre-audit-v1`](https://github.com/Salado210102/arc-smart-orders/tree/pre-audit-v1)).

## License

MIT
