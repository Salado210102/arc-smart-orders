# Arc Microgrants — submission (ready to fill)

> **Program:** Arc Microgrants · $500 USDC (20 of a $10k pool) · non-dilutive · route into the Circle Grant
> Program · [event page](https://community.arc.io/public/events/arc-microgrants-f8tijfjhyq)
> **Rules:** one submission per project · submissions close **Oct 14 2026 23:59 ET** · rolling review,
> all decisions by **Oct 21** · paid in **USDC on Arc**.
> **Eligibility:** deployed and working on **Arc MAINNET** · public repo · public builder profile.
> **No company needed** · individuals/pseudonymous welcome.
>
> ⚠️ **We are NOT eligible yet:** the project runs on Arc **testnet** only. The block is the missing
> **ERC-8004 / ERC-8183** registries + a real **DEX venue** on mainnet. **Fill this once `DeployMainnet`
> has run.** Meanwhile, this doc is the exact payload.

---

## Field-by-field answers

| Form field | Answer |
|---|---|
| **Project name** | Arc Smart Orders + Agent Launchpad |
| **Live deployment link (Arc mainnet)** | ⏳ `https://explorer.arc.io/address/<OrderExecutor>` — **fill after mainnet deploy** |
| **Public repo** | https://github.com/Salado210102/arc-smart-orders (frozen tag `pre-audit-v2`) |
| **Builder profile** | GitHub `Salado210102` · X `@Cryptofun2026` |
| **Contact email** | hello@basepump.dev |
| **Payout wallet (USDC on Arc)** | `0x0FBFAF7069B45Dd9c16AdD8a04Bf556046EA7e93` (Safe 2/2) — or any wallet that can receive USDC on Arc |
| **Short description** | see below |
| **What it uses Arc for** | see below |

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

- Live UI: https://launchpad-neon-chi.vercel.app
- Audit package (scope, sizes, tests): https://github.com/Salado210102/arc-smart-orders/blob/pre-audit-v2/docs/AUDIT_PACKAGE.md
- Testnet deployment + tx hashes: https://github.com/Salado210102/arc-smart-orders/blob/pre-audit-v2/DEPLOYMENTS.md
- Tests: **34/34** Foundry + **1** Arc-mainnet-fork dry-run (deploy invariants verified).

---

## Pre-submit checklist

- [ ] Mainnet deploy done (`CONFIRM_MAINNET=1` + real `DEX_ROUTER`, `ERC8004_REGISTRY`, `ERC8183_ESCROW`)
- [ ] Live mainnet link opens on `explorer.arc.io`
- [ ] Repo public + frozen tag pushed
- [ ] Builder profile set (GitHub/X)
- [ ] Payout wallet can receive USDC on Arc
- [ ] No secrets in the repo (`.secrets/` gitignored) ✅
