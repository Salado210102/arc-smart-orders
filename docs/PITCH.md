# Arc Smart Orders & Agentic Execution Protocol

> One-pager for Arc / Circle grant & ecosystem applications.
> **Status: reference implementation, open source (MIT), NOT audited.** Some features are
> **testnet-only** or **pending external infra** — stated plainly below.

**Repo:** https://github.com/Salado210102/arc-smart-orders · **DApp:** https://arc.basepump.dev

## 1. Summary

Non-custodial execution infrastructure on **Arc**: limit/DCA orders authored as off-chain **EIP-712 +
Uniswap Permit2** intents and filled **atomically** by a keeper. Fills are gas-efficient (USDC-denominated,
sub-second finality) and the executor **recomputes the signed commitment on-chain** — the keeper can never
redirect the output or fill below the signed rate.

## 2. Standards

- **EIP-712 + Uniswap Permit2** — signed intents with in-contract `(tokenOut, minOut)` verification
  (witness for one-shot; a signed `DcaIntent` for recurring orders).
- **ERC-8004** (agent identity/reputation) and **ERC-8183** (job escrow / micro-payments) — integrated on
  Arc **testnet** (the registries are **not yet on Arc mainnet**).

## 3. Deployments

| Network | State |
|---|---|
| **Arc Mainnet (5042)** | Core contracts deployed and **owned by a Safe 2/2** `0x0FBFAF7069B45Dd9c16AdD8a04Bf556046EA7e93`. **Agent Launchpad is live** (launch + bonding-curve trading). Order **fills run in DRY-RUN** pending a swap venue (StableFX is permissioned; no public AMM on Arc yet). ERC-8004 identity is skipped until the registry ships. |
| **Arc Testnet (5042002)** | Full **E2E verified with real on-chain fills**. |

## 4. Infrastructure (production-ready)

- **Keeper engine** — multi-network, **PM2**, port-isolated: Mainnet **DRY-RUN :8788** / Testnet **LIVE :8789**.
- **Telemetry** — on-chain **keeper gas monitor** with **Telegram alerts** (~every 60 min).
- **Governance** — owner-only Safe setters (`setKeeper` / `setAllowedTarget` / `setFee`). No `Pausable`;
  emergency brake = revoke the swap target / rotate the keeper.

## 5. On-chain proof (testnet)

- **LIMIT fill E2E:** [`0xb075e97c8d7ce1693f750f8407e4b9785bec61a2011b289497069203dd6d71a8`](https://explorer.testnet.arc.io/tx/0xb075e97c8d7ce1693f750f8407e4b9785bec61a2011b289497069203dd6d71a8)
  → atomic **1 USDC → 0.917 EURC**, witness (`tokenOut=EURC`, `minOut`) enforced.
- **OrderExecutor (testnet):** `0xB19F1193BcC50c2aC0fdD9f1a28F95f7493f6Ee3`
- **MockStableRouter (testnet, test venue):** `0x228bea1763e9D52dF82714Cde250B12f1f175489`

## 6. Phase 2 (draft — not deployed, not audited)

- **`AgentCreditPool`** — peer-to-contract **USDC micro-credit** for AI agents (invite-only, first-loss
  reserve, per-agent/epoch caps, hybrid USDC bond + ERC-8004, keeper auto-repay via ERC-8183). Supports
  **cirBTC collateral** (LTV 70% / liquidation 80%).
- **`AgentYieldVault`** — **ERC-4626** vault on **cirBTC** with a pluggable yield strategy.
- **`RevenueSplitter` + `AgentStakingVault`** — agent revenue → 70% stakers / 30% treasury.
- **Python SDK** (`arc-agent-treasury`) — agents check balance / borrow / repay.

## 7. Links

- Repo (MIT): https://github.com/Salado210102/arc-smart-orders
- Audit package: `docs/AUDIT_PACKAGE.md` · Runbook: `docs/MAINNET_RUNBOOK.md`
- Deployments & tx hashes: `DEPLOYMENTS.md`
