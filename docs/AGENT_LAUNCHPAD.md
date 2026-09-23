# Agent Launchpad — architecture & plan (Arc)

> A launchpad where anyone can **launch an AI agent** that has: an on-chain **identity** (ERC-8004),
> a **USDC bonding-curve token**, autonomous **earnings** (ERC-8183 jobs), and **smart orders**
> (our `OrderExecutor` v2). Stablecoin-native, because Arc settles gas and value in **USDC**.

---

## 0. Vision & why Arc

Today's agent frameworks stop at "an LLM with a wallet". The missing layer is **economic identity**:
a token that funds the agent, a market that prices it, a job-escrow that pays it, and orders that
let it (or its holders) trade it — all non-custodial.

Arc is the right chain: **USDC is the gas token and the unit of account**, finality is
deterministic, and **ERC-8004 / ERC-8183 / Permit2 are already deployed**.

```
                         ┌──────────────────── Agent Launchpad ────────────────────┐
   creator ──launch──►   │  AgentFactory ─► AgentToken + AgentBondingCurve (USDC)   │
                         │         │                    │                          │
                         │         ▼                    ▼                          │
                         │   ERC-8004 Identity   curve buys/sells (USDC)            │
                         │   (agentId + metadata)         │                          │
                         │         │                      │ graduation               │
                         │         ▼                      ▼                          │
                         │  ERC-8183 jobs  ◄──►   DEX pool + LiquidityLocker        │
                         │  (escrow/earnings)                                      │
                         └─────────┬───────────────────────────────────────────────┘
                                   │ smart orders (limit/TWAP), keeper, fee
                                   ▼
                         OrderExecutor v2 (arc-smart-orders)  ──►  treasury Safe (0.30%)
```

---

## 1. Primitives & standards (minting + budget)

### 1.1 Identity — ERC-8004
On launch, `AgentFactory` calls **`IdentityRegistry.register(metadataURI)`** → mints the agent's
identity NFT (`agentId`). Metadata (IPFS/Arweave):
```json
{
  "name": "Alpha Fx Agent",
  "description": "Autonomous USDC/EURC FX agent",
  "image": "ipfs://…",
  "model": "…",
  "capabilities": ["fx_trading", "dca", "copy_trading"],
  "endpoint": "https://agent.example/api",
  "token": "0x…", "curve": "0x…"
}
```
- **ReputationRegistry** accrues feedback from completed jobs → the agent's track record.
- **ValidationRegistry** for KYC/audit attestations (optional, permissioned agents).

### 1.2 Budget & earnings — ERC-8183 (AgenticCommerce)
Agents are **first-class economic actors**:
- A **client** (human or another agent) creates a job (`createJob`), funds escrow in **USDC**, the
  agent-as-provider executes and `submit`s, the evaluator `complete`s → the agent gets paid.
- The agent's **income** can be routed to a `RevenueSplitter` → token stakers / buybacks (below).
- The launchpad is the **discovery + identity** layer on top of the ACP escrow.

---

## 2. Economic mechanics — USDC bonding curve + anti-rug

### 2.1 Curve (constant product with virtual reserves, denominated in USDC)
State: virtual reserves `x` (USDC) and `y` (tokens), invariant `k = x·y`. Price `p = x / y` (USDC/token).

- **Buy** with `dU` USDC → `dT = y − k/(x + dU)` tokens (fee `φ` subtracted first).
- **Sell** `dT` tokens → `dU = x − k/(y + dT)` USDC (fee `φ` subtracted).
- Price rises monotonically with buys → early demand is rewarded, no admin-set prices.

Illustrative (start `x=5,000 USDC`, `y=1e9` tokens → `p₀ = 0.000005` USDC):
buying `100 USDC` mints ≈ `19.6M` tokens and moves `p` to ≈ `0.0000052`.

### 2.2 Fees
- **Curve fee** `φ` (e.g., 1%) on every buy/sell → split: **protocol treasury** (Safe) + **agent
  treasury** (agent ops / buybacks / staker rewards).
- Everything in **USDC** — no volatile fee token, no slippage on the fee itself.

### 2.3 Graduation (upgrade to a real DEX pool)
When the curve raises a threshold (`Y_graduation` USDC) or sells `X_curve` tokens, the remaining
liquidity is **migrated to a DEX pool** (reuse our `GraduationModule` + `LiquidityLocker`) and the
**LP is locked/burned** → permanent liquidity.

### 2.4 Anti-rug protections (enforced in code)
| Risk | Protection |
|---|---|
| Infinite mint / hidden inflation | **Fixed supply**, **no mint** after init, no proxy upgrade of the token |
| Creator pulls liquidity | **LP locked** in `LiquidityLocker` at graduation; unlock time configurable (default: long/none) |
| Owner drains treasury | **Ownership → Safe** (multisig) + **timelock** on parameter changes; treasury is a separate contract |
| Sniper / MEV dump | **Anti-sniper** launch guard (first N seconds: higher fee + max-buy), **max wallet/tx** early caps |
| Creator instant dump | **Vesting** for creator allocation (linear, on-chain) |
| Fee rug (dynamic tax) | **Immutable** fee parameters set at deploy (no post-launch tax changes on the token) |
| Abandonment | **Agent treasury** funds from fees; optional **dev-escrow** released on milestones |

