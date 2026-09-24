# ARC AI — M0.2 DATA ENGINE v0 — Architecture

> **Status: architecture/design only. NO code, no database, no migrations, no RPC/WS calls,
> no indexer, no dependencies added, no infrastructure provisioned.** Prepared for the owner's
> review. Implementation begins only after explicit approval.
>
> Companions: `docs/ARC_AI_MASTER_ARCHITECTURE.md` (Revision 02, authoritative),
> `docs/DEPLOYMENTS.md`, `docs/VENUE_INTEGRATION.md`.

---

## 0. Purpose

M0.2 defines the reliable Arc data foundation for everything downstream:

```
DATA -> FEATURE STORE -> QUANT ENGINE -> SMART MONEY -> CONSENSUS
     -> PATTERN -> PAPER TRADING -> BACKTEST -> EVENT REPLAY -> AI
```

Optimization order: **correctness -> reproducibility -> provenance -> historical integrity ->
recovery -> observability**. Performance must be sufficient, not maximal (§26).

Non-goals: trading, execution, scoring, Smart Money, AI, Telegram, backtesting.

---

## 1. Verified Arc facts that constrain the design

| Fact | Value | Implication |
|---|---|---|
| Mainnet chain id | `5042` | Identity/partition key prefix |
| Testnet chain id | `5042002` | Dev/test environment |
| Block time | ~0.5 s | ~172,800 blocks/day; storage/checkpoint design must scale |
| Gas token | USDC (native 18-dec / ERC-20 6-dec) | Two decimal systems must never be mixed |
| Min base fee | 20 gwei | Execution-relevant only |
| RPC | `https://rpc.mainnet.arc.io` | Canonical provider-independent HTTP endpoint |
| WS | mainnet: provider-specific only; testnet: `wss://rpc.testnet.arc.io` | Mainnet live WS needs a provider key |
| Explorer | `explorer.arc.io` / `explorer.testnet.arc.io` | Cross-check/audit source |
| `eth_getLogs` | range caps observed (operators chunk ~2,000) | Backfill must be chunked + adaptive |
| Consensus | Malachite BFT, permissioned Proof-of-Authority validators | Commit requires >2/3 pre-commit votes |
| Finality | **Deterministic, final on commit, <1 s, "no reorganization risk"** | A fixed confirmation depth is not a finality mechanism (§9) |
| Block timestamps | Non-decreasing, 1-second granularity; sub-second blocks may share a timestamp | Order by `block_number`, never by timestamp |
| Native USDC moves | EIP-7708 emits ERC-20 `Transfer` logs for native sends from a system emitter | Broad USDC transfer coverage has an on-chain hook; avoid double-counting two emitters (§29) |
| Data indexers | Alchemy, Envio, Goldsky, Pinax (RPC/Firehose/Substreams), The Graph, Thirdweb, Zerion | Optional accelerators, never authoritative (§5) |

> Verified in the M0.1 audit and this revision against `docs.arc.io` (System overview,
> Deterministic finality, EVM differences, Data indexers, Gas and fees), the official Uniswap
> deployment feed, and the official Morpho deployment page.
>
> **Front-running caveat:** Alchemy's ARC data API advertises "pending transactions", but Arc's
> official docs state there is no public mempool and the system is final on commit. Any
> pending-tx surface must be treated as unverified until confirmed. M0.2 indexes **committed
> blocks only**.

---

## 2. Existing repository infrastructure (inspect before building)

`existing component -> location -> reusable? -> how`.

| Component | Location | Reuse? | How |
|---|---|---|---|
| Arc chain constants + RPC + chain ids | `sdk/src/index.ts` (`RPC`, `ARC_MAINNET_CHAIN_ID`, `ARC_TESTNET_CHAIN_ID`) | Yes | Single source of network truth |
| viem public/wallet client + `defineChain` | `keeper/src/worker.ts`, `keeper/src/server.ts` | Yes | Base HTTP client; add WS behind the source abstraction |
| Poll loop + block checkpoint | `ops/launchpad-alerts.mjs` (`state.lastBlock`, `saveState/loadState`) | Yes (pattern) | Move checkpoints from JSON file to Postgres |
| `getLogs` + ABI event decoding | `ops/launchpad-alerts.mjs`, `ops/keeper-metrics-bot.mjs`, `keeper/src/worker.ts` | Yes | Seed for the decoder registry |
| Incremental log crawl (`fromBlock=last+1..latest`) | `ops/launchpad-alerts.mjs`, `bots/*.py` | Yes | Live tail pattern |
| Chunked historical scan (`LOOKBACK_BLOCKS`) | `bots/mev_morpho_liquidator.py` et al. | Yes (pattern) | Replace fixed 2,000 with adaptive chunking |
| Idempotent DDL + typed rows + upsert | `keeper/src/db.ts` (`node:sqlite`) | Yes (pattern) | Keep keeper SQLite unchanged; Data Engine uses Postgres |
| In-process event bus + WS broadcast | `keeper/src/events.ts`, `keeper/src/server.ts` (`/ws`) | Optional | Stream live tail to consumers |
| Dependency-free env loading | `keeper/src/env.ts`, bots `load_env()` | Yes | Reuse; secrets stay out of git |
| Telegram alerting | `ops/launchpad-alerts.mjs`, bots `notify()` | Yes | Critical Data Engine alerts (§21) |
| Retry/error containment/gas-floor | `keeper/src/worker.ts` (`gas()`), bots `try/except` | Yes (pattern) | Generalize into retry/backoff middleware |
| PM2 process supervision | `ops/*.ecosystem.config.cjs`, VPS PM2, `keeper/arc-keeper.service` | Yes | Add a Data Engine process |
| Token/contract constants + deploy receipts | `sdk/src/index.ts`, `apps/launchpad/src/contracts.ts`, `contracts/broadcast/**` | Partial | Seed only; Data Engine must discover tokens |
| M0.1 domain types + interfaces | `arcai/src/types/*`, `arcai/src/interfaces/*` | Yes | `BlockRef`, `SwapEvent`, `TransferEvent`, `TokenLaunchEvent`, `DataProvider`, `FeatureStore`, `Clock` |
| Docker (BasePump) | separate repo | No | Out of scope |

**Gap analysis (to build in M0.2):** Postgres, a dedicated ingestion worker, reorg handling, a
decoder registry, a backfill orchestrator, data-quality checks, and data-engine metrics.
Redis is not used anywhere today and is not assumed.

> Deliberate: **keeper stays on `node:sqlite`.** The Data Engine is a separate process with its
> own Postgres; do not merge them (different lifecycles and risk).

---

## 3. Canonical data model

Priority: **M** = MUST (M0.2A), **S** = SHOULD (M0.2B/C), **L** = LATER (M0.2D+).

### BLOCK
| Field | P | Notes |
|---|---|---|
| `chain_id` | M | Identity prefix |
| `block_number` | M | |
| `block_hash` | M | Physical identity |
| `parent_hash` | M | Continuity check |
| `timestamp` | M | EVENT TIME |
| `first_seen_at` | M | OBSERVATION TIME |
| `decoded_at` | M | PROCESSING TIME |
| `source_id` | M | Provenance |
| `status` | M | observed/confirmed/finalized/orphaned |
| `tx_count`, `log_count` | S | Rollups |
| `base_fee_per_gas`, `gas_used` | L | Fee analytics |

### TRANSACTION
| Field | P | Notes |
|---|---|---|
| `chain_id`, `tx_hash` | M | Identity |
| `block_number`, `block_hash` | M | |
| `transaction_index` | M | |
| `from_address` | M | Funding graph |
| `to_address` | M | null for creation |
| `value` | M | Native USDC (18-dec), bigint/string |
| `status` | S | 1/0 (receipt) |
| `gas_used`, `effective_gas_price` | S | |
| `nonce`, `input`, `input_selector` | S | Decoding context |
| `contract_created` | L | If creation |
| `first_seen_at`, `decoded_at` | M | Time model |

### LOG / EVENT (raw)
| Field | P | Notes |
|---|---|---|
| `chain_id`, `block_hash`, `log_index` | M | Physical identity |
| `block_number`, `transaction_hash`, `transaction_index` | M | |
| `address` | M | Emitter |
| `topics` | M | JSON array |
| `data` | M | Hex, immutable |
| `removed` | M | Provider reorg hint |
| `decoded_event_type` | S | Versioned |
| `canonical` | M | Flips on reorg |
| `first_seen_at`, `decoded_at` | M | Time model |
| `source_id` | M | Provenance |

### TOKEN
| Field | P | Notes |
|---|---|---|
| `chain_id`, `address` | M | Identity |
| `symbol`, `name` | S | From contract calls |
| `decimals` | S | Sanity-checked 0-36 |
| `deployer` | S | Creation tx |
| `creation_block`, `creation_timestamp` | S | |
| `first_seen_at` | M | Observation time |
| `discovery_source` | S | transfer/factory/registry |

### TRANSFER (normalized)
| Field | P | Notes |
|---|---|---|
| `chain_id`, `block_hash`, `tx_hash`, `log_index` | M | From log |
| `token_address` | M | FK TOKEN |
| `from_address`, `to_address` | M | Wallet graph |
| `amount` | M | Base units; non-negative |
| `block_number`, `block_timestamp` | M | Event time |
| `canonical` | M | |

