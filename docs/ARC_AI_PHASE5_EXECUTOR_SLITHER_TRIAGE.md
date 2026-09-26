# Slither Triage — Arc AI Phase 5 Executor (appendix)

> Post-tag appendix. **Contract/interfaces unchanged**; the frozen artifact hash in
> `ARC_AI_PHASE5_EXECUTOR_AUDIT_SCOPE.md` §7 still matches the running tree
> (`ArcIntelExecutor.sol` = `57faad3b…c642`). Two **regression tests** were added post-tag (test files
> only; updated hashes below). Kept for total transparency to any reviewer.

## Run

- Tool: **Slither 0.11.6** · compile via Foundry (`forge build --build-info`, `--skip ./test/** ./script/**`)
- Command: `slither . --checklist` (from `arc-intel/executor/`)
- Scope analyzed: **8 contracts / 102 detectors** (src: `ArcIntelExecutor`, vendored `IArcIntel`, `testonly/*`)
- Result: **12 findings** — `reentrancy-balance` (High) · `unchecked-transfer` (High) ·
  `unused-return` (Medium) · `timestamp` (Low)

## Findings & triage

### reentrancy-balance — High / Medium-confidence — **FALSE POSITIVE (by design)**
- `ArcIntelExecutor.execute` `src/ArcIntelExecutor.sol#L128-L177`; external call `poolManager.unlock(...)` L166;
  balance read `outBefore` L163; stale use `amountOut < order.minOut` L170.
- **Why it does not apply here:** (1) `execute` is `nonReentrant`, so a hook cannot re-enter it;
  (2) the measurement is the **recipient's own balance delta**, i.e. the ground truth of what the user
  *actually received* — a balance decrease can only make `amountOut` smaller and therefore **fail
  `minOut` and revert** (fail-safe); (3) within `unlockCallback` the Argus hook runs **before** our
  `take`, so it cannot remove the output before we send it; (4) the pool/tokens are **allowlisted by the
  Safe**, so a balance-lying token is out of the trust model.
- **Action:** none.

### unchecked-transfer — High — **NOT EXPLOITABLE here (fail-safe); best-practice note**
- `ArcIntelExecutor.execute` L174 (`transfer(user, leftover)` refund) and `_settle` L215
  (`transfer(poolManager, amount)`).
- **Why it is safe in this design:** `_settle` runs just before `poolManager.settle()`; if the transfer
  silently paid nothing, the PoolManager's own delta accounting is not cleared and `unlock` reverts
  (`CurrencyNotSettled`) → the whole tx reverts. The dust refund, if a false-returning token ignored it,
  only leaves that dust in the executor (no custody, no user loss). Pool/token allowlist applies.
- **Best-practice recommendation (optional, NOT applied):** use a checked transfer (SafeERC20-style)
  to make the failure explicit. Deferred — it would change the frozen artifact and require a new tag.
- (`PoolSeeder.sol` L58/L65 hits are **test-only / out of scope**.)

### unused-return — Medium — **INFORMATIONAL**
- `execute` L166 ignores `poolManager.unlock(...)` return (the callback's `bytes`); `_settle` L216
  ignores `settle()`'s `paid`. Neither return is needed: settlement is enforced by the manager's
  accounting, not by the returned value.
- (`PoolSeeder.sol` L42/L50/L59/L66 are **test-only / out of scope**.)

### timestamp — Low — **ACCEPTED (informational)**
- `execute` L135 `block.timestamp > order.deadline`. Deadlines are a standard UX/MEV guard; small
  validator drift is expected and irrelevant to fund safety (`minOut` is the economic guarantee).

## Empirical confirmation (regression tests)

The two High findings were converted from "architectural argument" to **demonstrated behavior** with
two tests (added post-tag; **contract untouched**):

- **`testUncheckedTransferRevertsWholeTx`** — uses a token that returns `false` on `transfer()` **without
  reverting** and a mock manager with strict v4 flash accounting. Result: the whole tx **reverts with
  `CurrencyNotSettled`**, the Permit2 pull is undone and the order nonce is **not** consumed. Proves the
  fail-safe of the `unchecked-transfer` finding.
- **`testMaliciousHookCannotReenterOrManipulate`** — a hook running inside the swap that (1) tries to
  re-enter `execute` and (2) tries to move the recipient's output out (allowance-enforcing token, plus a
  pre-existing balance). Result: reentry **blocked by `nonReentrant`**, the drain **fails**, and the
  measured `amountOut` equals exactly the pool output with the pre-existing balance untouched. Proves the
  `reentrancy-balance` finding is a false positive here.

Suite: **24/24 passing** (`forge test`), fork test skipped by default.

## Conclusion

No Slither finding is an **applicable High/Medium** issue in this contract. The two High-severity
detectors are a by-design false positive and a fail-safe best-practice note. No code change is proposed;
the only optional hardening (checked ERC20 transfer) is deferred to an explicit owner decision because
the artifact is frozen at `arc-intel-executor-v1`.