> Rule of thumb: **immutable token + curve + locked LP + Safe-owned config + vesting** removes the
> classic rug vectors. Parameters that must stay tunable (fees, caps) live behind a **timelock**.

---

## 3. Native integration with `OrderExecutor` v2 + SDK

The launchpad is **composable with our smart-orders stack** (already live on Arc testnet):

- **Buying/selling the agent token** can route through `OrderExecutor` — the **bonding curve is a
  whitelisted `swapTarget`** (the executor approves it and calls `swap`), so limit/stop/TWAP/DCA
  orders work on the agent token with the same **input-side 0.30% fee → treasury**.
- **Non-custodial**: users sign a Permit2 witness/intent; the keeper fills; the executor enforces
  `minOut`/`minRate`. No deposits.
- **SDK** (`sdk/src/index.ts`, TS + verified Python recipe): `signLimitOrder`, `signTwapOrder` — an
  agent or its users integrate in a few lines.
- **Keeper** (persistent): the same API (`POST /v1/orders`) + worker fills agent-token orders; the
  `jobId` link submits the ERC-8183 deliverable → the keeper gets paid.
- **Agent-as-keeper / agent-as-client**: an autonomous agent can create ERC-8183 jobs to pay for
  execution, or be the provider whose fills are rated on ERC-8004.

```
user/agent ── sign intent ─► OrderExecutor v2 ── swapTarget = AgentBondingCurve (or DEX) ──► USDC ⇄ AgentToken
                                   │ fee 0.30% (input-side)
                                   ▼
                             treasury Safe
```

---

## 4. Core contracts

| Contract | Responsibility |
|---|---|
| **`AgentFactory.sol`** | Entry point. Creates an agent atomically: deploys `AgentToken` + `AgentBondingCurve`, mints the **ERC-8004 identity** (`IdentityRegistry.register`), stores metadata, emits `AgentCreated`. Optional launch fee → treasury. |
| **`AgentToken.sol`** | ERC-20, **fixed supply, no mint, no tax, no proxy** (max v4/DEX compatibility). Creator allocation assigned to a `Vesting`. |
| **`AgentBondingCurve.sol`** | USDC constant-product curve (virtual reserves). `buy()`, `sell()`, price view, curve fee split, graduation trigger. Immutable params. |
| **`AgentRegistry.sol`** | Discovery/index: `agentId ⇄ token ⇄ curve ⇄ operator ⇄ metadataURI`; enumeration for the launchpad UI. |
| **`GraduationModule.sol`** | Migrates curve liquidity to a DEX pool (+ `LiquidityLocker`) with **LP locked**. Reuses BasePump's proven pattern. |
| **`LiquidityLocker.sol`** | Locks LP NFTs/tokens (reused). |
| **`AgentTreasury.sol`** | Holds the agent's fee share; spends on ops, buybacks, or staker rewards (Safe/timelock controlled). |
| **`RevenueSplitter.sol`** *(optional)* | Splits agent ERC-8183 income/fees → stakers / buyback / treasury. Pairs with an ERC-4626 staking vault. |
| **`OrderExecutor.sol`** *(existing v2)* | Non-custodial order execution; the curve/DEX is a whitelisted `swapTarget`. |

**Interfaces to import:** `IIdentityRegistry`, `IReputationRegistry` (ERC-8004) · `IAgenticCommerce`,
`IACPHook` (ERC-8183) · `IERC20` · `LiquidityLocker`.

---

## 5. Roadmap (phases)

1. **P0 — Primitives (done):** `OrderExecutor v2` + SDK + persistent keeper + ERC-8004/8183 integration.
2. **P1 — Token + curve:** `AgentToken`, `AgentBondingCurve`, `AgentFactory` (testnet), unit + fork tests.
3. **P2 — Identity & discovery:** ERC-8004 registration in the factory, `AgentRegistry`, minimal UI.
4. **P3 — Graduation & anti-rug:** `GraduationModule` + `LiquidityLocker` + vesting + anti-sniper.
5. **P4 — Economics:** fee split, `AgentTreasury`, optional ERC-4626 staking + `RevenueSplitter`.
6. **P5 — Agentic jobs & smart orders:** wire ERC-8183 (hire/pay agents) + OrderExecutor as the curve router.
7. **P6 — Mainnet:** Safe 2/2 treasury, real DEX venue, audit.

## 6. Key risks
- **Regulatory**: agent tokens may be securities in some jurisdictions → disclaimers, no promises.
- **Curve design**: virtual reserves must be tuned to avoid instant graduation / cheap dumps.
- **Graduation venue**: Arc's AMM availability is early (see arc-smart-orders notes) → plan for
  StableFX/App Kit or our own locked pool.
- **Audit**: curve + factory must be audited before real value (UFSF/Uniswap-style programs may apply).
