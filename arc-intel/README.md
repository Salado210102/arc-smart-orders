# ARC Intelligence — Phase 1: on-chain event indexer (read-only)

Foundation module for the ARC Intelligence engine. **Read-only**: no signing, no transaction
sending, no execution code path. Its only job is to capture and persist Arc mainnet swaps and
launchpad events reliably and idempotently.

## Status (honest)

- Argus portal `0xb021be536808f551b31789422fd28a6c9c6e97da` **exists on Arc** and emits events
  (verified on-chain). [MEDIDO]
- **Bitquery source is scaffolded but DISABLED**: it requires `BITQUERY_OAUTH` and independent
  confirmation that Bitquery indexes Arc. Neither could be verified here. [BLOQUEADO]
- **Argus ABI**: event signatures taken from the **official repo** `arguspad/argus-world`
  (`onchain/event-signatures.md`) and cross-checked with keccak256 (TokenCreated/PartsDeployed/CurveOpened).
  Source = official GitHub repo, **not explorer-verified** (Arc Blockscout API is Cloudflare-blocked).
  `TokenCreated` is decoded → `tokens` populated (name/symbol/creator/pool_id) on real data.
  **No `DevBuy` event exists in Argus** → `dev_buys` is not populated (would require inference). [MEDIDO]
- **Uniswap v4 (PoolManager `0x8366…0951`)**: Initialize/ModifyLiquidity/Swap/Donate confirmed via official
  `Uniswap/v4-core` signatures + keccak256. `Initialize` → `pools_v4` (poolId→currency0/currency1); v4 `Swap`
  → `swaps` (dex `uniswap_v4`, token resolved via `pools_v4`). In the validated range **v4 = 472 swaps vs
  v3/v2 = 91 (~84% previously missed)**. [MEDIDO]
- **`dev_buys_inferred`** is a VIEW over `swaps` (`wallet == tokens.creator` within a configurable window,
  default 24h), `is_inferred=1`, separate from confirmed `dev_buys`. It is **0 on v4 launches** because the
  launch Swap `sender` is the Argus Portal, not the creator (correct inference needs ERC-20 `Transfer(to==creator)`). [MEDIDO]
- A working **RPC source** is included as a stopgap so the pipeline can be exercised end-to-end
  on real Arc data now (swaps + raw launchpad events + token rows via pool `token0/token1`). [MEDIDO]

## Architecture (source-agnostic)

```
EventSource (RPC now / Bitquery when enabled)
      ↓
IndexerService  (poll loop, reconnect+backoff, cursor, health)
      ↓
EventProcessor  (normalize → rows; idempotent)
      ↓
Storage (SQLite repo; portable schema for Postgres later)
```

No secrets in code. Config via env: `ARC_RPC`, `INDEXER_DB`, `INDEXER_LOG`,
`INDEXER_POLL_SECONDS`, `INDEXER_MAX_RANGE`, `BITQUERY_OAUTH`.

### Tables
`tokens`, `swaps`, `dev_buys`, `launchpad_events`, `wallets`, `health`, `meta`.
Idempotency key = `(tx_hash, log_index)`.

### Adding a launchpad
Add `LaunchpadConfig(name, address, topic_map=<topic0→name>)` in `indexer/config.py`. No pipeline
change (Flutchfun / NebulaPad / Lunya already anticipated).

## Run

```bash
# from arc-intel/
python -m indexer.run --start 22700000 --ticks 3 --range 200 --resolve-tokens --report
```

## Tests

```bash
cd arc-intel
python -m unittest discover -s tests -t . -v
```
