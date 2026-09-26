# Stateful Invariant Campaign — Arc AI Phase 5 Executor (appendix)

> Post-tag **additional testing**. **Contract untouched** (`ArcIntelExecutor.sol` = `57faad3b…c642`);
> tag `arc-intel-executor-v1` unchanged. Kept for total transparency to any reviewer.

## Harness

- `test/ArcIntelExecutor.invariants.t.sol` — a `Handler` exposing eight fuzzed entrypoints:
  happy-path (`executeValidA/B`) **plus four must-fail actions** (`executeExpired`,
  `executeMinOutTooHigh`, `executeWhilePaused`, `executeDisallowed`) and the state toggles
  (`setPaused`, `setPoolAllowed`).
- The campaign fuzzes **only** the handler; tokens, pool manager and executor are `excludeContract`ed
  so the fuzzer cannot mint tokens or change the pool rate (harness-only actions).
- Rate is fixed **1:1** and the fuzzer cannot change it → conservation is well-defined.

The must-fail actions are **attempted, not avoided**: each `execute*` explicitly expects a revert and
increments a per-category counter; a success is recorded as `unexpectedSuccess` (which must stay 0).

## Invariants

| # | Invariant | Statement |
|---|---|---|
| 1 | `invariant_noDoubleFill` | One intent → at most one fill: no `(user, nonce)` is ever filled twice. |
| 2 | `invariant_noCustody` | After every interaction the executor holds **0** of both tokens. |
| 3 | `invariant_noValueCreated` | Σ received by recipients ≤ Σ pulled via Permit2 (no tokens from nothing). |
| 4 | `invariant_pauseAbsolute` | While paused, **no** fill succeeds, under any input. |
| 5 | `invariant_emptyAllowlistNoFill` | With the pool not allowlisted, **no** fill succeeds (fail-closed). |
| 6 | `invariant_noUnexpectedSuccess` | No must-fail action (expired / minOut-too-high / paused / disallowed) ever succeeds. |

## Result

```
ArcIntelExecutorInvariants invariants (runs: 5000, calls: 500000, reverts: 0)
[PASS] invariant_emptyAllowlistNoFill
[PASS] invariant_noCustody
[PASS] invariant_noDoubleFill
[PASS] invariant_noUnexpectedSuccess
[PASS] invariant_noValueCreated
[PASS] invariant_pauseAbsolute
```

- **5000 runs × depth 100 = 500,000 calls, 0 handler reverts, 6/6 invariants hold** (~2m37s).
- **Active break coverage** (per run; totals across the campaign in the selector table ≈62k each):
  `expiredTried ≈ 11`, `minOutTried ≈ 9`, `pausedTried ≈ 14`, `disallowedTried ≈ 15`, `validFills ≈ 3`
  per run. So the campaign **did try** the edge cases — and the contract correctly rejected them.
- Default (`forge test`, 256 runs) also green.

> The must-fail semantics are *also* asserted deterministically by unit tests with `vm.expectRevert`
> (`testRevertExpired`, `testRevertMinOutNotMet`, `testRevertWhenPaused`, `testRevertRevokedPool`),
> so this invariant campaign adds stateful coverage on top of exact-revert assertions.

Reproduce:
```bash
FOUNDRY_INVARIANT_RUNS=5000 FOUNDRY_INVARIANT_DEPTH=100 \
  forge test --match-contract ArcIntelExecutorInvariants
```

## Two initial failures — root-caused (harness artifacts, not contract bugs)

Documented per the project's rule (reproduce, root-cause, never just silence).

**F1 — `invariant_noCustody`: executor "held" 1716 tokenA.**
- *Sequence*: `MockERC20.mint(<addr>, 1716)`.
- *Root cause*: Foundry's invariant fuzzer, by default, targets **all** contracts deployed in
  `setUp` — so it called `mint` directly on the token (and could have called it with the executor as
  recipient). That is a harness action impossible in production, not a contract defect.
- *Fix*: restrict targeting — `targetContract(handler)` +
  `excludeContract(tokenA/tokenB/poolManager/permit2/executor)` + `excludeSelector(setExecutor)`.

**F2 — `invariant_noValueCreated`: received (1.75e19) > pulled (1281).**
- *Sequence*: `MockPoolManager.setRate(13676669198579488431022338302651878)` then a fill.
- *Root cause*: the fuzzer raised the mock pool's **rate** far above 1, so the pool paid out more than
  was put in — again a harness mutation (the rate models market price, not executor logic). The
  invariant "received ≤ pulled" is only meaningful with rate ≤ 1, which the 1:1 campaign enforces.
- *Fix*: same target restriction (the pool manager is no longer fuzzable).

After the fix, the 5000×100 campaign shows **0 failures and 0 handler reverts**.
