# Launch thread — X / Farcaster

> Build-in-public, quant-engineering + AI-economy framing. Each cast/tweet is < 280 chars.
> **Before posting: verify the @handles** (I don't want to tag the wrong account). Suggested targets
> are listed at the end. Replace `@Arc`/`@circle` with the verified official handles.

---

**1/ 🧵 Hook**
```
Just shipped Arc Smart Orders — the first agentic, non-custodial order engine on @Arc.

Limit & TWAP FX orders (USDC ⇄ EURC) that are:
• 0% custody
• gas paid in USDC
• sub-second settlement
• agent-native (ERC-8004 + ERC-8183)

Full E2E live on testnet ▾
```

**2/ The problem**
```
On-chain "orders" usually mean one of two bad options:

1. A custodial bot holding your funds.
2. A plain permit that only commits HOW MUCH a spender can move — not WHAT it buys, nor at what price.

A compromised keeper = it can swap to a worthless token or fill at a terrible rate.
```

**3/ The fix: enforce the intent**
```
Arc Smart Orders makes the order intent the source of truth.

The user (or an AI agent) signs off-chain. A keeper executes through a verified OrderExecutor that RECOMPUTES the signed commitment and reverts on mismatch.

Funds never leave the wallet until the fill.
```

**4/ Two signing flows**
```
• LIMIT → Permit2 permitWitnessTransferFrom with a witness committing (tokenOut, minOut). The executor recomputes the witness on-chain → the keeper can't redirect or under-fill.

• TWAP → PermitSingle + a signed Eip712 DcaIntent (minRate = your FX limit), verified on every part.
```

**5/ Agent-native execution**
```
The keeper is an ERC-8004 agent (on-chain identity + reputation).

Execution is paid via ERC-8183 job escrow:
create → setBudget → fund → submit → complete.

So an AI agent can HIRE execution trustlessly — and build a reputation doing it.
```

**6/ Verifiable linkage**
```
No ACP hook (they need whitelisting) — we link job ↔ fill verifiably:

deliverable = keccak256(fillTxHash)

The evaluator checks the fill matches the signed intent, then releases escrow. Non-custodial, no whitelist.
```

**7/ Proof (testnet, 3 separate wallets)**
```
ERC-8004 agent 896807
ERC-8183 job 186648 → Completed

register      0xf6a2aeff…f8a5
createJob     0xda8de4bd…b4cb
FILL          0x4a1f3dd8…c714
complete      0xafabb974…8475
reputation    0x7c171ad1…24e3

explorer.testnet.arc.io
```

**8/ Collusion-resistant roles**
```
A · Client/Agent — signs intent, creates job, funds escrow
B · Keeper/Executor — ERC-8004 identity, fills, submits proof
C · Validator/Evaluator — releases escrow, records reputation

3 wallets. Nobody can both perform and self-approve.
```

**9/ Why Arc**
```
USDC is the gas token (~$0.001/tx) — no volatile gas exposure.
Instant, deterministic finality — one confirmation.
Permit2 + ERC-8004 + ERC-8183 already deployed.

Stablecoins + agents are the native workload. @Arc is built for exactly this.
```

**10/ CTA**
```
Open source (MIT) — executor + SDK + keeper:

github.com/Salado210102/arc-smart-orders

Next: wire the production swap venue, off-chain price readiness, publish SDKs.

Building agentic finance on @Arc? Let's talk. 🛠️
```

---

## Accounts to tag (VERIFY handles before posting)
- **Circle** — official: `@circle` (verify).
- **Arc** — official handle TBD; find it linked from `docs.arc.io` / `arc.io` (do **not** guess).
- **ERC-8183 authors** (credit, from the EIP): Davide Crapis `@dcrapis`, Bryan Lim `@ai-virtual-b`,
  Tay Weixiong `@twx-virtuals`, Chooi Zuhwa `@Zuhwa`.
- **ERC-8004** — see eips.ethereum.org/EIPS/eip-8004 for authors.
- Optionally: Circle DevRel / Arc DevRel accounts once verified.

## Farcaster variant
Same text as casts, in a `/arc` channel if it exists (else `/base` or `/dev`). Attach the flow diagram
image and the explorer links.
