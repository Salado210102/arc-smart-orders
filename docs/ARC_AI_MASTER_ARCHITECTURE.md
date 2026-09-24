# ARC AI — MASTER ARCHITECTURE (Revision 02)

> **Status: architecture proposal only. NO production code written, modified, installed, committed or
> deployed.** Prepared for the project owner's review.
> Revision 02 incorporates the owner's architectural decisions (custody, scope, paper-first, provider-agnostic
> AI, data day-1, feature store, backtest/evaluation, event replay, tool layer, venue adapters, community AI,
> monetization, compliance). **Revision 02 is authoritative** over Revision 01.

---

## 0. Decisions incorporated in Revision 02 (authoritative)

| # | Decision |
|---|---|
| 1 | **Non-custodial** custody. The LLM never touches keys and never signs arbitrary txs. |
| 2 | **Arc-only** scope for the MVP; keep interfaces modular for future chains. |
| 3 | **Paper trading FIRST**; real trading only after explicit validation gates. |
| 4 | **Provider-agnostic AI** (`AIProvider` interface). LLM interprets; it does not compute quant. |
| 5 | **Index Arc from day 1** — the data layer is a core asset. |
| 6 | New core module: **Backtest & Evaluation Engine**. |
| 7 | New core module: **Feature Store** (versioned features). |
| 8 | New core module: **Event Replay Engine**. |
| 9 | New core layer: **AI Tool Layer** (controlled tools; no raw DB/exec for the LLM). |
| 10 | **Venue Adapter** architecture (pluggable DEX venues). |
| 11 | Future **Community AI** (GREEN/YELLOW/RED; Spanish→English). |
| 12 | Future **Telegram Launchpad** (design room only, not built). |
| 13 | **Monetization: free core + trading fees** (premium later). |
| 14 | **Brand/compliance** requirements designed in (no guaranteed returns). |
| 15 | Final pipeline principle (§15). |

---

## 1. Executive summary

