# GEX Quant Agent — Technical Specification (GEX / 0DTE)

> **Status:** design spec (not implemented, not audited). Complements
> [`PHASE2_ARCHITECTURE.md`](PHASE2_ARCHITECTURE.md) and the smart-order engine in
> [`../contracts/src/OrderExecutor.sol`](../contracts/src/OrderExecutor.sol).

A **quantitative agent** that ingests **Gamma Exposure (GEX)** data — **Call Wall**, **Put Wall** and
**Zero Gamma** — and emits **low-latency EIP-712 signed orders** into `OrderExecutor v2` on Arc. The
agent is a *signal + order producer*; execution and settlement stay non-custodial on Arc.

---

## 1 · Scope & assumptions

- **Signal inputs are off-chain.** GEX is computed from an options chain on external venues
  (e.g. Deribit/CBOE/CME for the relevant underlying). Arc itself has no options venue.
- **Arc is the execution + settlement layer.** The agent trades a **tradable instrument on Arc**
  (today: the USDC⇄EURC stablecoin pair via a whitelisted `swapTarget`; tomorrow: any agent token or a
  tokenized asset). The mapping *signal → Arc instrument* is explicit (§5).
- **Non-custodial.** The agent only produces **signed intents** (or drives a delegated hot key). It never
  holds user funds; `OrderExecutor` enforces `minOut` / `minRate` on-chain.
- **Honest limits.** GEX edge is *statistical*, not guaranteed. This is not investment advice; 0DTE is
  high-risk. The agent ships **dry-run first** and with hard risk caps (§7).

---

## 2 · Glossary

| Term | Meaning |
|---|---|
| **GEX** | Gamma Exposure — dealer gamma per strike, `OI · Γ · S² · 0.01`, signed (calls +, puts −). |
| **Call Wall** | Strike with the largest **positive** GEX (dealer supply of upside gamma) → **resistance**. |
| **Put Wall** | Strike with the largest **negative** GEX (dealer demand of downside gamma) → **support**. |
| **Zero Gamma** | Price where **net GEX crosses 0** (a.k.a. gamma flip). Above → positive-gamma regime; below → negative-gamma regime. |
| **0DTE** | Options expiring the same day; pinning/vol regime is dominated by current expiry. |

---

## 3 · Architecture

```
        EXTERNAL OPTIONS DATA                    ARC (5042)
 ┌───────────────────────────────┐        ┌──────────────────────────┐
 │ 1. Market Data Collector       │        │ 7. Relayer / Keeper (B)  │
 │    options chain (OI, IV, Γ)   │        │    submits executeOrder  │
 └───────────────┬───────────────┘        └─────────────▲────────────┘
                 ▼                                       │
 │ 2. GEX Engine                                          │ signed order + swapData
 │    GEX per strike → Call/Put Wall, Zero Gamma         │
                 ▼                                       │
 │ 3. Signal / Strategy (0DTE)                  ┌────────┴──────────────┐
 │    regime: positive vs negative gamma        │ 6. Signer (EIP-712)    │
                 ▼                              │    hot key / EIP-1271  │
 │ 4. Risk & Sizing                            └────────▲──────────────┘
 │    caps, stops, kill-switch                          │
                 ▼                                       │
 │ 5. Order Builder ─────────── LIMIT / TWAP ───────────┘
 │    → minOut / minRate, deadline, tokenOut
```

Components are independent processes; the **hot path** (§8) is `3→4→5→6→7`.

---

## 4 · GEX Engine

### 4.1 Per-strike GEX
For each strike `K` and expiry `T`:

```
Γ_call(K,T) = ∂²C/∂S²     (Black–Scholes, from IV + T)
GEX(K,T)    = OI(K,T) · Γ(K,T) · S² · 0.01 · sign   (call: +1, put: −1)
NetGEX(p)   = Σ_K GEX(K, T_current) evaluated with spot = p
```

### 4.2 Derived signals (engine output)
```jsonc
{
  "underlying": "SPX|BTC|…",
  "spot": 5312.4,
  "ts": 1758660000,
  "callWall": 5350,          // max positive GEX strike
  "putWall": 5280,           // max negative GEX strike
  "zeroGamma": 5305.2,       // root of NetGEX(p) = 0
  "netGex": 1.8e9,           // regime sign
  "regime": "positive",      // positive | negative
  "expiry": "0DTE",
  "confidence": 0.72         // |netGex| / rolling σ, 0..1
}
```

