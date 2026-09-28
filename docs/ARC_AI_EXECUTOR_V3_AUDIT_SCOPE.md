# Audit Scope — ArcIntelExecutor V2 / V3 (pre-audit)

**Project:** Arc AI / SNIPER IA — non-custodial order executor (sessions + pool policy)
**Repo:** https://github.com/Salado210102/arc-smart-orders
**Network:** Arc (testnet `5042002`; mainnet `5042`)
**Frozen at:** git tag **`arc-intel-executor-v3-pre-audit`**
**Signed/off-chain modules included:** the **signer** (`execution/signer.py`) and the **custody**
(`execution/custody.py`) modules are **in scope** (they decrypt keys / submit txs).

---

## 1. Objective

Independent review of the **non-custodial** executor **V2/V3** that (a) turns one user-signed order into
one fill, and (b) lets a **scoped session key** place orders without a per-order user signature, all
against the Uniswap **v4 PoolManager**, with on-chain enforced `minOut` / `deadline` / single-use nonce /
session caps. Deliverable: findings by severity + remediation pass.

## 2. Scope

### 2.1 Contracts (Solidity 0.8.26)
| # | Contract | Path | Criticality |
|---|---|---|---|
| 1 | **ArcIntelExecutorV2** (sessions) | `arc-intel/executor/src/ArcIntelExecutorV2.sol` | 🔴 Critical |
| 2 | **ArcIntelExecutorV3** (sessions + pool policy) | `arc-intel/executor/src/ArcIntelExecutorV3.sol` | 🔴 Critical |
| 3 | **IArcIntel** (vendored interfaces) | `arc-intel/executor/src/interfaces/IArcIntel.sol` | 🔴 Critical (trust boundary) |

### 2.2 Off-chain (Python) — in scope
| # | Module | Path | Criticality |
|---|---|---|---|
| 4 | **signer** (único punto de descifrado) | `arc-intel/execution/signer.py` | 🔴 Critical (keys) |
| 5 | **custody** (firma/envío de txs) | `arc-intel/execution/custody.py` | 🔴 Critical |
| 6 | **eip712** (witness/permit) | `arc-intel/execution/eip712.py` | 🟠 High |
| 7 | **preorders** (payload de orden) | `arc-intel/execution/preorders.py` | 🟠 High |
| 8 | **sessions** (EIP-712 de sesión, cifrado) | `arc-intel/execution/sessions.py` | 🟠 High |

**Dependencies (external, NOT in scope):** Permit2 `0x000000000022D473030F116dDEE9F6B43aC78BA3` and the
Arc v4 **PoolManager** `0x8366a39CC670B4001A1121B8F6A443A643e40951`.
**Out of scope:** `test/*`, `script/*`, `src/testonly/*` (test-only).

## 3. Security checklist

- [x] **One intent → at most one fill**: `orderNonceUsed[user][nonce]` set before external calls;
      `cancelOrder` revokes.
- [x] **`minOut` enforced on-chain** on the recipient's balance delta.
- [x] **`deadline` enforced**; expired orders revert.
- [x] **v1 witness binds** `poolId, zeroForOne, minOut, recipient, orderNonce, deadline` (B2).
- [x] **Session scope on-chain**: `poolId`, `tokenIn`, `maxPerOrder`, `maxTotal`, `spent`, `minOutFloor`,
      `expiry`, **revocable**; `recipient == user`.
- [x] **Allowlist fail-closed**: V2 = `allowedPools`; V3 = `allowedPools` **o** `allowedHooks` (por
      launchpad) **o** `allowAllPools` (**solo testnet**, gate por `isTestnet`).
- [x] **`unlockCallback` only** callable by the PoolManager.
- [x] **Reentrancy** guard on both entrypoints; hostile hook contained.
- [x] **No custody at rest**: no `rescue`/`withdraw`.
- [x] **Admin bounded**: owner (Safe en mainnet) solo `setPaused` + policy.
- [x] **Invariantes (5000×100)**: `spent ≤ maxTotal`; sesión revocada/expirada no llena; `recipient ==
      user`; sesión solo toca su pool/token; nonce único; executor sin saldo; pause absoluto.
- [x] **Slither** V2/V3: sin High/Medium aplicables (ver `ARC_AI_EXECUTOR_V2V3_SLITHER_TRIAGE.md`).
- [x] **Domain separator** fork-safe (recomputa con `chainid`).

## 4. Attack vectors considered

| Vector | Where | Mitigation |
|---|---|---|
| Session key filtrada | sessions | Scope + topes on-chain; output a `user`; revocable; `maxTotal` al peor `minOutFloor`. |
| Keeper bajo-llena / redirige | executor | Witness + `minOut` on-chain; keeper solo censura. |
| Replay / doble fill | executor | Nonce único + permit noce; revert no consume nonce. |
| Cross-chain replay | Permit2/EIP-712 | Domino con `chainId` + verifyingContract; domain dinámico. |
| Hook no confiable | v4 `hooks` | `allowedPools` / `allowedHooks` (mainnet); `allowAllPools` solo testnet. |
| `allowAllPools` en mainnet | owner | **Bloqueado on-chain** (`setAllowAllPools` revierte si `!isTestnet`) + check en deploy. |
| Token malicioso | ERC20 | Pull atómico; output por delta; reverts propagan. |
| Reentrancy | executor | `nonReentrant`; `unlockCallback` gated. |
| `pause` abuso | owner | No ejecuta/redirige/embarga; solo bloquea fills nuevos. |

## 5. Manifest (SHA-256)

| Path | SHA-256 |
|---|---|
| `arc-intel/executor/src/ArcIntelExecutorV2.sol` | `c39a39eaebd9aae9d453f8e3dbb3d6cc3b8c827295d87d89d5128bc637fbfdd3` |
| `arc-intel/executor/src/ArcIntelExecutorV3.sol` | `830b2e43484a15f250111767cf3de7094bdc77dabe523e3ddd58cd848a946310` |
| `arc-intel/executor/src/interfaces/IArcIntel.sol` | `6c5704e7a1284029fed046df997140912ee725cca7507713e63252ce2aeb08f7` |
| `arc-intel/execution/signer.py` | `c03b1cddf728da2bad9761d96bbf2b6abcf9e5aa0d7195dfc6737d07bb205eb6` |
| `arc-intel/execution/custody.py` | `6ef1a29810c6589c2825d2dec423a71a11d8e48247ae0814e3dcc7e6bc12a39e` |
| `arc-intel/execution/eip712.py` | `930c2629818134e4d6cb30b1910fc24e973ad9830d8d16ee25746ec58e0e71d3` |
| `arc-intel/execution/preorders.py` | `fe32c61569e7c15cf9371cfc8c305e37030e16c99f9af83d588327ce435e41e6` |
| `arc-intel/execution/sessions.py` | `0f0541c38dd9ff1c07c9a25ff8e1a5d01512d3c3ed7531f434a2af92a042ba8e` |

## 6. Reproducción

```
cd arc-intel/executor && forge test        # unit + invariantes (5000×100)
```