### SWAP (normalized)
| Field | P | Notes |
|---|---|---|
| `chain_id`, `block_hash`, `tx_hash`, `log_index` | M | Identity |
| `pool_address` | M | FK POOL |
| `token_in`, `token_out` | M | |
| `amount_in`, `amount_out` | M | > 0, tokens differ |
| `sender`, `recipient` | S | Where decodable |
| `price_token1_per_token0` | S | Derived, raw |
| `venue` | M | uniswap-v3 / uniswap-v4 / launchpad-dex |
| `fee_tier` | S | v3 |
| `canonical` | M | |

### POOL
| Field | P | Notes |
|---|---|---|
| `chain_id`, `address` | M | Identity |
| `venue` | M | |
| `token0`, `token1` | S | Contract calls |
| `fee_tier` | S | v3 |
| `creation_block`, `creation_timestamp` | S | PoolCreated/Initialize |
| `tick`, `sqrt_price_x96`, `liquidity` | L | Live state |
| `first_seen_at`, `canonical` | M | |

> **Do not over-model.** M0.2A stores BLOCK + TRANSACTION + LOG + one decoder
> (`erc20_transfer@1`). TOKEN/TRANSFER/SWAP/POOL arrive in M0.2B-D. LATER fields are documented
> to prevent schema regret, not to be built now.

---

## 4. Raw vs normalized data

Two layers, always.

- **RAW** — blocks/transactions/logs exactly as received (hex, topics, provider payload) plus
  provenance and observation time. **Immutable.** Never edited or deleted; only `canonical`
  flags change.
- **NORMALIZED** — canonical internal shapes (TRANSFER, SWAP, TOKEN, POOL) produced by
  versioned decoders from raw data.

Why both:
- **Reprocessing:** if decoding/normalization changes, normalized rows are rebuilt from raw
  without re-fetching the chain.
- **Provenance/audit:** every normalized row traces to a raw log + decoder version.
- **Debugging:** discrepancies are investigated at the raw layer.
- **Schema evolution:** raw schema is stable; normalized schema evolves behind versions.

Rule: **normalized is a pure function of (raw, decoder_version, normalization_version).** Any
normalized row not reproducible from raw is a bug.

---

## 5. Source strategy

| Dimension | A. Direct Arc RPC (HTTP) | B. WebSocket provider | C. Third-party indexer | D. Hybrid (recommended) |
|---|---|---|---|---|
| Coverage | Full blocks/txs/logs | Same, push | Curated/decoded | RPC baseline + optional WS |
| Latency | Poll-bound (~1-2 s) | ~block time | Minutes | Near-real-time |
| Reliability | High (canonical) | Provider-dependent | Provider-dependent | High (RPC fallback) |
| Backfill | Good (chunked getLogs) | Poor | Usually good | RPC for backfill, WS tail |
| Rate limits | Public limits | Plan-dependent | Plan-dependent | Manageable |
| Cost | $0 | Free -> paid | $ + lock-in | $0 -> low |
| Lock-in | None | Medium | High | Low |
| Failure mode | Missed block -> poll gap | Dropped socket -> silent gap | Outage -> gap | RPC preserves correctness |
| Data ownership | Ours | Ours | Theirs | Ours |
| ToS/privacy | Public chain data | Provider ToS | Provider ToS | Fine |

**Recommendation (D, Hybrid):**
1. **HTTP RPC polling is the correctness baseline** — canonical, dependency-free, already
   proven in this repo, sufficient for backfill.
2. **WS is an optional latency optimization** for the live tail; when it drops, the poller
   catches up from the last checkpoint. WS is **never** the only source of truth.
3. **Third-party indexers are optional accelerators**, never authoritative; cross-checked
   against raw logs.

No provider is chosen silently; selection is explicit and stored per source record.

---

## 6. Provider abstraction

Conceptual interfaces (to live in `arcai/`, after approval — **not now**). They mirror the M0.1
`DataProvider` shape:

```
BlockSource       latestBlock(chainId) | getBlock(chainId, number) | streamBlocks()?
LogSource         getLogs(query) | streamLogs(filter)?
HistoricalSource  getLogsRange(filter, from, to, limit)   // chunking-aware
TransactionSource getTransaction / getReceipt
```

Rules:
- Each source has `kind`, `priority`, `capabilities`, `health()`.
- The engine selects a primary + ordered fallbacks; failures degrade gracefully.
- Normalized records always store `source_id`, so provenance survives fallback.
- No business logic inside a source; sources only fetch/stream.

Convention: extend the M0.1 `DataProvider` interface in `arcai/src/interfaces` rather than
inventing a parallel hierarchy.

---

## 7. Ingestion architecture

```
BLOCKCHAIN
  -> SOURCE (RPC poller / WS stream)      fetch only
     -> RAW INGESTION                     persist raw block/tx/log + provenance + observed_at
        -> VALIDATION                     shape, parent-hash continuity, ranges, non-null
           -> CANONICALIZATION            observed -> confirmed -> finalized; detect/apply reorg
              -> DECODING                 versioned: raw log -> normalized event
                 -> NORMALIZED EVENTS     persist with decoder/normalization version + canonical
                    -> DATABASE           Postgres (source of truth)
```

Responsibilities:
- **Source:** transport, pagination, provider limits.
- **Raw ingestion:** idempotent upsert; checkpoint advance only after commit.
- **Validation:** cheap invariants; quarantine failures into `data_quality_issues`.
- **Canonicalization:** finality/reorg state machine (§8-9).
- **Decoding:** pure functions keyed by `(event, version)`.
- **Database:** constraints enforce identity/uniqueness.

Reliability primitives:
- **Retry** with **exponential backoff + jitter** on transient errors (timeout, 429, 5xx).
- **Idempotency:** all writes use `INSERT ... ON CONFLICT` on natural keys (§10).
- **Duplicate detection:** unique keys + `removed`/reorg handling.
- **Checkpointing:** per (chain, source, stream) cursor advanced only after raw commit, so a
  crash re-fetches rather than skips.
- **Failure recovery:** at-least-once ingestion + idempotent writes = effectively once.
- **Dead-letter:** records failing validation are stored, not dropped, and alerted (§22).

---

## 8. Reorganizations (defensive only)

Arc states that committed blocks are final and irreversible, with **no reorganization risk**
(§9). M0.2 therefore treats reorg handling strictly as **defensive**: its only purpose is to
guarantee that an unexpected conflicting provider observation can never silently overwrite
canonical history. It is not an expected operational path; if it ever triggers it is a
**critical alert**, and its existence must never be read as evidence that Arc normally
reorganizes.

Per-block state machine (authoritative definitions in §9.C):
- `observed` — block + receipts/logs persisted; **not** yet part of canonical reads.
- `confirmed` — the block is on the canonical chain; readable by consumers.
- `finalized` — Arc consensus finality (or an enabled, verified finality signal). For Arc, a
  committed/confirmed block is already final; the states stay distinct (§9).
- `orphaned` — a competing block replaced this height; raw kept, `canonical=false`.

We do **not** reduce the policy to "wait N confirmations"; we keep explicit canonical state. The
`OPERATIONAL_CONFIRMATION_DEPTH` buffer (§9.B) is an ingestion concern, **not** a finality
mechanism.

Detection:
1. On ingesting block `B`, compare its `parent_hash` to the stored hash of `B-1`.
2. On mismatch, **walk back** to the common ancestor `A`.
3. Mark blocks `A+1 .. B-1` as `orphaned`; set `canonical=false` on their transactions, logs,
   and all normalized rows derived from them.
4. Invalidate downstream state for those heights. Raw rows are **kept** (marked non-canonical)
   for audit.

Handling:
- Orphaned transactions/logs are not deleted; `canonical=false` excludes them from reads. If a
  tx hash reappears canonically, conflicts resolve via `(chain_id, block_hash, log_index)`.
- Normalized invalidation is a bulk `UPDATE ... SET canonical=false WHERE block_number > A`.
- Downstream consumers read canonical rows only; the as-of model (§12) makes rollback safe
  because nothing is overwritten in place.

Configurability: `OPERATIONAL_CONFIRMATION_DEPTH` (default **0**; see §9.B),
`REORG_MAX_DEPTH` (stop and alert beyond it), `FINALITY_SOURCE` (`none` | provider |
contract-based; default `none`).

Why not just N confirmations: a count without canonical tracking still leaves wrong rows if a
provider ever returns a competing block. Explicit orphan flags are the mechanism; the operational
buffer is at most an ingestion safeguard.

### Reorg walkthrough (defensive example)

Arc states there is no reorganization risk, so this path is expected **never** to trigger.
M0.2 still implements it defensively (provider/indexer inconsistency, bugs, future upgrades),
and any triggering is treated as a **critical alert**.

Canonical chain, then block `102'` replaces block `102`:

```
Canonical initially:   100  <- 101  <- 102
After replacement:     100  <- 101  <- 102'      (102 orphaned)
```

Step by step:

1. **Detect.** Ingesting `102'` at height 102, compare `parent_hash(102')` to `block_hash(101)`.
   It matches `101`, but a canonical block already exists at height 102 (`102`). Because Arc is
   final-on-commit, this is an inconsistency, not a normal reorg: emit a critical alert
   immediately.
2. **Locate common ancestor.** Walk back (`102 -> 101`) until hashes agree; ancestor `A = 101`.
3. **Mark raw rows non-canonical.**
   - `blocks`: `102` gets `status='orphaned'`, `canonical=false`. Row `102` is **kept**.
   - `transactions`: rows in `102` get `canonical=false` (kept).
   - `logs`: rows with `block_hash = hash(102)` get `canonical=false` (kept).
4. **Invalidate derived (normalized) rows.**
   - `transfers`/`swaps` derived from logs in `102` get `canonical=false` (kept, not deleted).
   - Sets `superseded_at` / `superseded_by` so as-of reads exclude them from canonical state.
   - Token/pool counters or rollups keyed to height 102 are recomputed if they are materialized;
     otherwise they are derived on read from canonical rows.
5. **Insert the new canonical records.**
   - `blocks`: insert `102'` (`canonical=true`, `status='confirmed'`).
   - `transactions`/`logs`: insert `102'` rows with `ON CONFLICT (chain_id, tx_hash)` /
     `(chain_id, block_hash, log_index)`; genuinely new txs are inserted, re-included txs update
     their `block_hash`/`block_number`.
   - `transfers`/`swaps`: decode logs of `102'` into new canonical normalized rows.
6. **What remains.** Both `102` and `102'` exist in raw; only `102'` is canonical. Old raw and
   normalized rows are available for audit/reprocessing. Nothing is deleted.
7. **How downstream consumers know data changed.** A `canonical_epoch` (or max
   `canonicalized_at`) per chain is bumped on any invalidation; consumers cache by that epoch.
   Normalized reads always filter `canonical = true`. The `data_quality_issues` entry plus the
   critical alert records the event for operators.

Reduced formula: `chain_id = C AND block_height > A` -> `canonical := false` for raw and
normalized; then ingest the new branch as fresh canonical rows. This is safe because reads are
always canonical-filtered and all state is reconstructable from raw.

---

## 9. Finality model

### What Arc officially provides

From the official Arc documentation (System overview; Deterministic finality; EVM differences):

- Consensus is **Malachite**, a Tendermint-style **BFT** protocol over a **permissioned
  Proof-of-Authority** validator set.
- A block is committed after **more than two-thirds** of validators pre-commit. **Once
  committed, the block is final and irreversible.**
- Finality is **deterministic and sub-second** (benchmarked <350 ms; docs state <1 s), with
  **"no confirmation windows, no reorganization risk, no probabilistic uncertainty."**
- Arc docs explicitly advise offchain systems to act **after a single confirmation**.
- **Block timestamps are non-decreasing but not strictly increasing** (1-second granularity, so
  sub-second blocks may share a timestamp). Ordered state must use `block_number`.
- The builder does **not** document whether the JSON-RPC/Explorer exposes explicit
  `finalized`/`safe` block tags, nor a finality flag on receipts. This is **unverified**.

These are **three different concepts** and must never be conflated.

### A. Consensus finality (what Arc itself guarantees)

- Arc's Malachite BFT consensus commits a block once **more than two-thirds** of validators
  pre-commit. **Once committed, the block is deterministically final and irreversible.**
- **Additional confirmations are NOT required to establish consensus finality.** There is no
  probabilistic window to wait out, and no reorg risk by protocol.
- `FINALITY_SOURCE` records whether we additionally observe an explicit provider/contract
  finality signal. Default `none` (Arc's RPC/Explorer exposure of `finalized`/`safe` tags is
  unverified). Enabling a verified signal does not change the fact that commit is final.

### B. Operational observation buffer (NOT finality)

- Configurable `OPERATIONAL_CONFIRMATION_DEPTH`, default **0**.
- **Why 0:** because consensus finality is deterministic and instant, there is no protocol reason
  to delay a committed block from becoming `confirmed`. Defaulting to 0 means "as soon as we
  observe a committed block, it is canonical."
- A value **> 0** is only justified by *documented operational evidence* — e.g. a specific
  provider or indexer that intermittently serves a tail block it later replaces — and is then
  recorded as an **ingestion buffer**, never as a finality guarantee. There is no such evidence
  today, hence 0.
- The buffer may postpone marking `observed -> confirmed`; it may **never** be described as, or
  depended upon for, finality.

### C. Canonical status (exact definitions)

| Status | Exact meaning | `canonical` | Readable by consumers? |
|---|---|---|---|
| `observed` | Fetched and persisted with provenance; not yet determined canonical | `false` | Raw/audit/quality only |
| `confirmed` | Established to be on the canonical chain | `true` | Yes |
| `finalized` | Arc consensus finality attained (or a verified finality signal observed). On Arc, every `confirmed` block is already `finalized`; the status remains distinct so a future chain with probabilistic finality still works | `true` | Yes |
| `orphaned` | Replaced at its height by a competing block; raw evidence kept for audit | `false` | Raw/audit/quality only |

- **"confirmed" is not a synonym for "finalized."** `confirmed` means "we established canonical
  membership"; `finalized` means "consensus-final." On Arc these coincide in practice, but they
  are separate fields so the model never assumes instant finality on another chain.
- A record is readable by feature/backtest/trading consumers **iff** `canonical = true`.

### Raw-data readability (resolves the earlier contradiction)

Policy: **raw/audit and quality consumers read ALL statuses; derived/analysis consumers read only
`canonical = true`.** Decoding may run against raw `observed` rows, but its output is not
canonical until the block is confirmed.

| Consumer | Observed | Confirmed | Finalized | Orphaned |
|---|---|---|---|---|
| Raw audit | YES | YES | YES | **YES** (kept, never deleted) |
| Data quality | YES | YES | YES | YES |
| Decoder | YES (produces non-canonical output) | YES | YES | YES (only to reprocess/audit; output never canonical) |
| Feature Engine | NO | YES | YES | NO |
| Backtest | NO | YES | YES | NO |
| Trading / Execution | NO | YES | YES | NO |

**Raw observed data — even when it later becomes orphaned — remains auditable.** Raw evidence is
never deleted because it becomes non-canonical; invalidation only flips `canonical`/`status`.

---

## 10. Idempotency

Stable natural identities:

| Entity | Identity (unique) |
|---|---|
| Block | `(chain_id, block_hash)`; partial unique `(chain_id, block_number) WHERE canonical` |
| Transaction | `(chain_id, tx_hash)` |
| Log | `(chain_id, block_hash, log_index)` |
| Transfer | `(chain_id, tx_hash, log_index)` |
| Swap | `(chain_id, tx_hash, log_index)` |
| Token | `(chain_id, address)` |
| Pool | `(chain_id, address)` |

Consequences:
- Every write is `ON CONFLICT DO NOTHING` (raw) or `ON CONFLICT DO UPDATE` (state transitions
  like `canonical`/`status`), so re-runs never duplicate.
- `block_number` alone is not unique across a reorg; hence the physical key uses `block_hash`
  and canonicality is a separate partial unique index.
- Logs/transfers/swaps keyed by `(tx_hash, log_index)` are stable within a canonical chain and
  re-derivable if a tx re-lands in a different block (new `block_hash`).

---

## 11. Time model (explicit invariant)

**INVARIANT: the four timestamps below MUST NOT be collapsed into one column, and no stage may
substitute one for another.** `first_seen_at` (observation) must never replace `event_time`.

| Time | Meaning | Source | Column |
|---|---|---|---|
| **EVENT TIME** | when it happened on-chain | block `timestamp` | `event_time` |
| **OBSERVATION TIME** | when Arc AI first observed the data | our clock at first fetch | `first_seen_at` |
| **PROCESSING TIME** | when Arc AI decoded/normalized it | our clock at decode | `decoded_at` |
| **CANONICALIZATION TIME** | when Arc AI determined the record belonged to the canonical chain | our clock at confirmation/invalidation | `canonicalized_at` |

`event_time` and `first_seen_at` are both mandatory on every raw and normalized record.
`decoded_at` is mandatory on normalized records. `canonicalized_at` is set when a record enters
the canonical set and updated (with `superseded_at`) if it is later invalidated.

### Which timestamp future systems must use

| Downstream system | Primary time | Why |
|---|---|---|
| Historical market reconstruction | `event_time` (+ `block_number` for ordering) | Reconstructs what the market *was*, independent of our ingestion |
| Smart Money detection | `event_time` for behavior; `first_seen_at`/`canonicalized_at` for availability | Behavior is on-chain; availability governs decidability |
| Signal generation (historical) | `canonicalized_at <= T` and `event_time <= t` | Conservatively only use data we had actually canonicalized by T |
| Backtesting | `canonicalized_at`/`first_seen_at` gate + `event_time` ordering | Prevents look-ahead (see §28) |
| Event Replay | cutoff on availability time, order by `event_time`/`block_number` | "What did we know at T?" |

Backfilling old blocks yields **old** `event_time` but **current** `first_seen_at`/
`canonicalized_at`. This asymmetry is intentional and is exactly what makes look-ahead
detectable and preventable.