**Computation notes**
- Use the **front expiry** for 0DTE; optionally a blend of the front two.
- `zeroGamma` = numerically solve `NetGEX(p) = 0` (bisection over `[spot·0.9, spot·1.1]`).
- Recompute on a **fixed cadence** (e.g. every 1–5 s) and on any IV/OI shock.

---

## 5 · Signal → order mapping

The GEX regime selects the *playbook*; the Arc instrument selects the *token*. Default mapping for the
USDC⇄EURC pair (signal → EURC direction), and the generic rule:

| Regime / level | Playbook | Action on Arc |
|---|---|---|
| **Positive gamma** (spot > zero gamma) | Mean-revert; fade moves | **Sell rallies into Call Wall / buy dips at Put Wall** (range) |
| **Negative gamma** (spot < zero gamma) | Trend/breakout; vol expands | **Buy breakouts above spot / sell breakdowns** |
| Spot **at/near Zero Gamma** | Ambiguous — stand down | **No trade** (or reduce size) unless confidence > threshold |
| Spot piercing **Call Wall** | Resistance test | Take profit / fade longs |
| Spot piercing **Put Wall** | Support test | Buy the dip (bounce) / stop out shorts |

```
onSignal(sig):
    if |sig.spot - sig.zeroGamma| < ZONE: return NO_TRADE
    if sig.regime == "positive":
        if sig.spot >= sig.callWall - ε: order = LIMIT_SELL   # resistance
        if sig.spot <= sig.putWall  + ε: order = LIMIT_BUY    # support
    else:  # negative gamma
        if sig.spot > sig.zeroGamma:     order = TREND_BUY
        else:                            order = TREND_SELL
    return size(order, sig.confidence)
```

**Instrument mapping** is a config table (`underlying → Arc tokenIn/tokenOut + scale`), so the same
engine can trade EURC today and another Arc asset later.

---

## 6 · Order construction (EIP-712, matches `OrderExecutor v2`)

Two native order types map cleanly to the executor:

### 6.1 LIMIT (one-shot) — Permit2 SignatureTransfer **with witness**
User/agent signs a Permit2 `PermitWitnessTransferFrom` whose witness commits the exact output:

```
PermitWitnessTransferFrom(TokenPermissions permitted,address spender,uint256 nonce,uint256 deadline,OrderIntent witness)
OrderIntent(address tokenOut, uint256 minOut)
TokenPermissions(address token, uint256 amount)
```

- `spender` **must equal** the executor address.
- The executor **recomputes** the witness on-chain from the live `tokenOut`/`minOut`, so the keeper can
  never redirect output or fill below `minOut`.
- SDK: `signLimitOrder(wallet, { tokenIn, tokenOut, amountIn, minOut, spender, nonce, deadline, chainId })`.

### 6.2 TWAP (recurring) — Permit2 AllowanceTransfer **+ signed intent**
For scaling in/out over the session, sign a `PermitSingle` **and** a `DcaIntent`:

```
DcaIntent(address owner, address tokenIn, address tokenOut, uint256 maxAmountIn, uint256 minRate, uint256 deadline)
```

- `minRate` = minimum `tokenOut` (base units) **per `1e18`** of `tokenIn` (base units) — the FX/price limit.
- The contract requires `minOut >= partAmount · minRate / 1e18` on **every** part.
- Domain: `name="ArcSmartOrders", version="1", verifyingContract=executor` — matches
  `OrderExecutor` and [`sdk/src/index.ts`](../sdk/src/index.ts).
- SDK: `signTwapOrder(wallet, TwapOrder)` → `{ permitSignature, intentSignature }`.

### 6.3 Translation from GEX levels
```
minOut   = expectedOut · (1 − slippageBuffer)         # LIMIT
minRate  = expectedRate · (1 − slippageBuffer) · 1e18 # TWAP
deadline = now + horizon                              # short for 0DTE (e.g. 60–300 s)
amountIn = clamp(riskBudget · confidence, min, maxNotional)
```
`expectedOut/expectedRate` come from the venue quote; `slippageBuffer` and `horizon` are risk params.

### 6.4 Signing
- **EOA hot key** for latency, or **EIP-1271 smart account** (e.g. a Safe) for operational security —
  `OrderExecutor` verifies both (`_verifyIntentSignature`).
- Pre-approve **Permit2** once for `tokenIn` (`ensurePermit2Approval`) outside the hot path.

