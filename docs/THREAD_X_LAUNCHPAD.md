# X (Twitter) thread — Arc Smart Orders + Agent Launchpad

> Post as a thread. Keep each tweet < 280 chars. Attach 1 screenshot (the DApp Agents tab) to tweet 1/.
> Live DApp: https://launchpad-neon-chi.vercel.app · Repo: https://github.com/Salado210102/arc-smart-orders

---

**1/**
We shipped a non-custodial smart-order engine + AI-agent launchpad on Circle's Arc mainnet.

Here's what it does, how the non-custodial part actually works, and what building on a USDC-native L1 teaches you. 🧵

@arc @circle

**2/**
Smart orders, non-custodially:
• user signs an intent off-chain (Permit2 witness committing tokenOut+minOut, or an EIP-712 DcaIntent)
• a keeper fills it on-chain
• the executor RECOMPUTES the commitment and reverts on mismatch

→ the keeper can never redirect output or under-fill.

**3/**
Funds never leave the user's wallet until the fill — no deposit, no custody. A 0.30% input-side fee routes to a Safe 2/2 treasury. Any leftover is refunded in the same tx.

**4/**
Part 2: an Agent Launchpad.
An AI agent launches on its own USDC bonding curve, with (as the infra ships) an ERC-8004 identity, ERC-8183 job escrow, and an ERC-4626 vault that shares the agent's USDC revenue with stakers.

**5/**
Why Arc fits: USDC IS the gas token (~$0.001/tx, no volatile gas), sub-second deterministic finality (1 confirmation), and Permit2 at the canonical address. The agentic track plugs into Arc's ERC-8004 + ERC-8183 standards.

**6/**
Engineering: Safe 2/2 owns every contract, deterministic env-validated deploy, 34/34 Foundry tests, and an open audit package. The mainnet deploy refuses to run if the owner isn't the Safe or an address has no code. Open source (MIT).

**7/**
Honest status: the launchpad (create + curve trading) is LIVE on Arc mainnet. Smart-order fills + graduation are pending the Arc FX venue — StableFX is permissioned and there's no public AMM yet. We say so, plainly.

**8/**
Live: https://launchpad-neon-chi.vercel.app
Code: https://github.com/Salado210102/arc-smart-orders
Built solo on Circle's Arc. Feedback welcome. 🚀

#Arc #Circle #USDC #DeFi #AIAgents #BuildOnArc

---

## Mentions & channels (verified)

| Target | Handle / link |
|---|---|
| Arc (X) | [@arc](https://x.com/arc) |
| Circle (X) | [@circle](https://twitter.com/circle) |
| Arc Discord | https://discord.com/invite/buildonarc |
| Circle Discord | https://discord.com/invite/buildoncircle |
| Arc House (community) | https://community.arc.io |
| Arc docs (for quoting) | https://docs.arc.io |

**Hashtags:** `#Arc` `#Circle` `#USDC` `#EURC` `#DeFi` `#AIAgents` `#BuildOnArc`

### Posting tips
- Tag **@arc** + **@circle** in tweet **1/** (reach) and keep them off later tweets.
- Attach the **DApp screenshot** to 1/ (Agents tab) — media boosts reach.
- Post during US-hours for the Arc/Circle dev crowd; then **quote-tweet 1/** into the Arc Discord `#showcase` and Arc House.
- Reply to your own 8/ with the audit package link if there's interest:
  `https://github.com/Salado210102/arc-smart-orders/blob/pre-audit-v2/docs/AUDIT_PACKAGE.md`

#Arc #Circle #USDC #DeFi #AIAgents #BuildOnArc
