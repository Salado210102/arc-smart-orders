# ARC AI — Phase 5 addendum: v4 settlement design + executor options

> Design only. No contracts written, no funds, no signing. Read-only research + comparative spec.

## Part 1 — v4 settlement design (read-only research)

### 1.1 Key finding: a minimal executor can talk to the **PoolManager directly**
Arc launchpad liquidity lives in **Uniswap v4** (PoolManager singleton `0x8366a39cc670b4001a1121b8f6a443a643e40951`).
v4 uses a **singleton + flash accounting**: a caller invokes `PoolManager.unlock(data)`, and inside
the `unlockCallback` performs `swap(...)` and then `settle(...)` / `take(...)` to zero out the
currency deltas before returning. **No external router is required** to swap: the executor can
interact with the PoolManager directly. This is the smallest, most auditable path and removes the
need to whitelist a third-party router (single trust anchor = the PoolManager).

### 1.2 Intent → v4 swap mapping
An order intent should carry everything to reproduce the swap deterministically:

| Field | Purpose |
|---|---|
| `poolKey` `(currency0, currency1, fee, tickSpacing, hooks)` | identifies the v4 pool (derivable from `poolId`; we have it in `pools_v4`) |
| `zeroForOne` | direction (sell token = currencyIn → USDC) |
| `amountIn` | exact input (sell size) |
| `minOut` | signed minimum of the output currency (USDC) — **enforced on-chain** |
| `recipient` | user address (output goes here) |
| `deadline` | short TTL; reject after |
| `nonce` | per-user, single-use → **exactly one fill** |

Flow inside `execute(order, sig)`:
1. verify EIP-712 signature + `deadline` + unused `nonce` (mark used).
2. `Permit2.permitWitnessTransferFrom` pulls `amountIn` from the user, with the **intent as witness**
   (binds the signed terms; the executor cannot change them).
3. `PoolManager.unlock(...)` → inside callback `swap(key, {zeroForOne, amountIn, sqrtPriceLimit, hookData})`.
4. `take(outputCurrency, recipient, amountOut)` and `settle(inputCurrency, ...)`; require
   `amountOut >= minOut` (else revert).
5. `unlock` returns only if all deltas are zero (v4 enforces solvency).

### 1.3 Hook / tax caveats (must be measured, not assumed)
- Argus pools have a **bonding hook** that applies taxes on swaps (buy/sell tax, opening
  surcharge). The hook runs inside the swap → **`amountOut` is net of hook taxes**. Therefore
  `minOut` must be computed against the **hook-adjusted** expected output, with a slippage cap.
- Some hooks may set `beforeSwap` policies (anti-sniper, max wallet). The executor must pass the
  correct `hookData` and handle reverts gracefully. **Do not assume Argus-like mechanics for other
  hooks without checking the pool's hook code.**
- Verify empirically (read-only) with a test pool before any build: read the pool state and
  simulate a swap (`eth_call`) to see the realized output vs minOut.

### 1.4 Idempotency & failure
- `nonce` used once → replay impossible; a reverted tx leaves the nonce unused (retry allowed).
- `deadline` + `minOut` prevent stale/under-filled execution.
- Reconciliation reads the tx receipt / event; the chain is the source of truth.

## Part 2 — Route comparison: reuse/fork vs minimal purpose-built

| | Route A — fork `OrderExecutor` + add v4 | Route B — minimal purpose-built order contract |
|---|---|---|
| Fit | general (DCA, recurring, credit wiring) | exactly one signed sell, one fill |
| Est. LOC (est.) | ~450–600 (retains DCA/recurring/whitelist/fee/1271 + new v4 path) | **~150–250** |
| Audit surface | larger: every retained feature is in scope (even unused ones) | small: each line serves this bot only |
| External deps | router/target whitelist + Permit2 + (v3/v4 paths) | **PoolManager + Permit2 only** |
| Unused-feature risk | yes (DCA/credit hooks not needed here) | none by construction |
| Time to audit | higher (more code/cases) | lower (fewer lines/cases) |
| Reuse benefit | dev-time saved | dev-time spent re-writing a small contract |
| Safety base | **unaudited** (`OrderExecutor` not audited) | unaudited too, but far less to audit |

Honest read: the original "reuse because it's battle-tested" rationale **weakens** once we confirm
`OrderExecutor` is unaudited — what remains is only dev-time savings. For a single "signed order →
one fill, `minOut`/deadline/nonce, nothing else", a **minimal contract (Route B)** is likely
**cheaper to audit and easier to reason about**, at the cost of a bit more design now. It also
avoids pulling DCA/credit complexity that arc-intel does not use.

## Part 3 — Open items before choosing
- Confirm the v4 `swap`/`settle`/`take`/`unlock` flow against the **deployed** PoolManager
  (read-only `eth_call` simulation on a real pool; hook tax included).
- Decide Permit2 witness design (single EIP-712 intent reused as the Permit2 witness, like Smart Orders).
- Signing UX (Telegram WebApp needs HTTPS/domain; or deep-link to a wallet / minimal signing page).
- Then: audit vendor + scope for the chosen route.