---

## 12. As-of data

The layer must answer:
- "What did the system know at block X?"
- "What did the system know at timestamp T?"

Mechanism:
- Rows are **append-only and versioned**, never destructively overwritten.
- An as-of read filters: `event_time <= X` **and** `first_seen_at <= T` **and** `canonical`.
- Re-normalizations write a **new generation** (`normalization_version`) and mark prior rows
  `superseded_by` rather than deleting them.
- Feature/computation code receives a **cutoff** and must not read rows observed after it
  (leakage guard), enforceable in the repository layer by requiring a cutoff argument.

This prevents future information leaking into historical analysis and is the substrate for
Event Replay (§16).

---

## 13. Provenance

Every important normalized record carries: `source_id`, `ingested_at` (observation),
`block_number`, `block_hash`, `tx_hash`, `log_index` (where applicable), `decoder` +
`decoder_version`, `normalization_version`, `canonical`, `superseded_by`.

A `sources` table records provider `kind`, endpoint reference (no secrets), and priority. Any
derived number is traceable end-to-end to the raw log and code version that produced it.

---

## 14. Decoder versioning

Version three independent things:
1. **ABI** (`uniswap_v3_pool@1`, `erc20@1`) — immutable, checksummed.
2. **Event decoder** (`decode_transfer@1`) — pure function: raw log -> normalized event.
3. **Normalization logic** (`normalize_swap@1`) — cross-event rules.

Rules:
- A normalized row stores `decoder` + `decoder_version` + `normalization_version`.
- Changing any of them means a **new version**; old rows are not rewritten in place.
- A reprocessing job re-decodes raw logs into a new generation, so historical results can be
  reproduced with the version that generated them.
- The `decoder_registry` table lists available versions and their status.

---

## 15. Backfill

Two paths, one decoder.

| | LIVE INGESTION | HISTORICAL BACKFILL |
|---|---|---|
| Trigger | new head | operator/scheduled |
| Orchestration | continuous loop | bounded job with progress |
| Checkpoint | head cursor | range cursor per job |
| Rate handling | poll interval | adaptive chunk size, concurrency=1 |
| Failure | retry -> catch up | resume from range checkpoint |

Shared: the same raw-write + validation + canonicalization + decode pipeline; only the
orchestrator differs.

Backfill specifics:
- **Chunk size is configurable and adaptive**, not hardcoded. Start from a configured default
  (Arc operators chunk ~2,000, so that is a justified starting point); on range-limit/timeout,
  halve and retry; on success, grow back within bounds.
- Each job writes an `ingestion_runs` row (range, status, progress) and advances a checkpoint
  after each committed chunk.
- On restart it resumes from the last committed checkpoint; committed chunks are never
  re-fetched, and if they are, idempotency makes it harmless.
- Live ingestion pauses for a range under backfill, or backfill stays below the live checkpoint.

---

## 16. Event Replay compatibility

M0.2 must let a future replay engine reconstruct `state at block X` using **only** what was
available by X.

How the data layer enables it (without building replay now):
- Immutable raw logs + block timestamps -> deterministic input set.
- `first_seen_at`/`decoded_at` -> "known by T" filtering.
- Versioned normalization -> replay with the original code version.
- Canonical flags -> correct reorg handling at the replay boundary.
- A **replay clock** is future work; M0.2 only guarantees the data and as-of queries it needs.

---

## 17. Database architecture (PostgreSQL)

PostgreSQL is the right source of truth for M0.2: relational integrity, JSONB for raw payloads,
partial/unique indexes, `ON CONFLICT` idempotency, and analytical SQL for later features.

Expected tables:
- **Raw:** `blocks`, `transactions`, `logs`.
- **Normalized:** `tokens`, `transfers`, `swaps`, `pools`.
- **Infra:** `sources`, `checkpoints`, `ingestion_runs`, `decoder_registry`,
  `data_quality_issues`, `schema_migrations`.

Keys/indexes:
- PKs per §10; FKs from normalized -> raw where practical.
- Indexes: `logs(chain_id, address, block_number)`; `transfers(token_address, block_number)`;
  `transfers(from_address, block_number)`, `transfers(to_address, block_number)`;
  `swaps(pool_address, block_number)`; `blocks(chain_id, block_number)`.
- Partial unique `(chain_id, block_number) WHERE canonical` on `blocks`.

JSONB vs columns:
- **JSONB** for raw payloads and decoded extras (provider-specific) — flexible, auditable.
- **Normalized columns** for everything queried/indexed (addresses, amounts, block refs).
- Amounts stored as `numeric` or text-safe bigints (never float).

Partitioning / time-series:
- `blocks`/`transactions`/`logs` are append-heavy. **Start unpartitioned** (correctness first);
  plan declarative partitioning by block range later. Do not partition prematurely (§26).

### Table classification (correctness first)

| Table | Class | Notes |
|---|---|---|
| `blocks` | Append-only + mutable **state** field | Rows immutable except `status`, `canonical`, `canonicalized_at` |
| `transactions` | Append-only + mutable `canonical` | Identity `(chain_id, tx_hash)`; body immutable |
| `logs` | Append-only + mutable `canonical` | Raw hex immutable; never deleted |
| `tokens` | Mutable (slowly) | Metadata may be enriched later; row never discarded |
| `transfers` | Derived + mutable `canonical` | Pure function of raw logs + decoder version |
| `swaps` | Derived + mutable `canonical` | Pure function of raw logs + decoder version |
| `pools` | Derived + mutable | Enriched from factory/pool calls; `canonical` flag |
| `sources` | Mutable config | Provider endpoints (no secrets) and priority |
| `checkpoints` | Mutable | Cursor; advanced only after commit |
| `ingestion_runs` | Append-only + progress | Job status/progress |
| `decoder_registry` | Append-only | Version catalog |
| `data_quality_issues` | Append-only | Never deleted; supports audit |

Principles: raw is immutable; normalized is reconstructable; only `canonical`/`status`/
enrichment fields are ever updated, and updates are themselves append-audited.

Retention: see §19. No database, migrations, or tables are created now.

---

## 18. Redis

**Assessment: Redis is NOT required for M0.2.** Postgres covers the candidate needs:
- checkpoints — a `checkpoints` table;
- queues — `ingestion_runs` + `SELECT ... FOR UPDATE SKIP LOCKED`;
- temporary state — rows with `status`;
- rate limiting — in-process for a single worker.

Revisit Redis only for a concrete need: high-frequency hot cache for consumers, cross-process
rate limiting, or stream fan-out at scale. Until then it adds operational surface for no
correctness benefit. The master architecture already lists Redis as optional.

---

## 19. Data retention

| Category | Retention | Reconstructable? |
|---|---|---|
| Raw chain data (blocks/txs/logs) | **Permanent** | No — must keep |
| Normalized events (transfers/swaps) | **Permanent** | Yes, from raw + decoders |
| Market snapshots (later) | Long (backtest parity) | Partially |
| Derived features (later) | Long, versioned | Yes, from normalized |
| Signals (later) | **Permanent** (outcome history is the asset) | Yes, from inputs + versions |
| Ingestion/ops logs | Short (e.g. 30-90 days) | No |

Principle: raw and normalized are permanent; truly derivable, high-volume intermediates may be
pruned or recomputed under storage pressure.

---

## 20. Security

- **Secrets:** env on the VPS (chmod 600) or a secret manager; never in git or logs. Reuse the
  existing `.env` + PM2 pattern; add per-process credential separation.
- **RPC credentials:** provider keys isolated to the Data Engine process; endpoints referenced
  by an identifier in `sources`, never printed.
- **Database credentials:** least-privilege app role; no superuser; **no public port**
  (localhost / unix socket / private network); TLS if remote.
- **SQL injection:** parameterized queries only; no string-built SQL.
- **Network exposure:** Postgres and internal services bound to private interfaces; only the
  reverse-proxied HTTP endpoints are public.
- **Provider isolation:** one key cannot serve another component; rotate-able.
- **Audit logs:** ingestion runs, config changes, and quality events recorded and retained.
- **LLM boundary (future):** the LLM gets **no** database credentials and no raw SQL — data is
  reached only through the typed AI Tool Layer (master architecture §9), backed by the quant
  engine. M0.2 must not create any path that hands the DB to a model.

---

## 21. Observability

Metrics:
- `blocks_processed_total`, `block_lag` (head - checkpoint), `backlog_estimate`.
- `events_decoded_total`, `decode_failures_total`.
- `ingestion_latency_seconds`, `db_write_latency_seconds`.
- `provider_errors_total`, `retries_total`, `http_429_total`.
- `reorgs_total`, `reorg_depth_blocks`, `orphaned_rows_total`.
- `data_gaps_total`, `duplicate_rows_total`, `validation_failures_total`.

Critical alerts (reuse Telegram):
- No new block for > N block-times (pipeline stalled).
- Checkpoint not advancing while head advances.
- Reorg detected (alert beyond a depth threshold).
- Data gap detected (missing canonical block number).
- Decode-failure rate spike.
- Provider unreachable / sustained 429s.
- Database unreachable or writes failing.

