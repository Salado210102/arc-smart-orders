# Smart Contract Audit — Scope & Security Package

**Project:** Arc Smart Orders + Agent Launchpad
**Repo:** https://github.com/Salado210102/arc-smart-orders
**Network:** Arc (testnet 5042002 · mainnet 5042)
**Commit at scope:** git tag **`pre-audit-v2`** (`git rev-parse pre-audit-v2`) — frozen package in [`AUDIT_PACKAGE.md`](AUDIT_PACKAGE.md)

---

## 1. Objective

Independent review of the non-custodial order engine and the agent-launchpad economic modules,
focusing on **fund safety, economic invariants and access control**. Deliverable: a report with
findings classified by severity and a remediation pass.

## 2. Scope — contracts & SLOC

> SLOC below = raw lines in the source file (Solidity comments/blank included). Auditable SLOC
> (non-comment, non-blank) is ≈ **60–65%** of that.

| # | Contract | Path | Lines | Criticality |
|---|---|---|---:|---|
| 1 | **OrderExecutor** | `src/OrderExecutor.sol` | 383 | 🔴 Critical (moves user funds) |
| 2 | **AgentBondingCurve** | `src/launchpad/AgentBondingCurve.sol` | 229 | 🔴 Critical (holds USDC) |
| 3 | **AgentStakingVault** | `src/launchpad/AgentStakingVault.sol` | 153 | 🔴 Critical (principal + rewards) |
| 4 | **AgentFactory** | `src/launchpad/AgentFactory.sol` | 162 | 🟠 High (deploys the rest) |
| 5 | **GraduationModule** | `src/launchpad/GraduationModule.sol` | 109 | 🟠 High (liquidity) |
| 6 | **RevenueSplitter** | `src/launchpad/RevenueSplitter.sol` | 95 | 🟠 High (revenue) |
| 7 | **AgentToken** | `src/launchpad/AgentToken.sol` | 117 | 🟡 Medium |
| 8 | **LiquidityLocker** | `src/launchpad/LiquidityLocker.sol` | 83 | 🟡 Medium |
| 9 | **AgentRegistry** | `src/launchpad/AgentRegistry.sol` | 80 | 🟢 Low |
| | **TOTAL** | | **1411** | |

**Out of scope:** `src/launchpad/mocks/*` (test-only), the external DEX/router, the ERC-8004 / ERC-8183
registries (Arc/Circle), Permit2 (Uniswap, already audited), the off-chain keeper/API/UI.

## 3. Security checklist (per module)

### OrderExecutor
- [ ] Permit2 `permitWitnessTransferFrom` witness recomputation (tokenOut + minOut) — no bypass.
- [ ] `onlyKeeper` on execution; `onlyOwner` on `setKeeper`/`setAllowedTarget`/`setFee`.
- [ ] Swap-target whitelist enforced on both `executeOrder` and `executeDca`.
- [ ] Input-side fee: cap `feeBps <= 1000`; fee taken **before** the swap; `minOut` measured on the net.
- [ ] Leftover `tokenIn` refunded; no funds at rest; reentrancy guard; CEI order.
- [ ] EIP-1271 path (smart wallets) cannot be abused (digest bound to `verifyingContract`).

### AgentBondingCurve
- [ ] Constant-product invariant `k = x·y` holds across buy/sell; `x - x0 == realUsdc >= 0`.
- [ ] `sell` cannot drain the virtual reserve (`usdcOut < x` guard).
- [ ] Fee split to treasury/agent; no fee path lets a seller exceed the reserve.
- [ ] Graduation triggers exactly at `raisedUsdc >= graduationUsdc`; trading disabled after.
- [ ] `pullForGraduation` restricted to the graduation module and only after graduation.
- [ ] Sniper-window fee applied correctly; no way to bypass the launch fee.

