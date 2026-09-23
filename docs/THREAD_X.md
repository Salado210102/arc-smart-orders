# Launch thread — X / Farcaster (final)

> Each cast/tweet < 280 chars. **Verify @handles before posting** (don't guess the Arc account).
> Repo: https://github.com/Salado210102/arc-smart-orders

---

**1/ 🧵 Hook**
```
Shipped Arc Smart Orders on @Arc 🟠

The first non-custodial smart-order engine on Arc with:
• Permit2 intents (witness + signed TWAP)
• an INPUT-SIDE platform fee (0.30%)
• agent-native execution (ERC-8004 + ERC-8183)

0 custody · USDC gas · sub-second finality.

E2E on testnet ▾
github.com/Salado210102/arc-smart-orders
```

**2/ The problem**
```
On-chain "orders" usually mean one of two bad options:

1) A custodial bot holding your funds.
2) A plain permit that only commits HOW MUCH a spender moves — not WHAT it buys, at what price.

A compromised keeper can swap to a worthless token or fill at a terrible rate.
```

**3/ The fix: enforce the intent**
```
Arc Smart Orders makes the signed intent the source of truth.

The user (or an AI agent) signs off-chain. A keeper executes through a verified OrderExecutor that RECOMPUTES the commitment on-chain and reverts on mismatch.

Funds never leave the wallet until the fill.
```

**4/ Two signing flows**
```
• LIMIT → Permit2 permitWitnessTransferFrom with a witness committing (tokenOut, minOut). Recomputed on-chain → the keeper can't redirect or under-fill.

• TWAP → PermitSingle + a signed EIP-712 DcaIntent (minRate = your FX limit), verified every part.
```

**5/ Input-side platform fee (protocol revenue)**
```
Revenue: a 0.30% (30 bps) fee taken in tokenIn BEFORE the swap → paid in USDC/EURC, zero slippage risk, straight to the treasury.

Verified on-chain: a 1.00 USDC order → 0.003 USDC to treasury, 0.997 net to the swap.

Cap hard-coded at 10%.
```

**6/ Agent-native execution**
```
The keeper is an ERC-8004 agent (on-chain identity + reputation).

Execution is paid via ERC-8183 job escrow: create → setBudget → fund → submit → complete.

So an AI agent can HIRE execution trustlessly — and build reputation doing it.
```

**7/ Verifiable linkage**
```
No ACP hook (they need whitelisting) — we link job ↔ fill verifiably:

deliverable = keccak256(fillTxHash)

The evaluator checks the fill matches the signed intent, then releases escrow. Non-custodial.
```

**8/ Proof (testnet, 3 separate wallets)**
```
ERC-8004 agent 896809 · ERC-8183 job 186650 → Completed

FILL (with fee) 0xb3bb5918…da8c
→ 0.003 USDC fee to treasury
→ 0.997 USDC net to swap

3 wallets: client / keeper / validator.
explorer.testnet.arc.io
```

**9/ Why Arc**
```
USDC is the gas token (~$0.001/tx) — no volatile gas.
Instant, deterministic finality — one confirmation.
Permit2 + ERC-8004 + ERC-8183 already deployed.

Stablecoins + agents are the native workload. @Arc is built for exactly this.
```

**10/ CTA + repo**
```
Open source (MIT): executor + SDK (TS/Python) + keeper + agentic layer.

github.com/Salado210102/arc-smart-orders

Next: production swap venue, Safe 2/2 treasury, unify with an AI-agent launchpad.

Building agentic finance on @Arc? Let's talk. 🛠️
```

---

## Repo presentation post (GitHub / community — long form)

```
Arc Smart Orders — non-custodial, agent-native order infrastructure on Arc

TL;DR
• Limit & TWAP FX orders (USDC ⇄ EURC) that are non-custodial and settle with gas in USDC.
• Signed intents (Permit2 witness for LIMIT, a signed EIP-712 DcaIntent for TWAP) — enforced on-chain.
• Input-side platform fee (0.30%, cap 10%) → treasury Safe. Verified E2E on Arc testnet.
• Agent-native: ERC-8004 identity + ERC-8183 job escrow (the keeper is an agent that gets paid & rated).
• Open source (MIT). Live demo + tx tree in DEPLOYMENTS.md.

Why it matters
Plain permits commit "how much" a spender can move, not "what" is bought. We make the intent the
source of truth: the executor recomputes the signed witness/intent and reverts if the outcome
doesn't match. The user (or an AI agent) keeps custody; the keeper can't redirect or under-fill.

What's shipped
• OrderExecutor v2 (Solidity): atomic pull → swap → verify; input-side fee; whitelisted targets.
• SDK (TypeScript) + verified Python signing recipe.
• Keeper (TypeScript/viem): 20-gwei floor, USDC gas, instant finality.
• Agentic layer: ERC-8004 register/reputation + ERC-8183 job lifecycle.
• Docs: LAUNCH, REVENUE, SAFE_TREASURY, DEPLOYMENTS, THREAD_X.

Verified on Arc testnet (3 adversarial wallets): agent 896809, job 186650 → Completed;
fill 0xb3bb5918…da8c (0.003 USDC fee → treasury, 0.997 net → swap).

Repo: https://github.com/Salado210102/arc-smart-orders
```

## Accounts to tag (VERIFY handles before posting)
- **Circle** — official `@circle` (verify).
- **Arc** — official handle TBD (find it via `arc.io` / `docs.arc.io`; don't guess).
- **ERC-8183 authors** (credit): `@dcrapis`, `@ai-virtual-b`, `@twx-virtuals`, `@Zuhwa`.
- ERC-8004 authors: see eips.ethereum.org/EIPS/eip-8004.

## Farcaster variant
Same casts in `/arc` (else `/dev`), attach the flow diagram + explorer links.
