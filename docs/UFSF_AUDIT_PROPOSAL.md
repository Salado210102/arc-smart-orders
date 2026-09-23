# Audit Proposal — Uniswap Foundation Security Fund (UFSF) / Circle Grant

**Project:** Arc Smart Orders + Agent Launchpad
**Applicant:** BasePump (independent builder) · hello@basepump.dev · @Cryptofun2026
**Repo (MIT):** https://github.com/Salado210102/arc-smart-orders
**Live UI:** https://launchpad-neon-chi.vercel.app
**Network:** Arc testnet (5042002) — mainnet target 5042
**Request:** audit subsidy (UFSF covers up to 100% of audit cost) · **scope: 9 contracts / 1,411 SLOC**

---

## 1. What we built (and why it matters for Uniswap)

Two products, both **non-custodial** and built on Uniswap's own **Permit2**:

1. **Smart-order engine** — limit / stop / trailing / DCA / grid / copy orders on Base & Arc. Users sign
   a Permit2 `permitWitnessTransferFrom` whose **witness** commits `(tokenOut, minOut)` (one-shot) or a
   signed `DcaIntent` (recurring). A verified `OrderExecutor` **recomputes the commitment on-chain** and
   reverts on mismatch — the keeper can never redirect the output or under-fill.
2. **Agent Launchpad** — launch an AI agent with an **ERC-8004** identity, a **USDC bonding-curve token**,
   **ERC-8183** job escrow, LP **locked** at graduation, and an **ERC-4626 vault** where holders stake the
   agent token to earn the agent's USDC revenue (via a `RevenueSplitter`).

**Uniswap alignment:** Permit2 is core to the order engine (Arc has Permit2 at the canonical address);
the team also ships on **Uniswap v4** — our Base launchpad graduates every token into a **v4 pool with a
custom hook** (`afterSwapReturnDelta` reward-tax) and locks the liquidity.

## 2. Scope to audit (from `docs/AUDIT_SCOPE.md`)

| # | Contract | Lines | Criticality |
|---|---|---:|---|
| 1 | OrderExecutor | 383 | 🔴 |
| 2 | AgentBondingCurve | 229 | 🔴 |
| 3 | AgentStakingVault (ERC-4626) | 153 | 🔴 |
| 4 | AgentFactory | 162 | 🟠 |
| 5 | GraduationModule | 109 | 🟠 |
| 6 | RevenueSplitter | 95 | 🟠 |
| 7 | AgentToken | 117 | 🟡 |
| 8 | LiquidityLocker | 83 | 🟡 |
| 9 | AgentRegistry | 80 | 🟢 |
| | **TOTAL** | **1,411** | |

Key invariants & threat model: `docs/AUDIT_SCOPE.md` §3–4 (witness recomputation, `k=x·y` curve
invariant, reserve non-drain, ERC-4626 accumulator precision, LP lock, fee cap, access control).

## 3. Maturity evidence

- ✅ **34/34 Foundry tests** (orders 17 · launchpad 8 · graduation 3 · staking 5 · revenue-wiring 1),
  incl. mainnet **fork** tests of the Permit2 witness against the real Permit2.
- ✅ **Deployed and verified** on Arc testnet (see `DEPLOYMENTS.md`), incl. a **full agentic E2E** run
  (ERC-8004 agent → ERC-8183 job → fill → escrow release → reputation) with on-chain tx hashes.
- ✅ **Live UI** (Vercel) + **persistent keeper** (HTTP API + WebSocket + SQLite worker).
- ✅ **Revenue wiring proven**: order fee (0.30% input-side) → `RevenueSplitter` → 70% to the staking
  vault / 30% treasury (`test/RevenueWiring.t.sol`).
- ✅ Documented **mainnet runbook** with a Safe 2/2 treasury and a deterministic `DeployMainnet.s.sol`.

## 4. Requested support

- **Primary:** an **audit subsidy** (UFSF programme) against the scope in §2. A subsidized audit
  de-risks a live, fund-bearing non-custodial system and lets us **open-source the reusable tooling**
  (Permit2 witness/intent execution, USDC bonding curve, ERC-4626 USDC-yield vault) to the broader
  Uniswap/Superchain ecosystem.
- **Secondary (optional):** a small **Circle/Arc** ecosystem grant for docs + localisation + a Unichain
  deployment path.

## 5. Budget indication

Audit of 1,411 SLOC across 9 contracts is typically a **small-to-mid** engagement. We request a
subsidy covering **up to 100%** of the quoted audit cost. Line-item quotes can be shared; the team can
also co-fund a portion.

## 6. Team

- **Vicente Gonzalez** — founder & engineer (solo, Spain). Built the whole stack end-to-end on Base
  mainnet and Arc testnet: contracts, SDK (TS + verified Python recipe), keeper, agentic layer, UI.

## 7. Links

- Repo: https://github.com/Salado210102/arc-smart-orders (audited commit: `fe4c977`)
- Scope: `docs/AUDIT_SCOPE.md` · Runbook: `docs/MAINNET_RUNBOOK.md`
- Deployments & tx hashes: `DEPLOYMENTS.md`
- Live UI: https://launchpad-neon-chi.vercel.app