Expose `/health` and `/metrics` mirroring existing services; run a Data-Engine PM2 process.

---

## 22. Data quality

The engine must **fail visibly, not silently**. Violations -> `data_quality_issues` + alert:
- **Missing blocks:** canonical block numbers not contiguous over an indexed range.
- **Duplicate events:** unexpected unique-key conflicts.
- **Impossible timestamps:** block timestamp below the previous block, or far in the future.
- **Invalid token decimals:** outside 0-36, or missing `decimals()`.
- **Negative/zero amounts:** transfers/swaps with invalid non-positive amounts.
- **Inconsistent swaps:** `token_in == token_out`, or both amounts zero.
- **Broken parent-hash chain:** mismatch beyond the reorg path.
- **Unexplained gaps:** head advanced but no rows for a range (source silently skipped).
- **Receipt/log mismatch:** a log references a tx absent from the same block.

Every issue row carries provenance (block/tx/log, source, decoder) so it can be replayed and
fixed rather than hidden.

---

## 23. Cost model

Assumptions are explicit; ranges only (no invented precise prices).

### DEVELOPMENT (local)
| Item | Estimate | Assumption |
|---|---|---|
| RPC | $0 | Public Arc RPC |
| WS | $0 | Not used, or testnet WS |
| PostgreSQL | $0 | Local/self-host |
| Storage | $0 | Laptop/VPS disk |
| Redis / indexer | $0 | Not used |
| **Total** | **~$0/mo** | |

### EARLY PRODUCTION (small user base)
| Item | Estimate | Assumption |
|---|---|---|
| RPC | $0-25 | Free tier -> low paid |
| WS | $0-15 | Optional free tier |
| PostgreSQL | $0-25 | Self-host on existing VPS -> small managed |
| Storage | $5-15 | Hundreds of GB range |
| Redis / indexer | $0 | Not used |
| **Total** | **~$0-65/mo** | Reuses existing VPS/PM2/Telegram |

### GROWTH (meaningful Arc activity)
| Item | Estimate | Assumption |
|---|---|---|
| RPC | $50-200 | Higher limits + archival |
| WS | $15-50 | Redundant providers |
| PostgreSQL | $25-100 | Managed + backups |
| Storage | $20-75 | TB scale |
| Redis (optional) | $0-15 | Only if needed |
| Indexer (optional) | $0-100 | Only for expensive history |
| **Total** | **~$110-540/mo** | Scales with usage |

M0.2 starts in **DEVELOPMENT/EARLY**, reusing the existing VPS and $0 endpoints.

### Cost principles

- **Cheapest architecture that preserves correctness wins.** Correctness is not a place to
  economize; everything else is.
- **No Redis** is assumed (Postgres-only, §18). **No managed infrastructure** is required to
  start: self-host Postgres on the existing VPS.
- Cost is split by category so each can be tuned independently:
  `infra (VPS)` | `RPC provider` | `WS provider` | `database` | `storage` | `optional indexing`
  | `monitoring`.
- **Monitoring** (metrics + alerting) is expected to cost **$0**: reuse existing PM2, structured
  logs, and the existing Telegram channel; a hosted metrics backend is optional and deferred.
- Public RPC at $0 is acceptable for M0.2A; paid RPC/WS/archival arrives only when rate limits
  or history demand it.
- Backfill is **one-time** load, not a steady-state cost; keep concurrency low to stay on free
  tiers.

---

## 24. Minimum dataset for Smart Money

M0.2 must capture, for **all wallets** (not just our contracts), enough history to enable future
Smart Money analysis:
- **Wallet-level token movements:** every ERC-20 `Transfer` involving tracked tokens (in/out)
  with counterparties -> acquisition/disposal and funding graphs.
- **Native/stablecoin funding:** value transfers and USDC movements -> funding clusters.
- **Swaps:** pool, tokens, amounts, direction -> entry/exit prices and PnL.
- **Token lifecycle:** creation block/deployer -> deployer relationships, rug analysis.
- **Liquidity context:** pool creation + liquidity/price observations -> liquidity-adjusted
  returns.
- **Timing:** event time + observation time -> recency weighting, as-of features.
- **Outcomes:** stored signal->outcome links (future) -> evaluation.

**If any is missing, later Smart Money analysis becomes impossible or biased.** Most critical:
(a) broad transfer coverage (not only our contracts) and (b) observation-time provenance.
M0.2A/B must index **all ERC-20 Transfer logs** for the tracked token set and, where feasible,
a broad token-discovery pass.

M0.2 does **not** compute any Smart Money metric; it only ensures the raw material exists.

---

## 25. MVP scope (M0.2A -> M0.2D)

### M0.2A — Minimum ingestion foundation (live)

Smallest implementation that proves the pipeline is correct (nothing more):

- Postgres schema: **raw** (`blocks`, `transactions`, `logs`) + **infra** (`sources`,
  `checkpoints`, `ingestion_runs`, `data_quality_issues`, `schema_migrations`).
- One provider abstraction (HTTP RPC) + poller. WS is **not** required.
- Raw ingestion with provenance + the **four** timestamps (§11); idempotent upserts.
- Checkpoints advanced only after commit.
- Canonicalization state machine (`observed`/`confirmed`) with **defensive** conflict detection.
- Exactly **one** decoder: `erc20_transfer@1` -> `token_transfer_candidate` (provisional; full
  contract in §38). Promotion to a normalized `transfer` requires the validation in §38.
- Data-quality checks (missing blocks, duplicates, impossible timestamps, invalid amounts,
  broken parent-hash).
- Health + structured logs + basic counters. **No Telegram, no LLM, no Smart Money, no wallet
  scoring, no price prediction, no trading** (alerting channel arrives later).

**Explicitly out of M0.2A:** historical backfill (M0.2B), full reorg invalidation + alerts
(M0.2C), swaps/pools/launchpads and multi-source failover (M0.2D).

#### M0.2A acceptance criteria

M0.2A is complete only when all of the following are demonstrated (evidence recorded):

1. Arc blocks are ingested continuously and stored (raw layer).
2. Transactions and logs are stored with correct block/tx ordering keys.
3. Re-running ingestion of the same range creates **zero** duplicates (idempotency).
4. Provenance is present on every row (`source_id`, times, block/tx/log refs, decoder version).
5. Checkpoints advance correctly and resume after restart without gaps or double-rows.
6. Basic conflict handling: a competing block at a committed height is detected and flagged
   (defensive; no silent corruption).
7. `erc20_transfer@1` decodes ERC-20 `Transfer` logs into normalized rows correctly.
8. Data-quality checks detect and record each seeded fault.
9. The system recovers from an interruption and continues without manual repair.

Acceptance is measured by the recovery/reorg tests in §36, not by "it runs". The M0.2A data
boundary is fixed in §41, the binding invariants in §42, and the allowed/forbidden implementation
contract in §43.

### M0.2B — Historical backfill
- Backfill orchestrator with adaptive chunking + resumable range checkpoints.
- Reuses A's pipeline; `ingestion_runs` progress; rate-limit handling.
- Token registry population (`decimals/symbol/name`), token discovery from transfers.
- Additional decoders: `uniswap_v3_swap@1`, `uniswap_v4_swap@1`; `pools` tracking.

### M0.2C — Data quality / reorg hardening
- Full reorg walk-back, orphan invalidation of normalized rows, `REORG_MAX_DEPTH` guard.
- Complete quality checks + `data_quality_issues`; gap detection vs explorer reconciliation.
- Finality configuration (`FINALITY_SOURCE`), confirmation-depth calibration.
- Decoder registry + a **reprocessing** path (new generation from raw).

### M0.2D — Expanded coverage
- Additional venues/launchpad decoders; pool/liquidity tracking; richer token discovery.
- Multi-source failover; optional indexer cross-checks; snapshot surfaces for downstream.
- Performance/partitioning work, only when justified by real volume.

---

## 26. No premature optimization

Optimize first for correctness, reproducibility, provenance, historical integrity, recovery, and
observability. Do not partition, cache, shard, or horizontally scale until real data volume
requires it. Postgres on one VPS is sufficient for M0.2. Performance must be adequate, not
maximal.

---

## 27. Architecture document

This file (`docs/ARC_AI_DATA_ENGINE_M02.md`) is the M0.2 design. It is documentation only. No
code, schema, migration, dependency, provider connection, or infrastructure is created by M0.2
until the owner approves implementation.

---

## 28. Look-ahead bias rule (foundational)

**RULE: a historical query evaluated "at time/block T" may only use information whose
availability timestamp is `<= T`.** If availability is uncertain, the datum **must not** be used.

Definition of **available** (conservative, in priority order):

1. **Canonicalization time** (`canonicalized_at`) — the strictest. A record exists for a
   historical strategy only once we had determined it canonical. This is the default gate for
   **signal generation and backtesting** because it also accounts for our ingestion reality.
2. **Observation time** (`first_seen_at`) — used when reasoning about "what data existed to us",
   e.g. availability of off-chain context.
3. **Event time** (`event_time`) — used **only** for reconstruction/behavioral ordering, never as
   the availability gate for a historical decision.

