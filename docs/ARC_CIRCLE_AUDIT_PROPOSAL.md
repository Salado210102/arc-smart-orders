# Audit Support Proposal — Arc / Circle ecosystem

**Project:** Arc Smart Orders + Agent Launchpad
**Applicant:** Vicente Gonzalez — independent builder (solo, Spain) · hello@basepump.dev · X @VICENTEGon651262 · Telegram @Cryptofun2026
**Repo (MIT):** https://github.com/Salado210102/arc-smart-orders
**Live UI:** https://arc.basepump.dev · **API:** https://api.basepump.dev
**Network:** Arc **mainnet (5042, live)** + testnet (5042002)
**Ask:** support for an **independent audit** of the fund-bearing core · **scope: 9 contracts / 1,411 SLOC**

> This is the **Arc/Circle-targeted** version of the audit proposal (`UFSF_AUDIT_PROPOSAL.md` was
> Uniswap-oriented and required a registered legal entity). Arc/Circle ecosystem programmes accept
> **individual builders**, which matches our current status.

---

## 1. What we built (Arc-native, non-custodial)

1. **Smart-order engine (USDC ⇄ EURC)** — a user (or an AI agent) signs an order **off-chain**: a Permit2
   `permitWitnessTransferFrom` whose witness commits `(tokenOut, minOut)` (one-shot), or an **EIP-712
   `DcaIntent`** for recurring/TWAP orders. A keeper fills it on-chain, but `OrderExecutor`
   **recomputes the commitment** and reverts on mismatch → the keeper can never redirect the output or
   under-fill. Files never leave the wallet until the fill; a **0.30% input-side fee** routes to a Safe 2/2.
2. **AI-agent launchpad** — an agent launches on its own **USDC bonding curve**; the roadmap adds an
   **ERC-8004** identity, **ERC-8183** job escrow, LP **locked 365d** at graduation, and an **ERC-4626
   vault** that distributes the agent's USDC revenue to stakers (70/30 via `RevenueSplitter`).

## 2. Why it matters for Arc / Circle

- **USDC-native**: gas and settlement are the same asset; the order engine is a natural fit for Arc's
  stablecoin FX pair, and the agentic layer uses Circle's **ERC-8004 / ERC-8183** standards.
- **Non-custodial, fund-bearing contracts** → an audit directly de-risks real user funds.
- **Reusable/open tooling** (MIT): Permit2 witness/intent execution, USDC bonding curve, ERC-4626
  USDC-yield vault — reusable by other Arc builders.
- **Cross-chain path**: a draft `CrossChainOrderExecutor` is ready to plug into **CCTP/Interop** once it
  ships on Arc.

## 3. Scope to audit (from `docs/AUDIT_SCOPE.md`)

| # | Contract | Lines | Criticality |
|---|---|---:|---|
| 1 | OrderExecutor | 383 | 🔴 (moves user funds) |
| 2 | AgentBondingCurve | 229 | 🔴 (holds USDC) |
| 3 | AgentStakingVault (ERC-4626) | 153 | 🔴 (principal + rewards) |
| 4 | AgentFactory | 162 | 🟠 (deploys the rest) |
| 5 | GraduationModule | 109 | 🟠 (liquidity) |
| 6 | RevenueSplitter | 95 | 🟠 (revenue) |
| 7 | AgentToken | 117 | 🟡 |
| 8 | LiquidityLocker | 83 | 🟡 (anti-rug) |
| 9 | AgentRegistry | 80 | 🟢 |
| | **TOTAL** | **1,411** | |

Invariants & threat model: `docs/AUDIT_SCOPE.md` §3–4 (witness recomputation, `k=x·y` curve invariant,
reserve non-drain, ERC-4626 precision, LP lock, fee cap, access control).

> **Out of scope (separate, later phase):** Phase-2 `AgentCreditPool`/`RevenueRouter`/`AgentYieldVault`
> and the cross-chain executor — currently **draft**, not deployed with funds.

## 4. Maturity evidence

- ✅ **Foundry tests green**: 34/34 core (orders 17 · launchpad 8 · graduation 3 · staking 5 ·
  revenue-wiring 1) **+ 30 more** (credit 21 · revenue-router 3 · cross-chain 6); mainnet-fork dry-run.
- ✅ **Live on Arc mainnet**: agent creation + bonding-curve trading; Safe-owned contracts (see
  `DEPLOYMENTS.md`).
- ✅ **Full E2E on testnet**: cross-chain-style witness fill and an **agentic run** (ERC-8004 → ERC-8183
  job → fill → escrow → reputation) with on-chain tx hashes; **Smart Swap** widget reaching `FILLED`.
- ✅ **Persistent keeper 24/7** (HTTP API + WS + SQLite worker), now served over **HTTPS**
  (`https://api.basepump.dev/arc-keeper` mainnet, `…/arc-keeper-testnet` testnet).
- ✅ **Deterministic deploy** + Safe 2/2 treasury; docs complete; **public HTTPS** endpoints.

## 5. Requested support

- **Primary:** **funding or facilitation of an independent audit** of the scope in §3 (Arc/Circle
  audit programme, security partner, or a grant earmarked for audit). We can also co-fund a portion.
- **Secondary (optional):** an Arc ecosystem grant for documentation/localisation and continued
  testnet→mainnet hardening.

## 6. Budget indication

1,411 SLOC across 9 contracts is a **small-to-mid** engagement (order of magnitude **≈ $10k–40k**
depending on the firm; competitive audits can be lower). We are happy to share line-item quotes and to
run a **competitive/community audit** (Code4rena / Cantina / Sherlock / CodeHawks) if that fits the
programme better.

## 7. Team

- **Vicente Gonzalez** — founder & engineer (solo, Spain). Built the full stack end-to-end on Arc:
  contracts, TS + Python SDKs, keeper, agentic layer, UI. No incorporated entity (independent builder).

## 8. Links

- Repo: https://github.com/Salado210102/arc-smart-orders (frozen tag `pre-audit-v2`)
- Package: `docs/AUDIT_PACKAGE.md` · Scope: `docs/AUDIT_SCOPE.md` · Runbook: `docs/MAINNET_RUNBOOK.md`
- Deployments & tx hashes: `DEPLOYMENTS.md`
- Live UI: https://arc.basepump.dev · API: https://api.basepump.dev/arc-keeper/health

## 9. Honest status

The launchpad (create + curve trading) is **live on mainnet**. Smart-order **fills** and **graduation**
on mainnet are **pending an FX venue** (StableFX is permissioned; no public AMM yet) — the keeper runs in
**dry-run** until then. The whole codebase is **unaudited**. An audit now de-risks the live, fund-bearing
contracts before those features are switched on.
