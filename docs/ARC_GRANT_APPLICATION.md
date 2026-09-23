# Arc / Circle — grant & partnership pitch + funding-channel matrix

> Pitch + **verified funding-channel matrix** for the Arc/Circle ecosystem. The official channels are
> **Arc House events/forms** (there is **no public grants email**). Dates/eligibility verified **2026-09-23**.
> For the Microgrants field-by-field answers see [`ARC_MICROGRANTS_FORM.md`](ARC_MICROGRANTS_FORM.md).

---

## Quick facts

| Field | Value |
|---|---|
| Project | **Arc Smart Orders + Agent Launchpad** |
| Applicant | BasePump (independent builder) · Vicente Gonzalez · hello@basepump.dev · X @VICENTEGon651262 · LinkedIn linkedin.com/in/vicente-gonzalez-4a051b2a3 · Telegram @Cryptofun2026 |
| Repo (MIT) | https://github.com/Salado210102/arc-smart-orders |
| Live UI | https://arc.basepump.dev |
| Network | Arc **mainnet 5042** (live) — built **only** on Arc + Circle stack |
| Treasury | Safe **2/2** `0x0FBFAF7069B45Dd9c16AdD8a04Bf556046EA7e93` (owner + fee recipient) |

## One-liner

Non-custodial **limit/stop/trailing/DCA/grid/copy orders on Arc FX (USDC⇄EURC)** + a launchpad where
**AI agents get an ERC-8004 identity, a USDC bonding-curve token, ERC-8183 job escrow, locked liquidity,
and an ERC-4626 vault that pays the agent's USDC revenue to stakers**.

## Why it fits Arc's stated focus areas

- **Agentic economic activity / AI agents** — ERC-8004 identity + ERC-8183 job escrow, kept deliberately
  **non-custodial** (the keeper can never redirect a fill; the signed witness is recomputed on-chain).
- **Onchain FX (Stablecoin FX)** — the order engine settles USDC⇄EURC via Permit2
  `permitWitnessTransferFrom`; perfect for 24/7 FX with predictable, stablecoin-denominated fees.
- **USDC-native** — gas, fees and settlement are all USDC; platform fee (0.30%) routes to a Safe treasury,
  not to a token.
- **App Kit / StableFX synergy** — the `swapTarget` is pluggable; happy to integrate **Circle App Kit
  Swap** and/or **StableFX** as the graduation/execution venue instead of a mock.

## Maturity (all on Arc)

- **34/34 Foundry tests** incl. a mainnet-fork test of the Permit2 witness.
- **Deployed + verified on Arc** (testnet agentic E2E: ERC-8004 agent → ERC-8183 job → fill → escrow release →
  reputation, **plus live mainnet** Safe-owned deploy), live UI, and a persistent keeper (HTTP API + WebSocket + SQLite).
- **Safe-owned mainnet deploy rehearsed**: the exact `DeployMainnet` script ran on testnet with the
  **Safe 2/2** as owner/treasury, and the Safe executed the owner-only `registry.setFactory` tx.
- Open-source (MIT): contracts, SDK (TS + verified Python recipe), keeper, UI.

## The ask

1. **An audit subsidy** (or referral to a UFSF-eligible path) for the **9 contracts / 1,411 SLOC** scope in
   [`UFSF_AUDIT_PROPOSAL.md`](UFSF_AUDIT_PROPOSAL.md) — de-risks a live, fund-bearing non-custodial system.
2. **Ecosystem support / a mainnet go-live path**: the ERC-8004 / ERC-8183 registries are **not deployed
   on Arc mainnet** yet, which blocks the launchpad from going live there — guidance/coordination welcome.
3. Optional: **App Kit Swap / StableFX** integration as the production execution venue.

## Funding channels — matrix (verified 2026-09-23)

| Program | What you get | Key requirements | Individual-OK? | Deadline | Link |
|---|---|---|---|---|---|
| **Arc Microgrants** | **$500 USDC** (20 of a $10k pool), non-dilutive · route into the **Circle Grant Program** | **Live on Arc MAINNET** + public repo + builder profile (GitHub/X/Farcaster); 1 submission/project | ✅ yes — individuals, teams, pseudonymous, **no company** | **closes Oct 14 2026** 23:59 ET (decisions by Oct 21) | [event](https://community.arc.io/public/events/arc-microgrants-f8tijfjhyq) |
| **Arc Acceleration Season** | 6-week program · up to **$1M** access · Demo Day | LatAm fintech/AI startup; ship a live integration | teams/startups | **closed Sep 22 2026** | [event](https://community.arc.io/public/events/arc-acceleration-season-vanemu91dk) · [Airtable](https://airtable.com/appGGpgjSlDjntK7k/pagAoXwWYkoVVGbuB/form) |
| **Agentic Economy Prize** | **$50,000** (Circle-funded bonus) | Registered in *Build with Gemini XPRIZE* + use **Circle Agent Stack** + GCP hosting + a real USDC tx + public repo | teams | **Sep 25 2026** | [event](https://community.arc.io/public/events/the-agentic-economy-prize-aignfyumkq) |
| **UFSF** (audit subsidy) | up to **100%** of audit cost | **Registered legal entity** + KYB; not deployed on a non-Uniswap DEX | ❌ no (needs entity) | monthly cohorts (closes 7th) | [`areta.fillout.com/ufsf-projects`](https://areta.fillout.com/ufsf-projects) |
| **Uniswap Foundation Grants** | funding based on scope | Deploy to Unichain and/or Uniswap v4; docs; impact | (rolling) | rolling | [form](https://share.hsforms.com/1fxQjPQTgTYmPwlYxxKlSGQsdca9) |
| **Circle Grant Program** (Questbook) | **$5k–$100k USDC**, milestone-based (can fund an audit) | Live on Arc; Arc-central flow; Circle products (USDC/EURC) | ✅ yes (form asks "incorporated?" → non-incorporated allowed) | rolling / cohorts | [apply](https://circle.questbook.app/) · [info](https://www.circle.com/grant) |

### Read-out
- **Submitted:** **Arc Microgrants** (DoraHacks) **and** **Circle Grants Program — Cohort 2** (Questbook) — see §Submissions log.
- **Mainnet launchpad is LIVE** (create agent + bonding-curve trading, Safe-owned). Remaining mainnet gaps:
  a real **FX venue** (smart-order fills, keeper on `DRY=1`), **graduation** (needs an AMM), and the
  **ERC-8004/8183** registries (not deployed on mainnet yet).
- **Audit:** not done; requested via the Arc House post and inside the Circle Grant application (milestone 1).
- **UFSF** stays blocked until a legal entity exists.
- **No public email exists** for any of these; do not chase one.

## Submissions log

| Date | Program | Channel | Status |
|---|---|---|---|
| 2026-09-23 | **Circle Grants Program — Cohort 2** | Questbook (`circle.questbook.app`) | ✅ **submitted** (repo + deck + video + Drive) |
| 2026-09-23 | **Arc Microgrants** ($500) | DoraHacks BUIDL 49092 | ✅ submitted |
| 2026-09-23 | **Arc House** launch post | `community.arc.io` | ✅ approved / published |
| 2026-09-23 | **Arc House** audit-support post | `community.arc.io` | ✅ published |

## Community channels (not funding)
- Arc House: https://community.arc.io/ · Discord `discord.com/invite/buildonarc` · X `@arc`
- Circle developer platform: https://developers.circle.com/ (distribution: "Agent Marketplace → Get listed")