### AgentStakingVault (ERC-4626-style)
- [ ] Reward-per-share accumulator cannot lose precision / over/underflow.
- [ ] `pendingRewards = balance*acc/1e18 - rewardDebt` never underflows; deposit/withdraw settle debt.
- [ ] Withdraw returns the principal exactly; rewards paid on withdraw/claim.
- [ ] `notifyReward` when `totalSupply == 0` parks in `pool` and is allocated to the first staker.
- [ ] No share inflation / donation attack (shares are 1:1 with the asset; `totalAssets = totalSupply`).
- [ ] `withdraw` allowance check (`owner`/approved spender) is correct.

### AgentFactory / GraduationModule / RevenueSplitter / AgentToken / LiquidityLocker
- [ ] Factory wires module + registry + ownership atomically; supply moved to the curve.
- [ ] GraduationModule: `graduate` idempotent (once per curve); LP locked for the beneficiary.
- [ ] RevenueSplitter: `stakerShareBps <= 10_000`; USDC approve/notify/transfer correct (no double-spend).
- [ ] AgentToken: no mint after init; limits auto-lift on graduation; owner/curve/module exempt.
- [ ] LiquidityLocker: withdrawal only after `unlockTime` and only by the beneficiary.

## 4. Attack vectors considered & mitigations

| Vector | Where | Mitigation |
|---|---|---|
| **Flash-loan / oracle manipulation** | Curve & graduation | The curve prices purely from **its own virtual reserves** (no external oracle). Graduation reads curve state only. No price is imported from a manipulable source. |
| **Reentrancy** | OrderExecutor, Vault, Module | `nonReentrant` (OrderExecutor); state updated **before** external calls (CEI) elsewhere; token transfers last. |
| **MEV / frontrunning** | Curve & orders | **Anti-sniper** window (higher fee) + **max wallet/tx**; user-signed **slippage** (`minOut`, `minUsdcOut`, `minRate`) enforced on-chain. |
| **Slippage bypass** | Curve / OrderExecutor | `minTokensOut`/`minUsdcOut` on the curve; Permit2 **witness** (`tokenOut,minOut`) recomputed on-chain; `minRate` for TWAP. |
| **Precision loss (ERC-4626 accumulator)** | Vault | Reward-per-share scaled `1e18`; debt settled on every interaction; proportional split tested exact (`test_proportional_noPrecisionLoss`). |
| **Fee creep / rug on fees** | OrderExecutor / token | `feeBps` hard cap **1000 (10%)**; token fees immutable at deploy; owner = Safe. |
| **Unauthorized execution** | OrderExecutor | `onlyKeeper`; whitelisted swap targets. |
| **LP rug** | Graduation | LP locked in `LiquidityLocker` for the creator (unlock `+365d`); `claimRefund`-style escape not applicable. |
| **Replay / cross-chain signature** | Orders | EIP-712 domain binds `chainId` + `verifyingContract`. |
| **Double graduation / double reward** | Module / Vault | `graduated` flag per curve; `rewardDebt` settlement prevents double-claim. |
| **Rounding exploit in split** | Splitter | Integer math; `toStakers + toTreasury == amount`. |
| **Denial of service via revert** | Keeper path | Per-order try/catch in the keeper; `EXPIRED` state; graduation is permissionless. |

## 5. Known limitations / trust assumptions (for the auditors)

- **Keeper is trusted** to build a valid route within the user-signed constraints (`tokenOut`,
  `minOut`/`minRate`, whitelisted target). It **cannot** move more than the signed amount, redirect
  the output, or fill below the signed minimum.
- **Owner = Safe** controls `setKeeper`, `setAllowedTarget`, `setFee`; this is intentional.
- **External DEX** on mainnet is TBD; the testnet uses a MockDEX. The graduation venue must be
  reviewed when chosen.
- **ERC-8183 / ERC-8004** are external, deployed by Arc/Circle — out of scope.
- **No upgradeability**: contracts are immutable; a bug requires redeploy + migration (documented).

## 6. Requested deliverables
1. Findings report (severity: Critical/High/Medium/Low/Info) with PoCs where applicable.
2. Verification of the invariants in §3.
3. Fuzz/invariant suggestions (curve invariant, vault accounting).
4. A remediation review pass after fixes.
