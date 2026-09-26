# Audit Package — Arc AI Phase 5 Minimal Executor

> Everything a reviewer needs to reproduce the build, run the tests, and verify the E2E fill.
> **Frozen at git tag `arc-intel-executor-v1`** (`git rev-parse arc-intel-executor-v1`).

| | |
|---|---|
| Repo (MIT) | https://github.com/Salado210102/arc-smart-orders |
| Scope | [`ARC_AI_PHASE5_EXECUTOR_AUDIT_SCOPE.md`](ARC_AI_PHASE5_EXECUTOR_AUDIT_SCOPE.md) — **1 contract + interfaces / 284 SLOC** |
| Design | [`ARC_AI_PHASE5_MINIMAL_EXECUTOR_SPEC.md`](ARC_AI_PHASE5_MINIMAL_EXECUTOR_SPEC.md) · [`ARC_AI_PHASE5_V4_EXECUTOR_OPTIONS.md`](ARC_AI_PHASE5_V4_EXECUTOR_OPTIONS.md) |
| Network | Arc testnet `5042002` (mainnet `5042` pending) |
| Venue | Uniswap **v4** PoolManager `0x8366a39CC670B4001A1121B8F6A443A643e40951` |
| Token transfer | canonical **Permit2** `0x000000000022D473030F116dDEE9F6B43aC78BA3` |

---

## 1. Reproducible / deterministic build

`arc-intel/executor/foundry.toml`:

```toml
solc = "0.8.26"
auto_detect_solc = false
evm_version = "cancun"
optimizer = true
optimizer_runs = 200
via_ir = true
bytecode_hash = "none"   # deterministic bytecode (no metadata hash)
```

```bash
cd arc-intel/executor
forge build --sizes
forge test              # 24 unit/invariant/fuzz pass; fork test skipped unless RUN_FORK=1
```

## 2. Contract sizes (Spurious Dragon limit = 24,576 B runtime)

| Contract | Runtime (B) | Margin (B) |
|---|---:|---:|
| **ArcIntelExecutor** | **5,161** | **19,415** |

## 3. Test evidence

- **24/24** passing (`test/ArcIntelExecutor.t.sol`), including the two Slither-driven regressions
  (`testUncheckedTransferRevertsWholeTx`, `testMaliciousHookCannotReenterOrManipulate`; see
  [`..._SLITHER_TRIAGE.md`](ARC_AI_PHASE5_EXECUTOR_SLITHER_TRIAGE.md)) and:
  - fill + output to recipient (own and third party), **zero custody**;
  - witness binding; paused; pool not allowed/revoked; expired; nonce reuse;
  - token mismatch; `minOut` (exact + fuzz); partial fill with **dust refunded**;
  - **reentrancy** (hostile hook re-entering `execute`); `unlockCallback` only PoolManager;
  - `onlyOwner` on pause/allowlist; cancel (own and other users');
  - **atomicity: nonce NOT consumed when the swap reverts** (hostile/reverting pool).
- **Fork harness** (`test/ArcIntelFork.t.sol`, `RUN_FORK=1`) against the **real** PoolManager + a real
  Argus hook on an Arc-mainnet fork: validated the v4 ABI and **caught a real bug** — `BalanceDelta`
  packs **amount0 in the upper 128 bits** — which was fixed before audit (see SPEC §8.1).

## 4. Testnet E2E — VERIFIED (Arc testnet 5042002)

| Field | Value |
|---|---|
| **Executor** | `0x89dFF7077543feE9dF7fa470e89737FaDDc935E8` |
| Pool | `fee=3000 / tickSpacing=60 / hooks=0` (self-seeded, test tokens) |
| **Fill tx** | [`0x44fc6ecea5232153c53a57174b02ea5a3df472a891191692fbaddfe5c10038b4`](https://explorer.testnet.arc.io/tx/0x44fc6ecea5232153c53a57174b02ea5a3df472a891191692fbaddfe5c10038b4) — **success** |
| Result | seller spent `1e15` tokenIn → received `996006981039903` tokenOut (≥ signed `minOut` `9e14`) |

**Proves:** canonical Permit2 accepted the `PermitWitnessTransferFrom` (witness `ArcIntelOrder`), the
executor pulled the exact signed amount, ran `unlock`→`swap`→`take`/`settle` on the real v4 manager,
enforced `minOut`, paid the recipient — atomically.

> **Test-key hygiene:** generated only for this validation (unrelated to any real wallet), funded via
> the Circle faucet, used once, **destroyed** after. A prior generated key was discarded unused after
> an accidental local print (never funded/used).

## 5. Out of scope / known limitations (declare to reviewers)

See scope §5. Highlights: Permit2 and the v4 PoolManager are trusted/external; the pool allowlist is
the hook-vetting gate; hook tax is measured but only `minOut` guarantees price; **native-USDC predeploy
cannot be forked locally** (the E2E used plain ERC20s); `sqrtPriceLimitX96` uses the extreme sentinel.

## 6. Reviewer quickstart

```bash
git clone https://github.com/Salado210102/arc-smart-orders && cd arc-smart-orders/arc-intel/executor
git checkout arc-intel-executor-v1
forge build --sizes
forge test -vvv
# start here: docs/ARC_AI_PHASE5_EXECUTOR_AUDIT_SCOPE.md (§3–5), then src/ArcIntelExecutor.sol
```

## 7. Pre-submission checklist

- [x] Deterministic compiler config
- [x] `forge build --sizes` — well under the limit
- [x] `forge test` — 24/24
- [x] Fork harness vs real PoolManager (bug caught & fixed)
- [x] **Real testnet E2E fill** (tx recorded above)
- [x] Scope / threat model (`..._AUDIT_SCOPE.md`)
- [x] Design docs (spec + v4 route comparison)
- [x] Content manifest (SHA-256) in scope §7
- [ ] Create git tag `arc-intel-executor-v1` (pending owner approval to commit)
- [ ] Choose + contract the auditor (owner decision, human/third-party)
