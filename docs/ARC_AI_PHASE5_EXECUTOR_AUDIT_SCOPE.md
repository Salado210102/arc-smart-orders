# Audit Scope — Arc AI Phase 5 Minimal Executor

**Project:** Arc AI — Phase 5 non-custodial order executor
**Repo:** https://github.com/Salado210102/arc-smart-orders
**Network:** Arc (testnet `5042002`; mainnet `5042`)
**Frozen at:** git tag **`arc-intel-executor-v1`** (see `*_AUDIT_PACKAGE.md`; content manifest in §7)

---

## 1. Objective

Independent review of a **single-purpose, non-custodial** executor that turns **one user-signed
sell order** into **one fill** against the Uniswap **v4 PoolManager**, with on-chain enforced
`minOut`/`deadline`/single-use `nonce`. Deliverable: findings by severity + remediation pass.

## 2. Scope — contracts & SLOC

> SLOC = raw lines (comments/blank included). Auditable SLOC ≈ **55–60%** of that.

| # | Contract | Path | Lines | Criticality |
|---|---|---|---:|---|
| 1 | **ArcIntelExecutor** | `arc-intel/executor/src/ArcIntelExecutor.sol` | 218 | 🔴 Critical (moves user funds) |
| 2 | **IArcIntel** (vendored interfaces) | `arc-intel/executor/src/interfaces/IArcIntel.sol` | 66 | 🔴 Critical (trust boundary) |
| | **TOTAL** | | **284** | |

Runtime size: **5,161 B** (limit 24,576 B) — see package §2.

**Dependencies (external, NOT in scope, already audited by others):** Permit2
`0x000000000022D473030F116dDEE9F6B43aC78BA3` (canonical Uniswap) and the Arc Uniswap **v4
PoolManager** `0x8366a39CC670B4001A1121B8F6A443A643e40951`.

**Out of scope:** `src/testonly/*` (TestERC20, PoolSeeder), `script/*`, `test/*` (mocks/fork) —
test-only, never deployed in production.

## 3. Security checklist (per invariant)

- [ ] **One intent → at most one fill.** `orderNonceUsed[user][nonce]` set before external calls; a
      reverted fill must NOT consume the nonce (whole tx reverts). `cancelOrder` lets the signer revoke.
- [ ] **`minOut` enforced on-chain**, measured net of hook tax, on the recipient's balance delta.
- [ ] **`deadline` enforced**; expired orders revert.
- [ ] **Signature binding:** one Permit2 `PermitWitnessTransferFrom`; `spender == address(this)`;
      witness = `ArcIntelOrder(poolId, zeroForOne, minOut, recipient, orderNonce)`; token/amount from
      the permit. `poolId` recomputed as `keccak256(abi.encode(PoolKey))`; a mismatched key fails.
- [ ] **Direction/asset binding:** pulled `token` must equal the pool's input side for `zeroForOne`.
- [ ] **Pool allowlist** (`allowedPools[poolId]`) enforced, **fail-closed** (empty ⇒ nothing fills);
      blocks routing through unvetted **hooks**.
- [ ] **`unlockCallback` only callable by the PoolManager** (rejects forged callbacks).
- [ ] **Reentrancy:** guard on `execute`; `unlockCallback` cannot re-enter `execute`.
- [ ] **No custody at rest:** no `rescue`/`withdraw`; input pulled and settled in-tx; dust refunded.
- [ ] **Admin power bounded:** owner (Safe) may only `setPaused` / `setAllowedPool` — never move user
      funds or alter a signed order.
- [ ] **Atomicity:** repay/refund paths cannot leave funds in the executor.
- [ ] **Stateful invariants** (`docs/ARC_AI_PHASE5_EXECUTOR_INVARIANTS.md`): one-fill-per-nonce,
      no-custody, value conservation (received ≤ pulled), `pause` absolute, fail-closed allowlist —
      5000 runs × depth 100, 0 failures.

## 4. Attack vectors considered & mitigations

| Vector | Where | Mitigation |
|---|---|---|
| Keeper redirects/under-fills | executor | Witness + `minOut` recomputed on-chain; keeper can only censor. |
| Replay / double fill | executor | Single-use `orderNonce` + single-use Permit2 permit nonce; reverted fill leaves nonce free. |
| Cross-chain / cross-contract replay | Permit2 | Permit2 EIP-712 domain binds `chainId` + Permit2; `spender` binds this executor. |
| Untrusted hook | v4 `hooks` | `allowedPools` allowlist (Safe-managed); `beforeSwap` runs under the caller's own unlock. |
| Malicious token | ERC20 transfer | Pull is atomic; output measured by balance delta; reverts propagate. |
| Reentrancy | executor | `nonReentrant` on `execute`; `unlockCallback` gated to PoolManager. |
| Griefing / censoring keeper | executor | Keeper is permissionless; the user can self-submit or cancel. |
| Stuck funds | executor | No storage of funds; leftover `tokenIn` returned; all-or-nothing tx. |
| `pause` abuse | owner | Owner cannot execute, redirect, or seize; pause only blocks NEW fills. |

