# ARC AI — Phase 5: Minimal Executor Contract (Route B) — SPEC

> Design only. Not implemented, not deployed, not audited. One signed order → one fill.

## 1. Purpose

A single-purpose, **non-custodial** executor for arc-intel: a user signs **one sell order**
(token → USDC) with `minOut`/`deadline`/`nonce`; a **keeper** (any relayer) submits it; the
contract fills it against the **Uniswap v4 PoolManager** and enforces the signed terms. No
recurrence, no DCA, no credit, no custody.

## 2. Dependencies (canonical only)

- **Permit2** `0x000000000022D473030F116dDEE9F6B43aC78BA3` — confirmed deployed on Arc; canonical
  Uniswap contract (externally audited). We reuse the EIP-712 + `permitWitnessTransferFrom`
  pattern **on the canonical Permit2** (not a custom fork).
- **Uniswap v4 PoolManager** `0x8366a39cc670b4001a1121b8f6a443a643e40951` — confirmed contract.
- No external router; no third-party swap target to whitelist.

## 3. Intent (EIP-712)

```
struct Order {
  address user;        // payer + recipient
  PoolKey poolKey;     // (currency0, currency1, fee, tickSpacing, hooks)
  bool    zeroForOne;  // direction (token -> USDC)
  uint256 amountIn;    // exact input (sell size)
  uint256 minOut;      // signed minimum output (USDC), net of hook tax
  address recipient;   // output destination (user)
  uint256 deadline;    // short TTL
  uint256 nonce;       // single-use
}
```
**Domain separator (explicit, corrected):** the user signs exactly **one** message — a Permit2
`PermitWitnessTransferFrom` — and it is **Permit2's own EIP-712 domain** that is used:
`EIP712Domain{ name = "Permit2", version = "1", chainId, verifyingContract = the canonical Permit2 }`.
So the signature is bound to **this chain** (chainId) and to **Permit2** (verifyingContract), hence
not replayable on another chain. Binding to **this executor** comes from the signed `spender` field
(`spender == address(this)`), which Permit2 enforces against `msg.sender`. The order-specifics
(`poolId, zeroForOne, minOut, recipient, orderNonce`) are bound via the **witness**; `token/amount`
come from the permit. **The executor computes no domain of its own** (an earlier draft had unused
domain constants; removed). Corrected explicitly, not assumed.

## 4. State & roles

- `permit2`, `poolManager` — **immutable**.
- `nonceUsed[user][nonce]` (or bitmap) — single-use.
- `owner` = **Safe** — only for `pause()` and `setAllowedPools` (see scope below).
- **Whitelist scope (exact):** an **allowlist of `poolId`** where `poolId = keccak256(abi.encode(poolKey))`
  — i.e. vetted token+hook+pool combinations, **not arbitrary tokens**. `execute` reverts unless the
  order's `poolId` is allowed; **fail-closed** (empty allowlist ⇒ nothing fills). Its role is **not**
  price protection (that is `minOut`); it stops routing through an **unvetted/malicious hook** whose
  `beforeSwap` could misbehave or attempt reentrancy. Only the Safe can edit it.
- `paused` flag — emergency stop (does not touch existing user orders beyond blocking new fills).
- **No fund custody at rest** → no rescue/withdraw function exists (nothing to rescue). This is a
  deliberate security simplification: no admin path can move user funds.

## 5. Functions (minimal)

- `execute(Order order, bytes signature) external` — **permissionless** (any keeper/relayer):
  1. require `!paused`, `block.timestamp <= deadline`, `!nonceUsed[user][nonce]`; set used.
  2. `Permit2.permitWitnessTransferFrom(permit, transferDetails, user, witness=Order)` — pulls
     `amountIn` of the input currency; the witness binds the exact order (token/pool/minOut).
  3. `PoolManager.unlock(abi.encode(order))` → in `unlockCallback`:
     - `swap(poolKey, {zeroForOne, amountIn, sqrtPriceLimit, hookData})`.
     - `take(outputCurrency, recipient, amountOut)`; if `amountOut < minOut` → revert.
     - `settle(inputCurrency, ...)` using the pulled funds.
  4. emit `Filled(user, poolId, amountIn, amountOut, nonce)`.
- `cancelOrder(Order order) external` — the **user** marks their nonce used (revoke before fill).
- `pause(bool)` / `setAllowedPools(...)` — owner (Safe) only.

No other functions. No fees (platform fee, if any, taken on the output with a hard cap; deferred
to a later audited change).

### 5.1 Who pays gas & keeper trust model
- **The keeper (relayer) pays gas**; the **user only signs** the intent and never sends a tx.
- The signature binds `user, poolKey, zeroForOne, amountIn, minOut, recipient, deadline, nonce`.
  A keeper can therefore only choose **whether** and **when** (within `deadline`) to submit — it
  **cannot** alter size, minimum output, recipient, or route. Its worst case is **censorship
  (not submitting), not theft**; `minOut`/`deadline`/single-use `nonce` close the rest.
- The user can always `cancelOrder` on-chain before a fill; an unfilled order simply expires.

