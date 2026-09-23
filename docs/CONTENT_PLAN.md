# Content & distribution plan — 4 weeks

> Goal: **real usage**, not followers. Metrics that matter: **agents launched**, **fills**, **stakers**, and
> **devs integrating the SDK**. Channels: **X** (@VICENTEGon651262), **Arc House**, and (when available)
> Arc Discord / Farcaster. Tone: honest, technical, build-in-public. Cadence: **1 post/week** minimum.

## The plan at a glance

| Week | Theme | Where | Format | Draft |
|---|---|---|---|---|
| 1 | **Live** — fills + staking | X thread + Arc House post | announce | Thread A (posted) · Post B (below) |
| 2 | **How it works** (trust) | X thread | education | Thread C |
| 3 | **Build with it** (devs) | X thread + Arc House | outreach + snippet | Thread D |
| 4 | **Agents & treasury** (narrative) | X thread | vision | Thread E |

Rules: tag **@arc @circle @Uniswap**; attach **screenshots**; always link the repo; reply to your own
thread with the release; respond to every comment the first 24h.

---

## Post B — Arc House (week 1)

> Post in **Arc House** → https://community.arc.io

**Title:**
```
Live on Arc mainnet: smart-order fills + staking & yield
```

**Body:**
```
Hi all — update from a solo builder on Arc mainnet. Two new things are live:

1) Smart-order fills are live. You sign an order off-chain (Permit2 witness / EIP-712); a keeper fills it
on-chain via Uniswap v3, but the contract enforces your signed minOut — the keeper can't redirect the
output or under-fill. Funds never leave your wallet until the fill.

2) Staking & Yield is live. Each agent token gets an ERC-4626-style vault; the agent's revenue streams
70% to stakers / 30% to the Safe treasury, in USDC. Verified on-chain (a staker already claimed yield).

Try it → https://arc.basepump.dev
Code (MIT) → https://github.com/Salado210102/arc-smart-orders

Feedback welcome!
```

---

## Thread C — week 2 (education: why the keeper can't cheat)

**Tweet 1**
```
How do you trust a keeper with your order? You don't — you make the contract enforce it. 🧵

A quick look at why Arc Smart Orders stays non-custodial. @arc
```

**Tweet 2**
```
You sign a Permit2 witness committing (tokenOut, minOut) — or an EIP-712 DcaIntent for recurring orders.

The executor recomputes that commitment on-chain from the live trade and reverts on any mismatch. The
keeper literally cannot redirect the output or under-fill.
```

**Tweet 3**
```
Funds stay in your wallet until the fill. The 0.30% fee goes to a Safe 2/2.

Code (MIT) → https://github.com/Salado210102/arc-smart-orders
Try it → https://arc.basepump.dev
```

---

## Thread D — week 3 (developer outreach)

**Tweet 1**
```
Quant dev? You can sign an Arc Smart Order in two calls — TypeScript and Python SDKs. 👇 @arc
```

**Tweet 2**
```python
from arc_smart_orders import ArcSmartOrdersClient, to_units
c = ArcSmartOrdersClient(private_key=os.environ["ARC_PK"])
c.submit_limit_order(amount_in=to_units("1"), min_out=to_units("0.90"))
```

**Tweet 3**
```
Orders settle on Arc mainnet via Uniswap v3 — non-custodially.

Repo → https://github.com/Salado210102/arc-smart-orders
Feedback / PRs welcome. Building an agent? Let's talk.
```

---

## Thread E — week 4 (narrative: agentic treasury)

**Tweet 1**
```
The agentic economy needs agents that can pay their own way — in USDC, non-custodially. 🤖 @arc
```

**Tweet 2**
```
Launch an agent → it gets a USDC bonding curve, and its revenue streams 70% to stakers / 30% to a Safe
treasury, through an ERC-4626 vault. Live on Arc mainnet.
```

**Tweet 3**
```
Built solo, USDC-native on @arc. Try it → https://arc.basepump.dev
@circle @Uniswap
```

---

## Evergreen snippets (reuse anytime)
- "First live fill on Arc mainnet — non-custodially, via Uniswap v3" + tx link.
- "A staker just claimed USDC yield from an agent's revenue" + tx link.
- "Sign a limit order in 2 lines (TS/Python)" + snippet.
