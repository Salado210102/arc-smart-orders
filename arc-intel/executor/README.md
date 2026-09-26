# ArcIntelExecutor

Minimal, **non-custodial** Uniswap **v4** executor for arc-intel: **one user-signed sell order → one
fill**, with on-chain `minOut` / `deadline` / single-use `nonce`. No custody at rest, no upgradeability.
The owner (a Safe) can only `pause` and edit the pool allowlist.

## Quickstart

```bash
forge build --sizes
forge test                                   # 24 unit/fuzz + 5 stateful invariants; fork skipped
RUN_FORK=1 forge test --match-test testForkRealPoolSellLunya -vv   # Arc-mainnet fork (read-only)
forge test --match-contract ArcIntelExecutorInvariants \
  --invariant-runs 5000 --invariant-depth 100                       # heavier invariant campaign
```

- ~230 LOC, runtime ~5.2 kB (well under the 24,576 B limit).
- The executor talks **directly to the v4 PoolManager** (`unlock`→`swap`→`take`/`settle`); no router.
- Funds move via the **canonical Permit2** `permitWitnessTransferFrom` (witness = the signed order).

## Documentation

| Doc | What |
|---|---|
| [`docs/ARC_AI_PHASE5_EXECUTOR_AUDIT_SCOPE.md`](../../docs/ARC_AI_PHASE5_EXECUTOR_AUDIT_SCOPE.md) | Audit scope, invariants, threat model, frozen content manifest (SHA-256) |
| [`docs/ARC_AI_PHASE5_EXECUTOR_AUDIT_PACKAGE.md`](../../docs/ARC_AI_PHASE5_EXECUTOR_AUDIT_PACKAGE.md) | Build/test evidence, E2E fill, reviewer quickstart |
| [`docs/ARC_AI_PHASE5_MINIMAL_EXECUTOR_SPEC.md`](../../docs/ARC_AI_PHASE5_MINIMAL_EXECUTOR_SPEC.md) | Contract spec, v4 settlement, E2E result |
| [`docs/ARC_AI_PHASE5_V4_EXECUTOR_OPTIONS.md`](../../docs/ARC_AI_PHASE5_V4_EXECUTOR_OPTIONS.md) | Reuse/fork vs minimal (why Route B) |
| [`docs/ARC_AI_PHASE5_EXECUTOR_SLITHER_TRIAGE.md`](../../docs/ARC_AI_PHASE5_EXECUTOR_SLITHER_TRIAGE.md) | Slither findings + triage + empirical regression proof |

Frozen artifact: git tag **`arc-intel-executor-v1`** (contract hash `57faad3b…c642`; tests expanded
post-tag, marked as such in the scope manifest).

## Layout

```
src/ArcIntelExecutor.sol      the contract (audit target)
src/interfaces/IArcIntel.sol  minimal vendored Permit2 / v4 PoolManager interfaces
test/                         unit + fuzz + invariant + fork tests, mocks
src/testonly/                 TestERC20 + PoolSeeder (testnet E2E only, NOT audit scope)
script/DeployE2E.s.sol        testnet deploy/seed script (NOT audit scope)
```

## Verified end-to-end

Real fill on **Arc testnet (5042002)** against the live v4 PoolManager:
[`0x44fc6ece…038b4`](https://explorer.testnet.arc.io/tx/0x44fc6ecea5232153c53a57174b02ea5a3df472a891191692fbaddfe5c10038b4)
— sold `1e15`, received `996006981039903` (≥ `minOut`).

> External dependencies (trusted, already audited): canonical **Permit2**
> `0x000000000022D473030F116dDEE9F6B43aC78BA3`, and the v4 **PoolManager**
> `0x8366a39CC670B4001A1121B8F6A443A643e40951`.
