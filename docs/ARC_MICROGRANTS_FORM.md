# Arc Microgrants — submission (READY — copy/paste)

> **Program:** Arc Microgrants · $500 USDC (20 of a $10k pool) · non-dilutive · route into the Circle Grant
> Program · [event page](https://community.arc.io/public/events/arc-microgrants-f8tijfjhyq)
> **Rules:** one submission per project · submissions close **Oct 14 2026 23:59 ET** · rolling review,
> all decisions by **Oct 21** · paid in **USDC on Arc**.
> **Eligibility:** deployed and working on **Arc MAINNET** · public repo · public builder profile.
> **No company needed** · individuals/pseudonymous welcome.
>
> ✅ **Eligible:** the protocol is **live on Arc mainnet (5042)** — contracts + DApp at
> `https://launchpad-neon-chi.vercel.app` — since 2026-09-23.

---

## Field-by-field answers

| Form field | Answer |
|---|---|
| **Project name** | Arc Smart Orders + Agent Launchpad |
| **Live deployment link (Arc mainnet)** | https://launchpad-neon-chi.vercel.app (DApp on Arc mainnet, chain 5042) |
| **Public repo** | https://github.com/Salado210102/arc-smart-orders (frozen tag `pre-audit-v2`) |
| **Builder profile** | GitHub `Salado210102` · X `@Cryptofun2026` |
| **Contact email** | hello@basepump.dev |
| **Payout wallet (USDC on Arc)** | `0x0FBFAF7069B45Dd9c16AdD8a04Bf556046EA7e93` (Safe 2/2) — or any wallet that can receive USDC on Arc |
| **Short description** | see below |
| **What it uses Arc for** | see below |

---

## Mainnet contract addresses (Arc chain 5042)

| Contract | Address |
|---|---|
| OrderExecutor | `0x9b3a990d1a31Ff5E01ddB8702e10F2529811FDb7` |
| AgentFactory | `0x4A80a4748A1d2AB37300780FcBC2FD28d2Ed393B` |
| AgentRegistry | `0x8aE509565397C62a585c74aA44f7E3bFEab3Bb01` |
| GraduationModule | `0x1B8CA122DFd1100C0873A517b4875611Ed9De792` |
| LiquidityLocker | `0x9cb011A46A1127202Bc92F48f70Bf7010F1f9B6C` |
| Safe 2/2 (treasury) | `0x0FBFAF7069B45Dd9c16AdD8a04Bf556046EA7e93` |

All verified on-chain at `https://explorer.arc.io` (see `DEPLOYMENTS.md`).

---

## Short description (paste)

> **Arc Smart Orders + Agent Launchpad** is a non-custodial protocol on Arc with two parts:
>
> **(1) Smart orders for stablecoin FX.** A user signs an order off-chain — a Permit2
> `permitWitnessTransferFrom` whose witness commits `(tokenOut, minOut)`, or an EIP-712 `DcaIntent` for
> recurring orders. A keeper fills it on-chain, but the executor **recomputes the commitment** and reverts
> on mismatch, so the keeper can never redirect the output or fill below the signed rate. A 0.30%
> input-side fee goes to a Safe 2/2 treasury.
>
> **(2) An Agent Launchpad.** A launching AI agent gets an **ERC-8004** identity, a USDC **bonding-curve**
> token, **ERC-8183** job escrow, liquidity **locked 365 days** at graduation, and an **ERC-4626** vault
> that pays the agent's USDC revenue to stakers (70/30).
>
> Live on Arc, open-source (MIT), 34/34 Foundry tests.

## What it uses Arc for (paste)

> **USDC-native:** gas is USDC, so the keeper pays ~$0.001/tx with no volatile gas exposure, and every fee
> and settlement is USDC. **Sub-second deterministic finality** lets the keeper confirm fills with a single
> confirmation. **Permit2** (deployed at the canonical address on Arc) is core to the order flow.
> The agentic track builds on Arc's **ERC-8004** registries (identity/reputation) and **ERC-8183
> AgenticCommerce** (job escrow) so AI agents can autonomously transact and settle in USDC.

---

## Supporting evidence (paste links if the form allows)

- Live DApp (Arc mainnet): https://launchpad-neon-chi.vercel.app
- Audit package (scope, sizes, tests): https://github.com/Salado210102/arc-smart-orders/blob/pre-audit-v2/docs/AUDIT_PACKAGE.md
- Mainnet deployment + tx hashes: https://github.com/Salado210102/arc-smart-orders/blob/pre-audit-v2/DEPLOYMENTS.md
- Tests: **34/34** Foundry + **1** Arc-mainnet-fork dry-run (deploy invariants verified).

---

## Pre-submit checklist

- [x] Mainnet deploy done (Safe 2/2 + 5 contracts on Arc 5042)
- [x] Live mainnet link opens (`launchpad-neon-chi.vercel.app`)
- [x] Repo public + frozen tag `pre-audit-v2` pushed
- [x] Builder profile set (GitHub `Salado210102` / X `@Cryptofun2026`)
- [x] Payout wallet can receive USDC on Arc
- [x] No secrets in the repo (`.secrets/` gitignored)
