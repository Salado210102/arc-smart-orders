# Audit Package — Arc Smart Orders + Agent Launchpad

> Everything a reviewer needs to reproduce the build, run the tests, and verify the deployment.
> **Frozen at git tag `pre-audit-v2`** (`git rev-parse pre-audit-v2`).

| | |
|---|---|
| Repo (MIT) | https://github.com/Salado210102/arc-smart-orders |
| Scope | [`AUDIT_SCOPE.md`](AUDIT_SCOPE.md) — **9 contracts / 1,411 SLOC** |
| Network | Arc testnet `5042002` (manager: mainnet `5042`) |
| Live UI | https://arc.basepump.dev |
| Treasury | Safe 2/2 `0x0FBFAF7069B45Dd9c16AdD8a04Bf556046EA7e93` |

---

## 1. Reproducible / deterministic build

`contracts/foundry.toml`:

```toml
solc = "0.8.26"
auto_detect_solc = false
evm_version = "cancun"
optimizer = true
optimizer_runs = 200
via_ir = true
bytecode_hash = "none"   # deterministic bytecode (no metadata hash) -> reproducible addresses
```

```bash
cd contracts
forge build          # compile
forge test           # 34/34 unit + integration (the mainnet-fork test is skipped unless env is set)
```

## 2. Contract sizes (Spurious Dragon limit = 24,576 B runtime)

| Contract | Runtime (B) | Margin (B) |
|---|---:|---:|
| AgentFactory | 12,971 | 11,605 |
| OrderExecutor | 5,698 | 18,878 |
| AgentBondingCurve | 5,008 | 19,568 |
| AgentStakingVault | 3,598 | 20,978 |
| AgentToken | 2,696 | 21,880 |
| GraduationModule | 2,665 | 21,911 |
| AgentRegistry | 2,402 | 22,174 |
| RevenueSplitter | 2,102 | 22,474 |
| LiquidityLocker | 1,648 | 22,928 |

All contracts are **well under** the limit (largest margin 11.6 kB). Verify with `forge build --sizes`.

## 3. Test evidence

- **34/34** passing: orders 17 · launchpad 8 · graduation 3 · staking 5 · revenue-wiring 1.
- Mainnet-fork rehearsal: `test/DeployMainnetFork.t.sol` (skipped by default; see §4).
- Fork test of the Permit2 witness against the **real** Permit2: `test/Permit2WitnessFork.t.sol`.

## 4. Pre-audit mainnet-fork dry-run

`script/DeployMainnet.s.sol` reads every external address from env and **fails fast**:

| Check | Result |
|---|---|
| Real Arc-mainnet ERC-8004 (`0x8004A818…`) has no code yet | ✅ reverts `ERC8004_REGISTRY: no contract code at address` |
| `CONFIRM_MAINNET` missing | ✅ reverts `set CONFIRM_MAINNET=1` |
| `DEX_ROUTER` points at an EOA | ✅ reverts `no contract code at address` |
| `LAUNCHPAD_OWNER` is an EOA | ✅ reverts `must be a contract (Safe)` |
| Full deploy on an **Arc-mainnet fork** (infra simulated) | ✅ **all post-deploy invariants pass** |

Rehearsal (env in `.env.example`):
```bash
CONFIRM_MAINNET=1 USDC_MAINNET=0x3600…0000 DEX_ROUTER=0x…D3 \
ERC8004_REGISTRY=0x8004A818…BD9e ERC8183_ESCROW=0x0747…4583 \
ORDERS_KEEPER=0x327f…50bC LAUNCHPAD_OWNER=0x0FBFAF…7e93 \
forge test --match-test test_FullDeployOnFork -vv
```
The run also confirms the **deterministic Safe address** on a mainnet fork and prints the Safe-only
follow-up `registry.setFactory(factory)` (executed via [`../ops/safe-exec.mjs`](../ops/safe-exec.mjs)).

## 5. Deployment reference (Arc testnet) & treasury

| Contract | Address |
|---|---|
| OrderExecutor | `0x909102EAe94F964F33ea586aA8E215F170c1fde9` |
| AgentFactory | `0x3d66d4abE251Aa2bC92B7842002Eb822469369A9` |
| AgentRegistry | `0xAD5Bf8f7BA4A0e51092F4419CeF7D40308289e16` |
| GraduationModule | `0xBDF9BA264157EB634Dc65A61DfA512Fe5E3E1166` |
| LiquidityLocker | `0xDf1592E1e6a6ABA13eF7c8821004a4011Bd90Aba` |
| AgentStakingVault (demo) | `0x5D5e48336589f3d9fdC4EABd986a526D7BF1FE6d` |
| RevenueSplitter (demo) | `0xad5ad6b09d52FA8BD5Acd7d0954da783e7a7b2dc` |
| **Safe 2/2** (owner/treasury) | `0x0FBFAF7069B45Dd9c16AdD8a04Bf556046EA7e93` |

Full history + tx hashes: [`../DEPLOYMENTS.md`](../DEPLOYMENTS.md).

## 6. Out of scope / known limitations (declare to reviewers)

- **No `Pausable`.** Emergency control = owner-only setters (Safe): `setAllowedTarget(dex,false)`,
  `setGraduationModule(0)`, `setIdentity(0)`, `setKeeper`. See `MAINNET_RUNBOOK.md` §3.2.
- **ERC-8004 / ERC-8183 are not deployed on Arc mainnet yet** → the launchpad cannot go live there until
  they exist (mainnet deploy intentionally reverts). USDC, Permit2 and the Safe stack *are* on mainnet.
- **DEX venue TBD** — `swapTarget`/`dex` are pluggable; testnet uses `MockDEX`. Verified on Arc mainnet:
  **StableFX `FxEscrow` `0xe2E5F173…DFe6`** (permissioned RFQ, request via `sales@circle.com`) for the order
  engine; **no public AMM** yet for graduation. Reviewers should treat the `IDEX` interface as the boundary.
- **Graduation is GATED in V1** — deployed with `GRADUATION_GATED=1` → `factory.graduationModule = 0`, so
  graduation is disabled and raised USDC stays in each curve until the Safe enables a real AMM pool. The
  `GraduationModule`/`LiquidityLocker` code ships deployed-but-inactive (still in audit scope).
- **Graduation cap ($10k)** is a **DApp policy**, not an on-chain factory cap (deliberately: no bytecode
  change pre-audit). `AgentFactory.launch` accepts `graduationUsdc` per agent.
- `forge` **lint warnings** are present (informational: `missing-zero-check`, `reentrancy-events`,
  `erc20-unchecked-transfer`, `block-timestamp`); none is a failing build. Enumerate in review.

## 7. Reviewer quickstart

```bash
git clone https://github.com/Salado210102/arc-smart-orders && cd arc-smart-orders/contracts
git checkout pre-audit-v2
forge build --sizes
forge test -vvv
# start here: docs/AUDIT_SCOPE.md (threat model §3–4), then src/*.sol
```

## 8. Pre-submission checklist

- [x] Frozen commit + tag `pre-audit-v2`
- [x] Deterministic compiler config committed
- [x] `forge build --sizes` — all < 24,576 B
- [x] `forge test` — 34/34
- [x] Mainnet-fork rehearsal passes; fail-fast guardrails verified
- [x] Scope / threat model (`AUDIT_SCOPE.md`)
- [x] Deployment record (`DEPLOYMENTS.md`) + Safe address
- [ ] Push tag/repo to GitHub (public)
- [ ] Attach this package to the audit application (UFSF / Circle)