### 5.2 Pause — intent
- `pause` exists **only as an emergency stop for new fills**, not for routine ops or market moves
  (those are already handled by `minOut`). Trigger scenarios: (a) a suspected bug in the executor
  or its v4/Permit2 integration; (b) a dependency incident (PoolManager/Permit2) or an Argus hook
  behavior change/bug; (c) active exploitation or abnormal on-chain conditions affecting in-flight
  orders. Pending user orders are never executed by the admin — they expire at `deadline` or are
  cancelled by the user. (Full runbook deferred to implementation.)

## 6. Security properties / invariants (to be tested & audited)

- **One fill per nonce** (replay impossible); a reverted fill leaves the nonce unused.
- **`minOut` and `deadline` enforced on-chain**; keeper cannot alter signed terms or redirect output.
- **No custody at rest**; `execute` is atomic (v4 unlock requires zero deltas → all-or-nothing).
- **No owner power over user orders** (owner only pauses / whitelists pools).
- Reentrancy guarded; checks-effects-interactions around Permit2/pool calls.
- Output measured **net of hook tax** (Argus hook: sell tax 1% + pool fee 1% → ≈2% before slippage).
- `sqrtPriceLimit` bounded to avoid pathological fills.

## 7. Estimated size

- **~150–220 lines** (vs ~450–600 for a forked general executor). Fewer lines → smaller audit
  surface → cheaper/faster audit.

## 8. v4 simulation status (honest)

- **Measured (read-only `eth_call`)**: hook tax getters for the LUNYA pool (buy/sell 1%, pool fee
  1%, not bonded). This was the main unknown for `minOut`.
- **Not possible via plain `eth_call`**: a full swap, because v4 `unlock` calls back the *caller*
  (`unlockCallback`) — an EOA has no code and no router is deployed here. The exact realized
  `amountOut` (incl. hook `beforeSwap`) will be validated with the **minimal executor** on a
  **fork / testnet / state-override** environment during implementation — not assumed.

### 8.1 Fork validation (implemented, read-only, no funds)
A Foundry fork harness (`arc-intel/executor/test/ArcIntelFork.t.sol`, `RUN_FORK=1`) runs against the
**real** Arc PoolManager + a real Argus pool. Findings:

- **Validated**: our vendored `IPoolManager` ABI matches the deployed manager — `unlock` → `swap`
  executed, the `Swap` event fired, and the Argus `afterSwap` hook was invoked. Confirms the
  canonical v4 flow, including that the deployed manager uses no-arg `settle()` + `sync()`.
- **Real bug caught & fixed**: v4 `BalanceDelta` packs **amount0 in the UPPER 128 bits and amount1 in
  the LOWER 128** (confirmed against `v4-core` `BalanceDelta.sol`). The first version had them
  inverted; the fork test exposed it before any audit. Fixed in `ArcIntelExecutor` + mocks.
- **Blocker (environmental, not our code)**: Arc's USDC (`0x3600…`) is a **native-token predeploy**
  that delegates to `0x1800…`, which Foundry's EVM cannot emulate (`OpcodeNotFound`). So a *local*
  fork cannot complete the token transfer end-to-end. Full end-to-end fill must be validated on
  **Arc testnet** with real transactions.

### 8.2 Testnet E2E — VERIFIED (Arc testnet 5042002)
A real fill was executed end-to-end against the **real** v4 PoolManager on Arc testnet, using two
throwaway ERC20s and a self-seeded pool (hook `address(0)`), avoiding the native-USDC predeploy.

- **Executor** `0x89dFF7077543feE9dF7fa470e89737FaDDc935E8` · **PoolManager** `0x8366a39CC670B4001A1121B8F6A443A643e40951` ·
  pool `fee=3000 / tickSpacing=60 / hooks=0`.
- **Fill tx** [`0x44fc6ecea5232153c53a57174b02ea5a3df472a891191692fbaddfe5c10038b4`](https://explorer.testnet.arc.io/tx/0x44fc6ecea5232153c53a57174b02ea5a3df472a891191692fbaddfe5c10038b4) — **status success**.
- **Verified on-chain**: seller spent `1e15` tokenIn and received `996006981039903` tokenOut (≥ signed `minOut` `9e14`).
- **What this proves**: the **canonical Permit2** accepted our `PermitWitnessTransferFrom` signature
  (witness = `ArcIntelOrder`), the executor pulled the exact signed amount, swapped via the real v4
  `unlock`→`swap`→`take`/`settle`, enforced `minOut`, and paid out to the recipient — atomically.
- **Key hygiene**: the test key was generated **only** for this validation (unrelated to any real
  wallet), funded via the Circle faucet, used once, and **destroyed** (`keystore DESTROYED`) after the
  run. Not reused. (An earlier generated key was discarded unused after an accidental local-print
  incident — never funded, never used.)

## 9. Signing UX (recommended)

- **Deep-link / WalletConnect to the user's own mobile wallet** first (no domain/HTTPS to host,
  no custom signing UI to build/secure); the user signs in a wallet they already trust.
- A minimal hosted signing page is only a fallback for desktop users without a mobile wallet.

## 10. Before any audit vendor

- Freeze this spec; build the minimal contract; add fork/invariant tests (§6); simulate a real
  fill; then hand a small, single-purpose package to audit.