---

## 7 · Risk controls (mandatory)

| Control | Rule |
|---|---|
| **Kill switch** | Halt on GEX feed staleness > `MAX_STALE_MS`, RPC errors, or daily drawdown > `MAX_DD`. |
| **Notional caps** | Per-order `maxNotional`, per-day cumulative cap, max concurrent orders. |
| **Slippage** | `slippageBuffer` bounded (`≤ MAX_SLIP_BPS`); `minOut`/`minRate` always set (never 0). |
| **Deadlines** | Short horizons; cancel/skip on expiry. |
| **Venue allowlist** | Only executor-whitelisted `swapTarget`s; never a new target inside the hot path. |
| **Confidence gate** | No trade when `|spot − zeroGamma| < ZONE` or `confidence < MIN_CONF`. |
| **Dry-run first** | Keeper `DRY=1`, log intended fills, compare vs realized before going live. |
| **Isolation** | Hot key holds only gas + working balance; treasury is the Safe. |

---

## 8 · Latency budget

Arc has **instant deterministic finality** (1 confirmation) and cheap USDC gas, so the binding costs are
off-chain. Target **end-to-end < 500 ms** signal→submission:

| Stage | Target | Notes |
|---|---|---|
| Data ingest → GEX recompute | 50–200 ms | cached chain; recompute only on delta |
| Signal + risk decision | < 5 ms | in-memory, precomputed thresholds |
| Order build (minOut/minRate) | < 5 ms | pure arithmetic |
| EIP-712 sign | 1–10 ms | local key / smart-wallet |
| Relayer submit → mempool | 50–150 ms | pre-warmed nonce, persistent HTTP |
| On-chain inclusion | ~instant (Arc finality) | single tx, atomic |

**Latency techniques**
- Pre-sign **standing intents** (bounded size/deadline) and refresh on signal change.
- Warm the nonce and Permit2 allowance; keep a persistent RPC connection.
- Co-locate the collector + signer with the keeper; avoid approval/setup txs in the hot path.

---

## 9 · Telemetry & observability

- **Structured logs** per decision: `{ ts, regime, spot, callWall, putWall, zeroGamma, confidence,
  orderType, amountIn, minOut|minRate, latency_ms }`.
- **Metrics**: signals/min, orders/min, fill rate, slippage (realized vs signed), PnL, reject reasons.
- **Alerts** via the existing Telegram bot pattern (`ops/launchpad-alerts.mjs`,
  `ops/keeper-metrics-bot.mjs`): feed staleness, kill-switch trips, drawdown breaches.

---

## 10 · Validation plan

1. **Replay/backtest** the GEX engine on historical chains → signal quality (hit rate, mean reversion
   vs momentum).
2. **Paper trading** with the keeper in `DRY=1` (`keeper/src/worker.ts` builds but does not broadcast).
3. **Testnet live** (`arc-keeper-testnet`, `DRY=0`) against `MockStableRouter`.
4. **Capped mainnet pilot** with tight `maxNotional` + kill switch, on the whitelisted venue.

---

## 11 · Mapping to the existing stack

| Spec component | Repo artifact |
|---|---|
| Order types, witness, intent | [`contracts/src/OrderExecutor.sol`](../contracts/src/OrderExecutor.sol) |
| Signing (LIMIT/TWAP) | [`sdk/src/index.ts`](../sdk/src/index.ts) — `signLimitOrder`, `signTwapOrder` |
| Submit/relay, dry-run, ERC-8183 link | [`keeper/src/worker.ts`](../keeper/src/worker.ts) |
| Backtest / paper harness | to be added (`keeper/src/` quant module) |
| Alerts/metrics | [`ops/keeper-metrics-bot.mjs`](../ops/keeper-metrics-bot.mjs) |

## 12 · Open questions / dependencies

- **Instrument availability on Arc:** GEX is on an external underlying; a tradable Arc proxy (FX pair
  today; tokenized asset/AMM later) is required to express the view. Until a real venue exists, the agent
  runs **dry-run** like the rest of the order engine.
- **Options data rights:** external feeds may require licensing.
- **Latency vs safety:** shorter horizons raise the value of pre-signed standing intents — needs a
  careful nonce/deadline policy to avoid stale-order fills.

> **Not investment advice.** Statistical strategies can lose money; 0DTE especially. Ship behind caps,
> dry-run, and a kill switch.