Conservative policy by analysis type:

| Analysis | Availability gate | Ordering |
|---|---|---|
| Historical market reconstruction | `event_time <= t` (plus canonical) | `block_number`, `tx_index`, `log_index` |
| Smart Money behavior | `event_time <= t` | chain order |
| Smart Money *decidability* | `canonicalized_at <= T` | — |
| Signal generation (historical) | `canonicalized_at <= T` | chain order |
| Backtesting | `canonicalized_at <= T` (default) | chain order |

Rationale: gate on when we *could have known and committed* the fact, not merely when it
happened. This is intentionally stricter than event time and prevents subtle leakage (e.g. a
token's `decimals()` resolved later, a pool created in a later block, or a backfilled row
inserted after the fact). This rule is binding for all future Smart Money, Consensus, and
Backtest engines.

---

## 29. Broad ERC-20 transfer strategy

| | A. Index every Transfer from every contract | B. Known/relevant tokens only | C. Progressive discovery | D. Hybrid priority |
|---|---|---|---|---|
| Completeness | Maximal (incl. spam) | Low (misses unknown winners) | High (discovers then covers) | High, tiered |
| RPC/log volume | Very high | Low | Medium → high | Managed |
| Storage | Very high | Low | Medium | Medium |
| CPU/decode | Very high | Low | Medium | Medium |
| Backfill cost | Prohibitive | Cheap | Moderate | Controlled |
| Smart Money usefulness | High but noisy | Low | High | High |
| False positives | Many (non-ERC20 Transfer emitters, spam) | Few | Few after validation | Few |
| Token explosion | Severe | None | Controlled by validation | Controlled |

Arc-specific hook: native USDC movements surface as EIP-7708 `Transfer` logs from the **system
emitter** `0xffffFFFfFFffffffffffffffFfFFFfffFFFfFFfE` (18 dec), and the ERC-20 USDC contract
`0x3600000000000000000000000000000000000000` also emits `Transfer` (6 dec). A single ERC-20
`transfer()` therefore produces **two** logs. This is resolved in §39: the native system stream
is canonical for USDC and the streams are never summed. No cross-emitter dedup key is invented.

**Recommended M0.2A approach (do not implement yet):** **Strategy B+ (bounded known set)**.
Index transfers for a small, explicit seed token set, with the seed/discovery boundary specified
in §40. This proves the decoder and storage with a bounded blast radius while keeping broad
coverage possible later (§40). Full "every Transfer" (A) is explicitly **not** an M0.2A goal.

---

## 30. Token discovery and the seed/discovery boundary

Not every contract emitting `Transfer` is a legitimate ERC-20. Discovery is evidence-based, and a
token may exist in the **raw** layer before being accepted into the normalized **token registry**.
M0.2A runs on a **bounded seed set** (Strategy B+, §29) but must be built so broad coverage is
possible later without redesign.

### Seed sources

- Known Arc tokens (USDC, EURC, cirBTC; §verified Arc facts).
- Known launchpad/factory contracts (token created by a known factory).
- Known DEX/pool contracts (tokens appearing in pools we track).
- A curated token registry (explicit allowlist file/table).
- Protocol contracts we operate.
- Externally discovered addresses (later; any address surfaced by the above).

### Validation: `DISCOVERED -> VALIDATED -> REGISTERED`

| State | Evidence required |
|---|---|
| `DISCOVERED` | Address observed as an emitter of `Transfer`, or created by a known factory. Stored in **raw** only; not a coverage target |
| `VALIDATED` | Bytecode exists (not an EOA/precompile); `decimals()` returns `0..36`; `symbol()`/`name()` attempt recorded; a real `Transfer` with non-zero value observed. Non-conforming emitters are rejected |
| `REGISTERED` | Accepted into the `tokens` registry with `discovery_source` and a confidence score; only now is it a normalized-transfer coverage target |

`rejected` is a terminal state retained for audit. A contract is **never** treated as an ERC-20
merely because it emits a `Transfer` topic.

### Future expansion (explicit, not implemented now)

1. **M0.2A:** curated seed list only.
2. **M0.2B/D:** add factory/launchpad-driven discovery and progressive auto-validation.
3. **Later:** broad coverage via a documented allow/deny policy and confidence thresholds; if
   full-scan is ever needed, it is an explicit, costed decision — not a silent scope change.

Nothing in the M0.2A schema may prevent this: `tokens` must be able to grow beyond the seed set,
transfers must reference arbitrary token addresses, and no component may assume a fixed token
list.

---

## 31. Price / liquidity readiness (data only; NOT a price engine)

M0.2 stores facts; a future Price/Liquidity Engine derives measurements. M0.2 must preserve, for
reconstruction: swaps (pool, tokens, amounts, direction, block/tx/log order), pools (venue,
tokens, fee tier, creation block, and v3 tick/sqrtPrice/liquidity snapshots where we take them),
token pairs, block/timestamp, venue, and pool lifecycle events (create/initialize/updates).

Division of responsibility:

| Data Engine (M0.2) stores | Price Engine (future) derives |
|---|---|
| Raw swaps + ordering + amounts | VWAP/TWAP, candles, price series |
| Pool identity + fee tier + creation | Liquidity-adjusted prices, depth |
| Optional pool state snapshots | Slippage/impact models, routing |
| Token decimals/identity | Normalized human prices |
| Provenance + as-of metadata | Reproducible measurement with versioning |

M0.2 **does not** compute prices, candles, or liquidity scores. It only guarantees the inputs are
captured with enough ordering and provenance to be recomputed later.

---

## 32. Event ordering

Canonical order is **lexicographic**: `block_number` -> `transaction_index` -> `log_index`.
Attached to each event: `chain_id`, `block_hash`, `tx_hash`.

Why this matters:
- **Timestamps are insufficient**: Arc block timestamps are non-decreasing at 1-second
  granularity, so sub-second blocks can share a timestamp. Ordering by timestamp is wrong.
- **Wallet balances**: intra-block transfers must be applied in index order to compute balances
  correctly.
- **Swaps / Smart Money**: multiple swaps in one tx must be ordered by `log_index` to know the
  real sequence and prices.
- **Replay / historical state**: deterministic reconstruction requires a total order independent
  of wall-clock time. `(block_number, tx_index, log_index)` is that total order.

Rule: no component may order events by timestamp; always use the tuple above.

---

## 33. Snapshot strategy

Compare:

- **Event-sourced reconstruction** — state at any point is derived by replaying ordered events.
  Pros: exact, audit-friendly, reorg-safe, no snapshot drift. Cons: slower for deep histories.
- **Periodic snapshots** — materialized state at intervals. Pros: fast reads. Cons: can drift,
  must be invalidated on reorg, more write paths, schema coupling.

**Recommendation (minimum):** **event-sourced first; no snapshots in M0.2A.** Reconstruct state
by querying ordered canonical events with the §28 availability gate. This keeps M0.2 correct and
simple. Introduce **targeted, versioned snapshots only where measurement proves a query is too
slow** (likely per-wallet balances or pool state), and always store alongside them the
`block_number`, `decoder_version`, and provenance so a snapshot is reproducible and invalidatable
on a conflict. Snapshots are an optimization, never the source of truth.

## 34. Provider fallbacks (exact behavior)

Primary + ordered fallbacks, but fallback data is **never blindly trusted**.

| Situation | Detection | Action |
|---|---|---|
| Provider A **fails** (timeout, 5xx) | request error / retry budget exhausted | retry with backoff; if exhausted, switch to fallback; record `source_id`; alert if sustained |
| Provider A **temporarily behind** | `latestBlock(A) < checkpoint` or behind provider B | do **not** advance; wait/back off; use B for the missing range; never rewind a checkpoint |
| Provider A returns **incomplete** data | expected block/tx/log counts mismatch, or missing receipt | cross-check against fallback; if mismatch, quarantine range to `data_quality_issues` and re-fetch; do not commit partial |
| Provider A returns **inconsistent** data | same height, different `block_hash`/`parent_hash` | treat as conflict: do not overwrite canonical; record both; alert; follow §8 defensive path |
| Fallback returns conflicting data | hashes differ from committed head | prefer the branch consistent with stored canonical chain; quarantine + alert the discrepancy |

Rules:
- Every fetched record stores `source_id` and `first_seen_at`; provenance survives any fallback.
- Conflicting responses are **recorded** (`data_quality_issues`, and raw rows for both branches
  where practical), never silently dropped.
- A fallback may fill a gap but may not rewrite committed canonical history without the §8
  procedure.
- Cross-provider consistency checks are periodic and sampled, not per-block (cost control).

---

## 35. Data gap detection

**A silently skipped block is unacceptable.** Mechanisms:

- **Contiguity check:** for a canonical range, assert no missing `block_number` (partial unique
  index + range scan).
- **Checkpoint-vs-head drift:** if `head - checkpoint` grows beyond a threshold while the poller
  is healthy, a gap or stall exists.
- **Expected-count reconciliation:** block `tx_count`/`log_count` vs stored counts; receipt
  presence for every stored tx.
- **Log completeness:** each stored `log` references an existing tx in the same block; logs not
  silently absent for a known active contract.