## 5. Known limitations / trust assumptions (declare to reviewers)

- **Permit2 and the v4 PoolManager are trusted** (canonical, externally audited). The executor adds no
  custody and no fund-retaining state.
- **The pool must be allowlisted by the Safe** before any fill; the allowlist is the hook-vetting gate.
- **Hook tax is real and off-chain-unpredictable**: `minOut` is the only price guarantee (measured in
  a testnet fill — see package §4). Reviewers should assess the `beforeSwap`/`afterSwap` delta path.
- **No upgradeability** — immutable; a bug means redeploy.
- **Native-USDC predeploy caveat (Arc):** Arc's USDC (`0x3600…`) is a native-token predeploy; it cannot
  be emulated by a local Foundry fork. The E2E used plain ERC20s; the USDC-specific path on mainnet is
  an Arc/Circle property, not executor code.
- **`sqrtPriceLimitX96`** is set to the extreme sentinel (±1 from the v4 bounds); slippage is bounded
  solely by `minOut`. Flag if you prefer a price-limit guard.

## 6. Requested deliverables

1. Findings report (Critical/High/Medium/Low/Info) with PoCs where applicable.
2. Verification of the invariants in §3.
3. Fuzz/invariant suggestions (nonce/replay, `minOut`, delta side-mapping, allowlist).
4. Remediation review pass.

## 7. Frozen content manifest (SHA-256)

```
57faad3bb1f5061a070b307858548b7cf26705995933cc680645c7ab80c4c642  arc-intel/executor/src/ArcIntelExecutor.sol
de67db32e43b6fcb40b1b76ad45192d00e2258f83b472cd49bc4b6ad4ea720f3  arc-intel/executor/src/interfaces/IArcIntel.sol
1518e2dad68bcabad4f0c036eac46642ac11f5a8e84c4f1f04b76f98977bb4f1  arc-intel/executor/foundry.toml
4e2f2b69b4c9419c609cc2a5fbb78170ad2b75f38922c15cd8914b19fa619256  arc-intel/executor/test/ArcIntelExecutor.t.sol   (* expanded post-tag, Slither regression)
553e105c5344dece5747fe205ecc5367a46a7623e473596895aea931b720429c  arc-intel/executor/test/mocks/Mocks.sol      (* expanded post-tag, Slither regression)
f7b8e0d9127614e346ec6b5740c3e965695d71d892bb4dbebf0924fda8241094  arc-intel/executor/test/ArcIntelFork.t.sol
8af84068c0201237217b2a8f2dcb7cbd2b0c98f20cbb5b92b0155835225346a4  arc-intel/executor/src/testonly/TestERC20.sol
1e4e930ed6200762f2585ca5cf4d12b937547373dd28a14fec7236a2cc675a9a  arc-intel/executor/src/testonly/PoolSeeder.sol
515a662971de10a57dce5e0ab2bc4e6c59c52ecd0304b9af44756a3bfdcc5dfa  arc-intel/executor/script/DeployE2E.s.sol
fbdcff78f5b162d58efab6f21271aaf2f7850161247bd1598b26f87cf01d10b5  docs/ARC_AI_PHASE5_MINIMAL_EXECUTOR_SPEC.md
d03b11f38d58ccfa26cbea3a23feb4ac5b28f9cf14e18ee4970088ad7b1cb4ee  docs/ARC_AI_PHASE5_EXECUTION_DESIGN.md
ecafbdf990136d02c78ca1f42e22be22f35c53c082260d731f329e0c81812ac8  docs/ARC_AI_PHASE5_V4_EXECUTOR_OPTIONS.md
dbd19ccbb1d957032eb15e82f92bf06a3bfb858dc2a4d79a3b8779c459762e83  arc-intel/executor/test/ArcIntelExecutor.invariants.t.sol  (* added post-tag)
754f5e1076b130a7682bcaea1e015546c438085425ad4e1a7340174c4006dd67  arc-intel/executor/README.md                            (* added post-tag)
d3ca058c19f0ccd4b6f30739b412c3375e3ef23016cac42cb7386fd890f44410  docs/ARC_AI_PHASE5_EXECUTOR_INVARIANTS.md                (* added post-tag)
```