**ARC AI** is an AI-native **trading + on-chain intelligence** platform for **Arc** (Circle's stablecoin L1),
delivered primarily as a **Telegram bot**, built on a **non-custodial** architecture.

The moat is **proprietary Arc data + a deterministic quant engine**:

```
ARC → DATA ENGINE → FEATURE STORE → QUANT ENGINE → (SMART MONEY / CONSENSUS / PATTERN / RISK)
    → AI INTERPRETATION → TELEGRAM → USER → PAPER TRADE → VALIDATED EXECUTION
    → MONITORING → HISTORICAL OUTCOME → BACKTEST / EVALUATION
```

**MVP = intelligence + paper trading** (no real capital). **Real trading is gated behind proven validation.**

**Hard principle:** LLM *interprets/proposes*; a **deterministic engine** computes, validates and (only when
enabled) executes within hard limits. **The LLM never holds keys and never signs.**

---

## 2. Product vision

An **AI trading copilot + on-chain intelligence** for Arc: Smart Money (quantified), Consensus, Why engine,
Pattern recognition, Risk/manipulation, Exit intelligence, conversational analysis, paper trading → gated
automation, Community/Social AI, and (future) a Telegram launchpad.

---

## 3. Current repository architecture (inspected — reusable)

Monorepo `arc-smart-orders` (MIT), all reusable:
- `contracts/` (Foundry): `OrderExecutor.sol` (**live, non-custodial intent executor**), `CrossChainOrderExecutor.sol`,
  `launchpad/*` (factory/curve/registry/graduation/locker/agent token/splitter/staking vault),
  `credit/*` (AgentCreditPool/RevenueRouter/AgentYieldVault), `mev/*` (liquidation/oracle-arb/JIT/Morpho).
- `keeper/` (TS+viem): Fastify API + WS + SQLite worker (fills orders; ERC-8004/8183 agentic).
- `sdk/` (TS EIP-712/Permit2 signing), `sdk-python/`, `bots/` (Python AsyncWeb3 monitors).
- `apps/launchpad/` (Vite/React/Tailwind), `ops/`, `docs/`, `.github/workflows/ci.yml`.

**Already proven:** non-custodial order signing (Permit2 witness + EIP-712 `DcaIntent`), keeper execution,
Safe 2/2 treasury, HTTPS APIs, PM2 24/7, CI green.

> **This is our custody foundation** — see §11 and §5.

---

## 4. Proposed architecture (high level)

```
                        ┌──────────────────────── ARC AI ────────────────────────┐
 Telegram users / Web   │ BOT LAYER (grammY)  ·  ALERT LAYER (Telegram)          │
                        └───────▲───────────────────────────────▲────────────────┘
                                │                               │
                    ┌───────────┴───────────┐                   │
                    │ AI ORCHESTRATOR        │                   │
                    │ (provider-agnostic)    │                   │
                    └───▲───────────┬────────┘                   │
        reads facts     │           │ controlled tools (§9)      │ facts
                    ┌───┴───────────▼────────────────────────────────────────┐
                    │ AI TOOL LAYER  (schema + authz + logging + rate limits)  │
                    └───▲──────────────────────────────────────────────────────┘
                        │
   ┌────────────────────┴──────────────────────────────────────────────────────┐
   │ QUANT ENGINE  (Smart Money · Consensus · Pattern · Risk · Exit)            │
   ├────────────────────────────────────────────────────────────────────────────┤
   │ FEATURE STORE (versioned)  ·  BACKTEST & EVALUATION ENGINE  ·  EVENT REPLAY │
   ├────────────────────────────────────────────────────────────────────────────┤
   │ DATA ENGINE: indexer (RPC + WS) + optional 3rd-party indexers → PostgreSQL │
   │              + Redis (hot cache/queues)                                    │
   ├────────────────────────────────────────────────────────────────────────────┤
   │ EXECUTION ENGINE (viem) → VENUE ADAPTERS → contracts (owner = Safe)        │
   └────────────────────────────────────────────────────────────────────────────┘
```

**Monorepo additions (later):** `arcai/` workspace = `data/`, `features/`, `quant/`, `backtest/`, `replay/`,
`ai/` (orchestrator + providers + tools), `bot/`, `alerts/`, `exec/` (venue adapters), `risk/`.

---

## 5. Custody — NON-CUSTODIAL (decision #1)

**The LLM/user key is never held by the bot.** Trading is **intent-based and user-signed**, reusing the
existing repository's proven pattern.

### 5.1 Conceptual flow (matches the owner's requirement)
```
USER → AI → structured trade intent → RISK ENGINE → SIMULATION (eth_call)
     → USER AUTHORIZATION / SIGNATURE → EXECUTION (keeper) → MONITORING
```

### 5.2 How it works with the existing repo
- **Intent types (already implemented):**
  - LIMIT: Permit2 `permitWitnessTransferFrom` with witness `(tokenOut, minOut)` (`OrderExecutor.sol`).
  - Recurring: our EIP-712 `DcaIntent(owner, tokenIn, tokenOut, maxAmountIn, minRate, deadline)`.
- **Signing:** client-side (web companion via wagmi/viem, or wallet) using `sdk/src/index.ts`
  (`signLimitOrder`, `signTwapOrder`). **The bot never receives a private key.**
- **Execution:** the existing **keeper** submits the signed intent to `OrderExecutor`; the contract
  **recomputes the commitment on-chain** and reverts on mismatch — the keeper cannot redirect output or
  under-fill.
- **Telegram UX:** the bot prepares a "sign link" (deep link to the web companion). The user signs there;
  the bot receives the signed intent (or its hash) and hands it to the keeper. **No keys in Telegram.**
- **Optional later:** an **embedded wallet** (managed key) may be offered **only** with envelope encryption
  + KMS + hard caps + explicit custody disclosure + withdrawal protection. **Off by default.** (See §11.)

### 5.3 Hard bans (enforced by design)
The LLM must **never**: access/receive private keys · sign arbitrary txs · execute arbitrary txs · have
unrestricted execution authority. The LLM can only call **typed tools** (§9) that produce **validated intents**.

---

## 6. Blockchain scope — ARC ONLY (decision #2)

- **MVP targets only Arc mainnet (5042)** (+ testnet 5042002 for dev).
- **No multi-chain implementation** in the MVP.
- **Modular interfaces** (data providers, venue adapters, AI providers) so a future chain can be added by
  implementing the interface **without rewriting the intelligence engine**.

---

## 7. Data architecture — indexed from DAY 1 (decision #5)

**Verified Arc facts:** chainId 5042; RPC `https://rpc.mainnet.arc.io`; WS via Alchemy/Blockdaemon/QuickNode;
gas = USDC (18-dec native / 6-dec ERC-20 interface); min base fee 20 gwei; ~$0.001/tx; ~0.5s blocks;
explorer `explorer.arc.io`; `viem` ships `arc`/`arcTestnet`.

**Ingestion:** block poller + **WebSocket log subscriptions** for hot contracts (Uniswap routers/pools,
launchpads, our contracts). Backfill via **chunked `eth_getLogs`** (~2k-block chunks; Arc RPC range caps).

**Store:** **PostgreSQL** as source of truth; **Redis** for caches/queues/rate limits.

**Datasets (day 1, where technically/legally appropriate):** blocks, transactions, **swaps**, tokens, pools,
liquidity, prices, wallets, **wallet & funding relationships**, token launches, smart-money events, alerts,
signals, **signal outcomes**, paper trades.

**Providers:** primary + fallback RPC; optional third-party indexers; **avoid permanent dependence on any single
provider**; retain raw logs so every metric can be recomputed (auditable).

---

## 8. Feature Store (decision #7)

A **versioned** store of the quantitative features used by the intelligence engine. Features are computed by
the **Quant Engine** (not the LLM) and **versioned** (`feature_key`, `version`, `computed_at`, `as_of`).

**Wallet features:** realized PnL · unrealized PnL · win rate · trade count · avg/median return · avg holding
time · recent performance · drawdown · liquidity-adjusted performance.

**Token features:** liquidity · volume 1m/5m/1h · price movement · holder concentration · wallet concentration ·
deployer relationships.

**Market features:** smart-money count · smart-money convergence · wallet-quality distribution · funding-cluster
score · manipulation indicators · liquidity changes · volume acceleration.

> **Not finalizing formulas.** Every feature is an **as-of** computation (no look-ahead), versioned, and
> reproducible from raw data.

---

## 9. AI Tool Layer (decision #9)

The LLM gets **no** raw SQL and **no** signing/exec rights. It can only call **typed tools**:

```
getTokenAnalysis() · getWalletAnalysis() · getSmartMoneyConsensus() · getRiskAnalysis()
getHistoricalPatterns() · getPortfolio() · getPaperTrade() · createTradeIntent()
```

Each tool has **strict input schema · strict output schema · authorization rules · logging · rate limits ·
error handling**. `createTradeIntent()` only produces a **structured intent** (never a signed tx).

---

## 10. AI architecture — provider-agnostic (decision #4)

```
AIProvider (interface)
├── ProviderImpl A
├── ProviderImpl B
└── ProviderImpl C
```

- **Switchable LLM** without touching the trading/intelligence system.
- **Division of labor:** QUANT ENGINE **calculates facts**; AI ENGINE **interprets facts** (never computes
  PnL/score/risk itself).
- **Structured outputs** + schema validation; tools are allow-listed; the AI can **refuse** when evidence is
  insufficient ("no inventar").
- **No secrets/PII** in prompts; **cache** + model routing + per-request cost tracking.

---

## 11. Security architecture

- **Non-custodial first** (§5). Embedded wallet opt-in only, with **envelope encryption + KMS**, per-user
  isolation, hard caps, withdrawal protection, explicit disclosure.
- **Telegram auth** (telegram user id) + **2FA for withdrawals**; inline **confirmation** for destructive
  actions; **2-step approval** above thresholds.
- **Transactions:** mandatory **simulation (`eth_call`) + `estimate_gas`** before send; **malicious-contract
  detection** (known-bad lists, unusual approvals); **approval hygiene**; **per-tx/daily/per-user spend limits**;
  **emergency stop**.
- **LLM isolation:** tools-only; no keys; no raw DB; no arbitrary exec; full **audit log** (user, intent, tx,
  outcome).
- **Secrets:** env on VPS (chmod 600) or a manager; never in source/git/prompts.
- **Contracts:** owner = **Safe**, execution via **keeper** hot key (roles already implemented in our modules).

---

## 12. Trading / execution architecture

- **Venue Adapter architecture (decision #10):**
  ```
  VenueAdapter
  ├── UniswapV3Adapter      (SwapRouter02 0x53BF6B0684Ec7eF91e1387Da3D1a1769bC5A6F77)
  ├── UniswapV4Adapter      (Universal Router 0x4fcA4a51Ab4F23A7447b3284fBd7D73289A89Fb1)
  ├── LaunchpadDexAdapter(s)
  └── FutureVenueAdapter
  ```
  Start with the **minimum, most liquid + reliable** venue(s) only; add venues by implementing the interface.
- **Pipeline:** quote → build → **simulate** → **risk checks** → **user signature** → keeper/exec → receipt →
  **retry/idempotency** → **monitoring**. Never send a tx that fails simulation.
- **Nonce management**, spend limits, emergency stop (per user + global).
- **Arc MEV reality:** permissioned validators, no public mempool → optimize **reliability**, not latency races.

---

## 13. Quantitative intelligence architecture

- **Smart Money Score (methodology, not final):** robust **z-scores across a cohort** (not fixed thresholds),
  winsorized, **liquidity-adjusted** returns `r_liq = r · min(1, liq_at_entry / notional)`, recency-weighted;
  output 0–100 **with confidence + raw metrics** (explainable).
- **Consensus (candidate models):** count×quality · time-decayed convergence with **independence factor** ·
  **statistical surprise z-score** vs a baseline convergence rate (preferred — defensible).
- **Decay:** detect **active vs decaying** smart money via **exponential weighting with a tunable half-life**
  (chosen by cross-validation); validate out-of-sample.
- **Exit intelligence:** monitor the **same wallets** that produced the signal; detect net reduction/exit and
  consensus deterioration.
- **Bias controls (mandatory):** look-ahead, survivorship, leakage, selection, small-sample overfitting.

---

## 14. Backtest & Evaluation Engine (decision #6 — NEW CORE MODULE)

Evaluates **every** signal using **only information available at signal time**.

**Per signal, stored:** timestamp · market state · **features (as-of)** · model/algorithm **version** · signal
score · entry assumption · liquidity · estimated slippage · subsequent outcomes.

**Metrics:** win rate · median return · mean return · drawdown · false positives · false negatives ·
liquidity-adjusted results · slippage-adjusted results · **sample size (with CI)**.

**Protections:** look-ahead bias · survivorship bias · data leakage · selection bias · small-sample overfitting.

> **No profitability claim without statistically meaningful validation.**

---

## 15. Event Replay Engine (decision #8 — NEW)

Reconstruct the market **as-of** a historical point, using **only data available then**.
Example: `replay Arc market state at 2026-09-20 14:00`. Used for **backtesting, debugging, model evaluation,
strategy research**, and **avoiding look-ahead bias**. Requires: immutable raw logs + as-of feature queries +
deterministic replay clock.

---

## 16. Paper trading + real-trading gates (decision #3)

**Paper trading is the default.** Real trading is **disabled** until the validation phase proves the
**infrastructure and measurement framework** (not a profit promise).

### 16.1 Paper trading (Phase P2)
Simulated entry/exit, PnL, fees, slippage, drawdown, win rate, trade count — evaluated by the Backtest Engine.

### 16.2 Real-trading readiness gates (all must pass; no arbitrary performance guarantees)
1. **Data correctness:** block/swap/price/position reconciliation vs explorer on a sampled audit.
2. **Measurement correctness:** PnL/score/consensus/risk validated on hand-checked cases + OOS windows.
3. **Engine correctness:** simulation matches on-chain outcome for N dry-run intents; slippage model calibrated.
4. **Reliability:** alert pipeline delivery/reliability measured; no duplicate/lost alerts.
5. **Safety:** limits, emergency stop, malicious-contract checks, and audit log verified in a staged test.
6. **Paper→live parity:** paper results reproduce from the same inputs (deterministic replay).
7. **Explicit owner approval** + caps.

Only after 1–7: enable **capped** real execution (one venue, small limits, 2FA, kill-switch).

---

## 17. Telegram architecture

`grammY`; commands + **NLP→intent**; inline buttons/confirmations; per-user state; **approval flows**; deep
links to the web companion for **signing**; watchlists; alerts (consensus/exit/position). **No secrets in chat.**
Rate limiting + anti-spam + full audit log.

---

## 18. Community AI (future — decision #11)

Agents for **Telegram, X, announcements, FAQs, moderation, translations, educational content, product updates,
research summaries**. Permission tiers: **GREEN** (auto low-risk) · **YELLOW** (human approval) · **RED**
(human-only). **Owner inputs Spanish → professional English output.** No autonomous publishing of YELLOW/RED.

---

## 19. Future Telegram Launchpad (future only — decision #12)

Design room reserved; **not built now**. Future flow: `Telegram → AI Launch Assistant → token config → deploy
→ liquidity → launch → community → trading → monitoring`, reusing `contracts/src/launchpad/*`.

---

## 20. Monetization + brand/compliance (decisions #13, #14)

**Monetization:** **FREE CORE + TRADING FEES** (primary). Future premiums: advanced intelligence, automation,
API, pro tools. **No mandatory subscription for the MVP** (goal = adoption, data, validation).

**Brand/compliance (design-in, no spend yet):** trading **risk disclosures**; **no guaranteed returns**; **no
claims that AI predicts prices**; clear **analysis ≠ financial advice**; **paper ≠ live** clearly separated;
**transparent fees**; **explicit user authorization** for real transactions.

---

## 21. Final architecture principle (decision #15)

```
ARC BLOCKCHAIN → DATA ENGINE → FEATURE STORE → QUANT ENGINE
→ (SMART MONEY / CONSENSUS / PATTERN / RISK) → AI INTERPRETATION → TELEGRAM → USER
→ PAPER TRADE → VALIDATED EXECUTION → MONITORING → HISTORICAL OUTCOME → BACKTEST / EVALUATION
```

Long-term ecosystem: **TRADING AI + COMMUNITY AI + SOCIAL AI + (future) TELEGRAM LAUNCHPAD.**

---

## 22. Competitive landscape (researched)

| Product | Chains | Fee | Telegram | AI | Smart Money | Copy | Launchpad |
|---|---|---|---|---|---|---|---|
| Banana Gun | ETH/SOL/Base/BNB/MegaETH | 0.5–1% | ✅ + web | limited | partial | ✅ | ❌ |
| Trojan | Solana | ~0.9% | ✅ | limited | partial | ✅ | ❌ |
| Maestro | 14+ | 1% + subs | ✅ | ❌ | partial | ✅ | ❌ |
| BONKbot / GMGN / Sigma / BullX | SOL-centric | ~1% | ✅ | some | some | ✅ | some |
| Cielo | multi | analytics subs | ❌ | ❌ | ✅ | alerts | ❌ |
| Arc-native traders/screeners | Arc | n/a | some | ❌ | limited | ❌ | some |

**Gaps to target (Arc):** quantified **consensus** (z-score) · evidence-based **Why/Exit** · integrated
**risk/manipulation** engine · **AI-first Telegram** with strict security · **Arc-native data moat**.

---

## 23. Infrastructure costs (estimates)

| Item | Start | Notes |
|---|---|---|
| VPS | $0–20/mo | reuse existing |
| Postgres | $0 self-host → $15–25/mo managed | start self-host |
| Redis | $0 (VPS) | optional |
| RPC/WS | Free tier → $0–50/mo | premium when scaling |
| LLM API | $10–50/mo | cache + routing |
| Telegram | $0 | Bot API |
| Domain/TLS | ~$10/yr | reuse + Caddy |
| **MVP total** | **≈ $0–90/mo** | grows with usage |

---

## 24. Risks

Data gaps/provider dependence · quant false positives + biases · key management + malicious contracts + LLM
misuse · execution/slippage · regulatory/reputational (never call a token a scam without evidence) · strong
incumbents · solo-builder resources.

---

## 25. Open questions (owner)

1. Custody: confirm **non-custodial only** for MVP (embedded wallet = later, opt-in)? *(recommended yes)*
2. LLM provider(s) + budget?
3. OK to index aggressively from day 1 (storage/backfill cost)?
4. Alert delivery channel: same Telegram bot as `arc-alerts` or a dedicated bot/chat?
5. Which single venue first (Uniswap v3 vs v4) — pending liquidity test?
6. Branding/compliance copy — needed before first public posts?
7. When do you want the **readiness gates** (§16.2) reviewed?

---

### IMPLEMENTATION ROADMAP (Revision 02 — paper-first)

Each milestone: **objective · files · dependencies · tests · security · result · safe-to-proceed**.

#### M0.1 — `arcai/` workspace skeleton
- **Objective:** additive workspace, no prod impact. **Files:** root `package.json` (workspaces), `arcai/{package.json,tsconfig.json,src/}`.
- **Deps:** none. **Tests:** `tsc --noEmit` in CI. **Security:** none.
- **Result:** empty typechecked module. **Safe:** ✅.

#### M0.2 — Data Engine v0 (indexer → Postgres)
- **Objective:** ingest blocks/txs/logs (swaps/launches/transfers) with chunked backfill + WS live. **Files:** `arcai/data/*`, migrations.
- **Deps:** M0.1, RPC/WS, Postgres. **Tests:** decoders, small-range integration, idempotency/reorg.
- **Security:** read-only; new DB. **Result:** queryable Arc dataset. **Safe:** ✅.

#### M0.3 — Feature Store v0 (versioned)
- **Objective:** as-of feature computation + storage + versioning. **Files:** `arcai/features/*`.
- **Deps:** M0.2. **Tests:** as-of correctness, version pinning, reproducibility. **Security:** read-only.
- **Result:** versioned features. **Safe:** ✅.

#### M0.4 — Event Replay v0 (historical state)
- **Objective:** reconstruct market state as-of a timestamp. **Files:** `arcai/replay/*`.
- **Deps:** M0.2/M0.3. **Tests:** deterministic replay; no look-ahead. **Result:** replayable history. **Safe:** ✅.

#### M1.1 — Telegram bot skeleton + auth + health
- **Objective:** bot `/start`, user record, alerts channel, health. **Files:** `arcai/bot/*`.
- **Deps:** M0.1. **Tests:** handlers, env validation. **Security:** token in env, rate limit, no secret logging.
- **Result:** bot shell. **Safe:** ✅.

#### M1.2 — AI provider abstraction + Tool Layer
- **Objective:** `AIProvider` interface + impl A; typed tools (§9). **Files:** `arcai/ai/*`.
- **Deps:** M1.1, M1.3(read tools need data). **Tests:** schema validation, authz, rate limits, refusal paths.
- **Security:** no keys, no raw DB. **Result:** AI over controlled tools. **Safe:** ✅.

#### M1.3 — Intelligence views (token/wallet) + Risk v0
- **Objective:** `/token`, `/wallet`, risk indicators. **Files:** `arcai/quant/*`, `arcai/risk/*`.
- **Deps:** M0.3. **Tests:** fixture vs on-chain; bias checks. **Security:** read-only. **Result:** useful analysis. **Safe:** ✅.

#### M1.4 — Smart Money Score + Consensus v0 (+ methodology doc)
- **Objective:** scoring + consensus (candidate models) documented first. **Files:** `arcai/quant/smartmoney/*`, `docs/SMART_MONEY_METHODOLOGY.md`.
- **Deps:** M0.3. **Tests:** metric units, OOS windows, sample-size guards. **Result:** defensible signals. **Safe:** ✅.

#### M1.5 — Alerts + Watchlists
- **Objective:** `/watch`, consensus/exit alerts, dedupe/cooldown. **Files:** `arcai/alerts/*`.
- **Deps:** M1.4. **Tests:** rules, dedupe, delivery. **Security:** none. **Result:** core loop. **Safe:** ✅.

#### M2.1 — Backtest & Evaluation Engine
- **Objective:** evaluate all signals with as-of data; metrics + bias protections. **Files:** `arcai/backtest/*`.
- **Deps:** M0.4, M1.4. **Tests:** leakage/survivorship tests; metric correctness. **Result:** validated measurement. **Safe:** ✅.

#### M2.2 — Paper trading
- **Objective:** simulated entry/exit, PnL, fees, slippage; portfolio. **Files:** `arcai/paper/*`.
- **Deps:** M2.1. **Tests:** accounting invariants, deterministic replay. **Result:** strategy eval without risk. **Safe:** ✅.

#### M3.1 — Execution engine + Venue Adapter(s) — **REQUIRES OWNER APPROVAL + GATES (§16.2)**
- **Objective:** quote→simulate→**user sign**→execute on **one** venue, with limits + emergency stop.
- **Files:** `arcai/exec/*` (reuse `sdk/` + `OrderExecutor` pattern). **Deps:** M2.2, RPC premium.
- **Tests:** fork/local sim, limit enforcement, failure/retry, nonce. **Security:** non-custodial intents, 2FA, kill-switch, Safe-owned contracts.
- **Result:** capped live execution. **Safe:** ⛔ **only after gates + explicit approval**.

#### M4+ — Risk full · Exit intelligence · Pattern recognition · Strategies · Community/Social AI · Telegram Launchpad
Sequenced with their own designs, datasets and validation.

---

### WHAT SHOULD **NOT** BE BUILT YET
- Live trading / autonomous strategies (before §16.2 gates).
- Multi-chain support.
- Embedded (managed-key) wallets.
- Community/Social auto-publishing (YELLOW/RED).
- Telegram launchpad.
- Any LLM access to keys, raw SQL, or execution.

---

## Appendix — Verified Arc facts (2026-09-24)

chainId **5042** · RPC `https://rpc.mainnet.arc.io` · WS via Alchemy/Blockdaemon/QuickNode · testnet **5042002**
(`wss://rpc.testnet.arc.io`) · gas **USDC** (18-dec native / 6-dec ERC-20, same balance) · EIP-1559+EWMA,
min 20 gwei, ~$0.001/tx, ~0.5s blocks · explorer `explorer.arc.io` · `viem` ships `arc`/`arcTestnet` ·
Uniswap v3+v4 (Universal Router `0x4fcA…9Fb1`, SwapRouter02 `0x53BF…6F77`) · Morpho Blue `0x34CD…7fCD` + Aave ·
~$397M TVL · ~$66.8M/day DEX volume.

> **No code changed. Awaiting owner approval before implementation.**