- **Backfill holes:** the set of committed backfill ranges is itself checked for holes; a hole is
  a gap.
- **Decode failures:** an event that should decode but fails becomes a `data_quality_issues`
  row, not a skip.
- **Provider lag:** if `latestBlock(provider) < local head`, flag provider lag; do not treat it
  as a gap in *our* data.

Any detected gap -> record in `data_quality_issues` with the exact range, then a repair job
re-fetches that range idempotently. Gaps are visible, alertable, and repairable.

---

## 36. M0.2A failure / recovery tests (defined before implementation)

Each test specifies: **input state · failure · expected DB state · expected checkpoint · expected
alert/metric · manual intervention**. All tests run locally against fixtures/mocks (no live Arc
RPC), and each is M0.2A acceptance evidence (§25).

### Test A — Worker stops halfway through a block range
- **Input:** ingestion running over range `[N..N+k]`; a block is persisted but the next is not.
- **Failure:** process killed/aborted mid-range.
- **DB state:** only fully-committed blocks/rows exist; no partially-written block is marked
  canonical; committed rows unchanged.
- **Checkpoint:** remains at the last fully-committed block (never beyond uncommitted work).
- **Alert/metric:** none required on restart; `block_lag` grows during downtime.
- **Manual:** not allowed/needed — resume is automatic.

### Test B — Same block range processed twice
- **Input:** range already fully ingested.
- **Failure:** none (forced re-run).
- **DB state:** identical row counts; no duplicates; `ON CONFLICT` no-ops/updates only.
- **Checkpoint:** unchanged (already at range end).
- **Alert/metric:** `duplicate_rows_total` may increment; no error alert.
- **Manual:** not allowed/needed.

### Test C — Provider returns duplicate data
- **Input:** provider returns the same block/logs twice in one response.
- **Failure:** duplication.
- **DB state:** duplicates collapse via natural keys; canonical rows unchanged.
- **Checkpoint:** advances normally once the block is committed.
- **Alert/metric:** `duplicate_rows_total` observed; no data corruption.
- **Manual:** not allowed/needed.

### Test D — Provider temporarily fails
- **Input:** provider returns timeout/5xx.
- **Failure:** transient provider error.
- **DB state:** no partial row set for the failed fetch; last good state intact.
- **Checkpoint:** **not** advanced past unfetched data.
- **Alert/metric:** `provider_errors_total`/`retries_total` rise; escalate to alert only if
  sustained beyond budget.
- **Manual:** allowed only if failures persist past the retry/fallback budget.

### Test E — Defensive reorg (unexpected conflicting observation)
- **Input:** canonical chain `...101 <- 102`; provider then presents `102'` at height 102 sharing
  parent `101`.
- **Failure:** a conflicting block at an already-canonical committed height.
- **DB state:** `102` -> `status='orphaned'`, `canonical=false` (raw kept); its transactions/logs
  -> `canonical=false`; derived `token_transfer_candidate` rows from `102` -> `canonical=false`
  (kept); `102'` inserted as canonical; canonical reads exclude `102`. **No raw evidence deleted.**
- **Checkpoint:** keeps advancing; does **not** rewind below the common ancestor `101`.
- **Alert/metric:** **critical alert** + `data_quality_issues` entry + `reorgs_total` increment.
- **Manual:** required (investigation); the system remains consistent meanwhile.
- **Explicit note:** the existence of this test is **not** evidence that Arc normally reorganizes.
  Arc provides deterministic finality; this path is purely defensive and if it fires it is an
  anomaly to investigate.

### Test F — Decoder encounters an unknown event
- **Input:** a `Transfer`-topic log with malformed/missing fields or an unexpected emitter.
- **Failure:** decoder cannot produce a valid candidate.
- **DB state:** raw log stored; **no** invalid normalized row written; issue recorded.
- **Checkpoint:** advances (the block is still valid).
- **Alert/metric:** `decode_failures_total` + `data_quality_issues` row.
- **Manual:** allowed for triage; ingestion continues regardless.

### Test G — Database temporarily unavailable
- **Input:** Postgres connection drops during ingestion.
- **Failure:** write failure.
- **DB state:** no partial writes committed; last good state intact.
- **Checkpoint:** **not** advanced (checkpoint write also fails/rolls back).
- **Alert/metric:** DB-error metric/alert.
- **Manual:** allowed only if the outage persists; recovery reprocesses idempotently.

### Test H — Process restarts from checkpoint
- **Input:** clean restart after a stop.
- **Failure:** none (planned).
- **DB state:** unchanged until new work commits; no gaps, no double-rows.
- **Checkpoint:** resumes from last committed; verifies `parent_hash` continuity before continuing.
- **Alert/metric:** none if continuity holds; alert if continuity check fails.
- **Manual:** not allowed/needed.

Results are recorded as M0.2A acceptance evidence (§25).

---

## 37. Open questions (final classification)

No artificial blockers. "Blocking" means it must be resolved **before writing M0.2A code**.

| Question | Blocking M0.2A? | Why? | Resolution |
|---|---|---|---|
| 1. PostgreSQL hosting | **No** | The design depends on Postgres, not on *where* it runs; self-host is enough | Self-host on the existing VPS (managed deferred to growth) |
| 2. RPC endpoint | **No** | The poller works with any endpoint; defaults are tunable | Public `https://rpc.mainnet.arc.io`; provider key optional |
| 3. Native USDC double-emitter | **No — resolved** | Previously guarded the decoder identity; now answered by official docs | §39: two emitters (`0xffff…fFFE` 18-dec, `0x3600…0000` 6-dec); never sum; USDC canonical = native system stream |
| 4. Operational confirmation depth | **No** | Default 0 is safe and is not a finality claim | `OPERATIONAL_CONFIRMATION_DEPTH = 0` (§9.B) |
| 5. Secrets + DB least privilege | **No** (design) / **Yes** (before deploy) | Design can proceed; a real DB run needs credentials | `.env` chmod 600 + least-privilege role; deferred to deployment |

Deferred (not blocking any milestone start):

| # | Question | Blocking? | Resolution |
|---|---|---|---|
| 6 | WS provider / whether to run WS | No | Polling suffices for M0.2A |
| 7 | Whether Arc exposes `finalized`/`safe` tags | No | Enable `FINALITY_SOURCE` only if verified |
| 8 | Managed PostgreSQL + backups | No | Growth phase |
| 9 | Redis | No | Only if a concrete need appears |
| 10 | Partitioning key for large tables | No | Defer until volume justifies |
| 11 | Snapshot triggers | No | Only after measured need |
| 12 | Third-party indexer adoption | No | Optional accelerators later |
| 13 | Backfill chunk-size defaults | No | Tune at M0.2B with real limits |
| 14 | Monitoring backend beyond logs/Telegram | No | Logs first |
| 15 | Token-discovery breadth/thresholds | No | M0.2B/D |

## 38. `erc20_transfer@1` decoder contract (hard prerequisite)

### Event identity

| Property | Value |
|---|---|
| Signature | `Transfer(address indexed from, address indexed to, uint256 value)` |
| topic0 | `0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef` |
| Indexed | `from` = `topics[1]`, `to` = `topics[2]` (each 32-byte left-padded address) |
| Non-indexed | `value` = `data[0..32]` (one 32-byte uint256) |
| ABI | Standard ERC-20 `Transfer` event (unchanged on Arc) |

### Source identity (which token)

- The token contract address is the **log emitter**: `log.address`.
- **Special case:** the native USDC system emitter `0xffffFFFfFFffffffffffffffFfFFFfffFFFfFFfE`
  emits `Transfer` but is **not** an ERC-20 token contract. It is tagged
  `emitter_kind = "native-system"` (18 dec) and handled per §39.
- For ERC-20 tokens, `log.address` is looked up in the token registry (§30).

### Normalized output: `token_transfer_candidate` (provisional)

Written fields: `chain_id`, `block_number`, `block_hash`, `tx_hash`, `transaction_index`,
`log_index`, `block_timestamp`/`event_time`, `token_address` (emitter), `emitter_kind`
(`erc20` | `native-system`), `from_address`, `to_address`, `value_raw`, `decimals` (**nullable**),
`amount` (nullable; only when `decimals` known), `token_status`, `source_id`, `first_seen_at`,
`decoded_at`, `canonical`, `decoder` (`erc20_transfer`), `decoder_version` (`1`).

### Minimum validation before writing a candidate

1. `len(topics) == 3`; otherwise malformed -> issue recorded, **no** normalized row.
2. `data` is exactly one 32-byte word; otherwise malformed -> issue, no row.
3. `from`/`to` decoded as addresses from `topics[1]/topics[2]`.
4. `value` decoded as `uint256`.
5. `value == 0`: legal for ERC-20, illegal-as-log for native (docs: zero-value native emits no
   log). Store with `is_zero_value = true`; never drop raw.
6. `from == to` (self-transfer): legal ERC-20; store and flag.
7. ERC-20 emitter must be a contract (code exists); unknown/unvalidated tokens are still stored
   as candidates with `token_status = 'unvalidated'`.
8. `decimals` comes from the registry if known; otherwise **NULL** (never guessed), and `amount`
   stays NULL.
