# Arc / Circle — grant & partnership pitch

> Ready-to-send blurb for the **Arc ecosystem** (Arc Discord `discord.com/invite/buildonarc`,
> `community.arc.io`, or a Circle partnership contact). Circle/Arc have **no public grant form** at the
> time of writing — this text is the submission payload for whichever channel is available.

---

## Quick facts

| Field | Value |
|---|---|
| Project | **Arc Smart Orders + Agent Launchpad** |
| Applicant | BasePump (independent builder) · Vicente Gonzalez · hello@basepump.dev · @Cryptofun2026 |
| Repo (MIT) | https://github.com/Salado210102/arc-smart-orders |
| Live UI | https://launchpad-neon-chi.vercel.app |
| Network | Arc **testnet 5042002** (mainnet 5042 target) — built **only** on Arc + Circle stack |
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
- **Deployed + verified on Arc testnet** with a full agentic E2E (ERC-8004 agent → ERC-8183 job → fill →
  escrow release → reputation), live UI, and a persistent keeper (HTTP API + WebSocket + SQLite).
- **Safe-owned mainnet deploy rehearsed**: the exact `DeployMainnet` script ran on testnet with the
  **Safe 2/2** as owner/treasury, and the Safe executed the owner-only `registry.setFactory` tx.
- Open-source (MIT): contracts, SDK (TS + verified Python recipe), keeper, UI.

## The ask

1. **An audit subsidy** (or referral to a UFSF-eligible path) for the **9 contracts / 1,411 SLOC** scope in
   [`UFSF_AUDIT_PROPOSAL.md`](UFSF_AUDIT_PROPOSAL.md) — de-risks a live, fund-bearing non-custodial system.
2. **Ecosystem support / a mainnet go-live path**: the ERC-8004 / ERC-8183 registries are **not deployed
   on Arc mainnet** yet, which blocks the launchpad from going live there — guidance/coordination welcome.
3. Optional: **App Kit Swap / StableFX** integration as the production execution venue.

## Channels (verified)

- Arc community: https://community.arc.io/ · Discord `discord.com/invite/buildonarc` · X `@arc`
- Circle developer platform: https://developers.circle.com/ (no public grant form; "Agent Marketplace →
  Get listed" exists for distribution)
- UFSF (audit subsidy): `https://areta.fillout.com/ufsf-projects` — **requires a registered legal entity**;
  keep ready until incorporated.
