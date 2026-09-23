# Dev community post — Arc Smart Orders + Agent Launchpad

> Ready to paste in **Arc/Circle Discord (`#dev-chat`), GitHub Discussions, dev forums, Farcaster**.
> Attach the screenshot `arc-launchpad.png` (Dashboard) when the platform allows images.

---

## Short version (Discord / Farcaster)

```
Hey builders 👋 — independent dev here. I shipped Arc Smart Orders + Agent Launchpad on Arc mainnet.

The interesting part is the non-custodial order flow: a user signs an intent off-chain (Permit2 permitWitnessTransferFrom whose witness commits tokenOut+minOut, or an EIP-712 DcaIntent for recurring orders). A keeper fills it on-chain, but the executor RECOMPUTES the commitment and reverts on mismatch — so the keeper can never redirect the output or fill below the signed rate. Funds stay in the wallet until the fill.

Part two is an AI-agent launchpad: an agent launches on its own USDC bonding curve (ERC-8004 identity + ERC-8183 job escrow + ERC-4626 staking as the infra ships).

Verifiable on-chain (Arc mainnet, chain 5042):
• OrderExecutor: 0x9b3a990d1a31Ff5E01ddB8702e10F2529811FDb7
• AgentFactory: 0x4A80a4748A1d2AB37300780FcBC2FD28d2Ed393B

Honest status: launchpad (create + curve trading) is LIVE on mainnet; smart-order fills + graduation are pending a venue (StableFX is permissioned; no public AMM yet). 34/34 Foundry tests, MIT, Safe 2/2 owns everything.

🔗 DApp: https://arc.basepump.dev
🔗 Repo: https://github.com/Salado210102/arc-smart-orders

Feedback welcome — especially on the witness/intent design and on the graduation-venue question. 🛠️
```

---

## Long version (GitHub Discussions / forum post)

**Title:** `Non-custodial smart orders + an AI-agent launchpad on Arc mainnet (open source, MIT)`

**Body:**

```markdown
Hi all — sharing an open-source protocol I built and deployed to **Arc mainnet (chain 5042)**.

## Why
Onchain stablecoin FX today is custodial or relies on thin AMM liquidity, and there's no safe, non-custodial way to post limit/TWAP orders — and no trust-minimized way for autonomous agents to trade and settle.

## What it does

### 1) Non-custodial smart orders (USDC ⇄ EURC)
- A user signs an order **off-chain**: a Permit2 `permitWitnessTransferFrom` whose **witness commits `(tokenOut, minOut)`**, or an EIP-712 `DcaIntent` for recurring/DCA orders.
- A **keeper** fills it on-chain, but the executor **recomputes the commitment** and **reverts on mismatch** → the keeper cannot redirect the output or under-fill.
- Atomic: pull → swap (whitelisted target) → refund leftover → verify `minOut`. A 0.30% input-side fee routes to a Safe 2/2.

### 2) Agent Launchpad
- An AI agent launches on its own **USDC bonding curve** (constant-product virtual reserves, anti-sniper limits).
- As the infra ships: **ERC-8004** identity, **ERC-8183** job escrow, and an **ERC-4626** vault that shares the agent's USDC revenue with stakers (70/30).

## Engineering
- Safe 2/2 owns every contract; deterministic, env-validated mainnet deploy (it refuses to run if the owner isn't the Safe or an address has no code).
- 34/34 Foundry tests; open audit package; MIT.
- Persistent keeper (HTTP API + SQLite worker) + live DApp.

## Verify
- OrderExecutor: `0x9b3a990d1a31Ff5E01ddB8702e10F2529811FDb7`
- AgentFactory: `0x4A80a4748A1d2AB37300780FcBC2FD28d2Ed393B`
- DApp: https://arc.basepump.dev
- Repo: https://github.com/Salado210102/arc-smart-orders

## Honest status & open questions
- Launchpad (create + curve trading): **live on mainnet**.
- Smart-order fills + graduation: **pending a venue** — StableFX is permissioned (institutions only) and there's no public AMM on Arc yet.
- **Question for the community:** what's the recommended on-chain FX venue on Arc for an independent builder? App Kit Swap looked non-composable (API-orchestrated), so I'm evaluating a minimal AMM or waiting for a public one.

Feedback on the witness/intent design and the graduation strategy is very welcome.
```

---

## Where to post
| Platform | Version |
|---|---|
| Circle Discord `#dev-chat` / `#general-chat` | Short |
| Arc Discord `#showcase` (when accepted) | Short |
| GitHub Discussions (repo → Discussions) | Long |
| Farcaster / X reply | Short |
| Reddit r/ethdev / r/CryptoCurrency (optional) | Long |