9. Zero-address legs (mint/burn) are permitted only for known tokens and the native emitter.
10. A malformed log **never** blocks ingestion; the raw log is always stored and an issue is
    recorded (§22).

### Why `token_transfer_candidate` and not `transfer`

M0.2A cannot definitively validate arbitrary ERC-20 semantics (proxy/fee-on-transfer/rebasing
tokens, non-standard returns, deceptive emitters). Labeling a row `transfer` after seeing a
single `Transfer` log would **invent** ERC-20 truth. A **candidate** with explicit
`token_status` and nullable `decimals` never over-claims, preserves raw evidence, and becomes
fully usable once the token is `REGISTERED` (§30). Tradeoff: candidates require a registry join
for full meaning — acceptable for correctness-first M0.2A.

### M0.2A decode scope

Seed set only (§40). USDC is decoded from the **native system emitter** (canonical; §39); the
ERC-20 USDC contract stream is stored separately and never summed; EURC and cirBTC are decoded
from their ERC-20 contracts. Any other emitter is raw-only in M0.2A.

## 39. Arc USDC double-emitter — RESOLVED

Resolved from official Arc documentation (`USDC system events`; `How to: Index Arc Events`).
**Status: RESOLVED — `BLOCKED_PENDING_ONCHAIN_SAMPLE` is not required.**

1. **Relevant addresses / contracts / precompiles**
   - Native USDC system emitter (EIP-7708): `0xffffFFFfFFffffffffffffffFfFFFfffFFFfFFfE`
     (18 decimals).
   - ERC-20 USDC contract (NativeFiatToken): `0x3600000000000000000000000000000000000000`
     (6 decimals).
   - Legacy testnet (pre-Zero5) native events: `0x1800000000000000000000000000000000000000`
     (`NativeCoinTransferred/Minted/Burned`, 18 dec) — testnet history only; mainnet has used
     EIP-7708 `Transfer` since genesis.
2. **Which events can be emitted**
   - Both the system emitter and the ERC-20 contract emit `Transfer(address,address,uint256)`
     with the **same topic0**.
   - Native: sends (`CALL`), `CREATE` endowment, `SELFDESTRUCT` moves, and precompile-driven
     `mint`/`burn`/`transfer`. Emitted **first** in the tx. Zero-value and self-transfers emit
     **no** log. Gas and block rewards emit **no** `Transfer`.
   - ERC-20: interface calls (`transfer`, `transferFrom`, `approve`-driven moves, mint/burn),
     6 decimals.
3. **Can the same economic movement appear twice?** **Yes.** A single ERC-20 `transfer()`
   produces **two** logs: the ERC-20 contract's 6-dec `Transfer` and the native system 18-dec
   `Transfer`. A plain native send produces only the system log.
4. **Evidence required** — none beyond the official docs above; the two emitters, decimals, and
   the double-emission rule are explicitly documented. A single fixture transaction (one
   ERC-20 USDC transfer) is recommended as a **decoder test**, not as a blocker.
5. **Deduplication identity if required** — **no cross-emitter dedup key is used.** There is no
   safe `(tx_hash, ...)` identity because the two logs have different `log_index` values and a
   tx may contain multiple distinct USDC movements. Policy instead: the **native system stream
   is canonical for USDC movements** (all explicit USDC movements, one stream, 18 dec). If the
   ERC-20 6-dec stream is stored at all, it is a **separate relation/flag**
   (`emitter_kind = 'erc20-interface'`) and is **never unioned or summed** with the native
   stream. The 18-dec and 6-dec values are never mixed or truncated.
6. **Must remain distinct / never deduplicated**
   - Native-only movements (plain value sends) that have no ERC-20 counterpart.
   - Mint/burn zero-address legs.
   - The 18-dec native value vs the 6-dec ERC-20 value of the same movement.
   - Different tokens (EURC, cirBTC) and different movements within one transaction.
   - Gas fees / block rewards (derived from the receipt/`block.miner`, not from `Transfer`).

## 40. Seed / discovery boundary

M0.2A runs on an explicit seed set; broad coverage is a future, costed decision (§30).

**M0.2A seed set (exhaustive):** USDC via the native system emitter (canonical, 18 dec); EURC
(mainnet `0xbEf5f6d51CB62b58e6A8f77868681825C6fe21c1`, testnet
`0x89B50855Aa3bE2F677cD6303Cec089B5F319D72a`); cirBTC mainnet
`0x171A4217b86A807A64eB94757Db6849fb4bDbAA0`; and the ERC-20 USDC contract stored separately
(never summed). Tokens created by our own contracts may be added later. No other emitters are
normalized in M0.2A.

**Boundary guarantee:** the schema stores arbitrary token addresses, `tokens` can grow beyond the
seed, and no component assumes a fixed token list — so the `DISCOVERED -> VALIDATED -> REGISTERED`
pipeline (§30) can expand later without redesign.

## 41. M0.2A data boundary (exact)

| Object | M0.2A | Future | Reason |
|---|---|---|---|
| Block | **YES** | | Foundation of ordering, provenance, checkpoints |
| Transaction | **YES** | | Required for ordering, receipts, funding context |
| Raw Log | **YES** | | Immutable evidence; source for all decoding |
| Transfer Candidate / Transfer | **YES** (candidate) | promoted transfer later | Proves the decoder with a bounded, honest representation |
| Token Registry | **minimal** (seed) | expanded | Needed to interpret candidates; broad discovery deferred |
| Swap | **NO** | M0.2B/D | Requires venue decoders not in M0.2A |
| Pool | **NO** | M0.2B/D | Requires factory/pool events and state calls |
| Liquidity | **NO** | M0.2D | Derived from pool state; not a data-engine primitive |
| Price | **NO** | Price Engine | Facts only in M0.2; measurement later |
| Wallet Features | **NO** | Feature Store | Different module/lifecycle |
| Smart Money | **NO** | Quant engine | Out of scope |
| Signals | **NO** | Quant engine | Out of scope |
| Backtest | **NO** | Backtest Engine | Out of scope |

Every `NO` above is excluded to keep M0.2A a minimal correctness proof; none is architecturally
foreclosed (see §42 Invariant 6 and §43 contract).

## 42. Formal invariants (M0.2A must never violate)

**Invariant 1 — No look-ahead.** Historical logic cannot consume data that was not observable by
timestamp T. Availability is gated conservatively on `canonicalized_at <= T` (default), never on
`event_time` alone (§28).

**Invariant 2 — Canonicality.** Non-canonical/orphaned events must never silently appear in
canonical datasets. All derived reads filter `canonical = true`; raw/audit/quality consumers may
read all statuses (§9.C).

**Invariant 3 — Provenance.** Every normalized row must be traceable to
`source -> block -> tx -> log -> decoder version` (plus time fields). No normalized row exists
without provenance.

**Invariant 4 — Idempotency.** Reprocessing the same source data must not create duplicates.
All writes are keyed `ON CONFLICT` on natural identities (§10).

**Invariant 5 — Ordering.** Event ordering is always
`block_number -> transaction_index -> log_index`, never wall-clock timestamps (Arc timestamps are
non-decreasing at 1-second granularity).

**Invariant 6 — Raw preservation.** Raw evidence is never silently destroyed because
normalization fails. Malformed logs and orphaned data are retained with `canonical=false` and an
issue record.

**Invariant 7 — Decoder versioning.** Changing decoder logic creates a new decoder version;
historical decoded data remains reproducible from raw with its original version (§14).

**Invariant 8 — No silent gaps.** Missing blocks/log ranges must produce detectable
`data_quality_issues` entries and alerts; ingestion never skips a block silently (§35).

## 43. Final M0.2A implementation contract

### Allowed in M0.2A

PostgreSQL; raw blocks; transactions; logs; provenance; the four timestamps; checkpoints;
`ingestion_runs`; `data_quality_issues`; one HTTP RPC source; `erc20_transfer@1` ->
`token_transfer_candidate`; health endpoint; metrics/counters; structured logs; recovery tests.

### Forbidden in M0.2A

Telegram; LLM; Smart Money; wallet scoring; trading; paper trading; execution; swaps; pools;
price engine; liquidity engine; backtesting; broad historical backfill; multi-provider production
failover; AI agents; launchpad.

The forbidden list is binding: none of it may be introduced while implementing M0.2A, even
partially. Any need discovered during implementation is recorded as a future-milestone item, not
absorbed into M0.2A.

---

`M0.2_REVISION_02_STATUS = READY_FOR_HUMAN_REVIEW`

All Revision 01 ambiguities are resolved: finality split into consensus finality / operational
buffer / canonical status (§9); raw-readability matrix defined (§9.C); `erc20_transfer@1` fully
specified (§38); the USDC double-emitter resolved from official docs (§39); seed/discovery
boundary fixed (§40); data boundary (§41), invariants (§42), and implementation contract (§43)
locked; recovery tests tightened (§36); open questions classified with no artificial blockers
(§37).

**No code, migrations, tables, dependencies, services, or connections have been created. No Arc
RPC/WebSocket/blockchain calls. BasePump untouched. Nothing committed.**

STOP AND WAIT FOR HUMAN APPROVAL.

