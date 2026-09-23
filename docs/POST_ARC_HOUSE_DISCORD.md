# Posts for Arc House / Arc Discord (adapted from the X thread)

> These are the community-friendly versions. Attach the screenshot on your Desktop:
> **`arc-launchpad.png`** (Dashboard tab).

---

## A) Discord — single message (paste into `#showcase` / `#builders`)

> Post in **Arc Discord** → https://discord.com/invite/buildonarc (channel `#showcase` or `#builders`).
> Discord caps a message at 2000 chars; this fits.

```
🚀 **Arc Smart Orders + Agent Launchpad** — non-custodial smart orders + an AI-agent launchpad, live on **Arc mainnet**.

**Smart orders (non-custodial):** you sign an intent off-chain — a Permit2 `permitWitnessTransferFrom` committing `(tokenOut, minOut)`, or an EIP-712 `DcaIntent` for recurring orders. A keeper fills it on-chain, but the executor **recomputes the commitment** and reverts on mismatch → the keeper can never redirect the output or fill below the signed rate. Funds never leave your wallet until the fill; a 0.30% input-side fee goes to a Safe 2/2.

**Agent Launchpad:** launch an AI agent on its own **USDC bonding curve**. As the infra ships, agents get an ERC-8004 identity, ERC-8183 job escrow, and an ERC-4626 vault that shares the agent's USDC revenue with stakers.

**Why Arc:** USDC as gas (~$0.001/tx, no volatile gas), sub-second deterministic finality, Permit2 at the canonical address, and native ERC-8004/8183 standards.

**Engineering:** Safe 2/2 owns every contract, deterministic env-validated deploy, 34/34 Foundry tests, open audit package. Open source (MIT).

**Status (honest):** the launchpad (create + curve trading) is LIVE on mainnet. Smart-order fills + graduation are pending the Arc FX venue (StableFX is permissioned; no public AMM yet).

🔗 DApp: https://launchpad-neon-chi.vercel.app
🔗 Code: https://github.com/Salado210102/arc-smart-orders
```

---

## B) Arc House — post (title + body)

> Post in **Arc House** → https://community.arc.io (e.g. a "Showcase" / "Builders" space).

**Title:**
```
Arc Smart Orders + Agent Launchpad — live on Arc mainnet
```

**Body:**
```
Hi everyone — I'm an independent builder and I just shipped **Arc Smart Orders + Agent Launchpad** on Arc mainnet. Two parts:

**(1) Non-custodial smart orders for stablecoin FX (USDC ⇄ EURC).**
A user (or an AI agent) signs an order off-chain — a Permit2 `permitWitnessTransferFrom` whose witness commits `(tokenOut, minOut)`, or an EIP-712 `DcaIntent` for recurring/DCA orders. A keeper fills it on-chain, but the executor **recomputes the commitment** and reverts on mismatch, so the keeper can never redirect the output or under-fill. Funds never leave the wallet until the fill, and a 0.30% input-side fee routes to a Safe 2/2 treasury.

**(2) An AI-agent launchpad.**
An agent launches on its own **USDC bonding curve**. As the infrastructure ships, agents gain an **ERC-8004** identity, **ERC-8183** job escrow, and an **ERC-4626** vault that distributes the agent's USDC revenue to stakers (70/30).

**Why Arc:** USDC as the gas token, sub-second deterministic finality, Permit2 at the canonical address, and native ERC-8004 / ERC-8183 standards for the agentic economy.

**Engineering:** Safe 2/2 owns every contract; deterministic, env-validated mainnet deploy (it refuses to run if the owner isn't the Safe or an address has no code); 34/34 Foundry tests; open audit package. Open source, MIT.

**Honest status:** the launchpad — creating an agent and trading on its curve — is **live on mainnet**. Smart-order fills and graduation are **pending the Arc FX venue** (StableFX is permissioned and there is no public AMM yet). I'd love feedback, and I'm happy to use App Kit Swap / a public AMM as soon as it's available.

🔗 DApp: https://launchpad-neon-chi.vercel.app
🔗 Code: https://github.com/Salado210102/arc-smart-orders
🔗 Audit package: https://github.com/Salado210102/arc-smart-orders/blob/pre-audit-v2/docs/AUDIT_PACKAGE.md
```

---

## Where to post
| Place | How |
|---|---|
| Arc Discord `#showcase` / `#builders` | Paste **A** + attach `arc-launchpad.png` |
| Arc House (community.arc.io) | New post with **B** (title + body) + the image |
| Optional: reply to Arc/Circle | keep it short, link the DApp |
