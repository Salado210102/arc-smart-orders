# Mainnet Runbook — Arc (chainId 5042)

Step-by-step to take the Agent Launchpad + OrderExecutor live on **Arc mainnet**. Do every step in
order; verify after each.

> ⚠️ This is a **fund-bearing** deployment. Freeze the audited commit, get the Safe ready, and do a
> full **testnet dry-run of the exact same script** before mainnet.

---

## 0. Network parameters (Arc)

| Param | Value |
|---|---|
| Chain ID | `5042` |
| RPC | `https://rpc.mainnet.arc.io` |
| Explorer | `https://explorer.arc.io` |
| Native gas | **USDC** (18-dec accounting) |
| **USDC (ERC-20, 6 dec)** | `0x3600000000000000000000000000000000000000` |
| EURC (6 dec) | `0xbEf5f6d51CB62b58e6A8f77868681825C6fe21c1` |
| Permit2 | `0x000000000022D473030F116dDEE9F6B43aC78BA3` |
| ERC-8004 IdentityRegistry | `0x8004A818BFB912233c491871b3d84c89A494BD9e` |
| ERC-8004 ReputationRegistry | `0x8004B663056A597Dffe9eCcC1965A193B7388713` |
| ERC-8004 ValidationRegistry | `0x8004Cb1BF31DAf7788923b405b754f57acEB4272` |
| ERC-8183 AgenticCommerce | `0x0747EEf0706327138c69792bF28Cd525089e4583` |
| Safe ProxyFactory (v1.4.1) | `0x4e1DCf7AD4e460CfD30791CCC4F9c8a4f820ec67` |
| Safe singleton (v1.4.1) | `0x41675C099F32341bf84BFc5382aF534df5C7461a` |
| **DEX / graduation venue** | `TBD` — select before deploying (see §2.3) |

---

## 1. Safe 2/2 (owner + treasury)

Full guide: [`SAFE_TREASURY.md`](SAFE_TREASURY.md). Summary:

- [ ] Create a **Safe 2/2** on Arc mainnet (two distinct signers).
  ```bash
  cd contracts
  SAFE_OWNER_1=0x… SAFE_OWNER_2=0x… \
  forge script script/CreateSafe.s.sol --rpc-url https://rpc.mainnet.arc.io --broadcast
  ```
- [ ] Record the **Safe address** → this is `OWNER` **and** `TREASURY` (fee recipient).
- [ ] Fund the Safe with a little **USDC** for gas (its own txs).
- [ ] The **Safe owns everything**: OrderExecutor, AgentFactory, vaults, splitter, registry.

## 2. Pre-flight

- [ ] **Audit completed** and Critical/High findings fixed ([`AUDIT_SCOPE.md`](AUDIT_SCOPE.md)).
- [ ] **Testnet dry-run**: run the exact `DeployMainnet.s.sol` on Arc testnet and verify end-to-end.
- [ ] **Deterministic deployer** funded with enough **USDC** for gas.
- [ ] Confirm all the §0 addresses on chain with `cast code …` (non-empty).
- [ ] **DEX venue chosen** (§2.3) — a real AMM/router on Arc that supports `addLiquidity` and mints LP.

### 2.3 DEX venue (must be decided before deploy)
The `GraduationModule` needs an `IDEX` with `addLiquidity(tokenA, tokenB, amountA, amountB, to)` and
`lpToken()`. Until an Arc AMM is available this is the testnet `MockDEX`; **do not go to mainnet with
a mock**. Candidates to evaluate: Circle **App Kit Swap** router, **StableFX** `FxEscrow`, or a
Uniswap-v4-style pool if deployed on Arc.

## 3. Deploy (deterministic, sequential)

```bash
cd contracts
export CONFIRM_MAINNET=1                     # safety gate (script reverts without it)
export RPC=https://rpc.mainnet.arc.io
export LAUNCHPAD_OWNER=<SAFE_ADDRESS>
export LAUNCHPAD_TREASURY=<SAFE_ADDRESS>
export ORDERS_KEEPER=<KEEPER_EOA>
export DEX=<chosen DEX address>
forge script script/DeployMainnet.s.sol \
  --rpc-url $RPC --private-key $PK --broadcast --slow --verify
```

The script deploys **in order** (same as the audited testnet run):
1. `LiquidityLocker(owner)`
2. `AgentRegistry(owner)`
3. `GraduationModule(owner, USDC, DEX, Locker, lockSeconds)`
4. `AgentFactory(USDC, Identity, treasury, owner, Registry, Module)`
5. `AgentStakingVault` is **per agent** (deploy on demand) — and `RevenueSplitter` per agent.
6. `OrderExecutor(owner, keeper, swapTarget, feeRecipient)` — `swapTarget` = the DEX; `feeRecipient`
   = the agent's splitter per agent (or the treasury for the generic engine).
7. `registry.setFactory(factory)`

## 4. Verify source on the explorer

- [ ] Arc explorer is Blockscout-compatible. After `--verify`, confirm every contract shows
  **"Contract Source Code Verified"** at `https://explorer.arc.io/address/<addr>#code`.
- [ ] If `--verify` is unsupported by the Arc verifier, verify via the explorer UI (paste sources /
  standard-json input from `out/`), or `forge verify-contract <addr> <contract> --chain 5042 --verifier blockscout --verifier-url https://explorer.arc.io/api`.

## 5. Post-deploy checks (read on-chain)

```bash
cast call <FACTORY>  'owner()(address)'                 --rpc-url $RPC   # = Safe
cast call <FACTORY>  'registry()(address)'              --rpc-url $RPC   # = Registry
cast call <REGISTRY> 'factory()(address)'               --rpc-url $RPC   # = Factory
cast call <EXECUTOR> 'feeBps()(uint256)'                --rpc-url $RPC   # <= 1000
cast call <EXECUTOR> 'feeRecipient()(address)'          --rpc-url $RPC   # = treasury/splitter
cast call <EXECUTOR> 'keeper()(address)'                --rpc-url $RPC   # = keeper EOA
```
- [ ] `feeRecipient`/`owner` are the Safe (or an agent splitter).
- [ ] Swap targets whitelisted (`allowedTargets(dex) == true`).
- [ ] Do a **small live order** end-to-end and confirm the fill + the fee landing in the treasury.
- [ ] Do a **small agent launch** + a buy/sell on the curve + a graduation dry-run (if feasible).

## 6. Ops
- [ ] Keeper running 24/7 (systemd/pm2) with a low-privilege key ([`../keeper/.env.example`](../keeper/.env.example)).
- [ ] Monitoring: fee accrual, treasury balance, keeper gas (USDC), order failure rate.
- [ ] Publish `DEPLOYMENTS.md` (mainnet) and the audited commit hash.

## 7. Rollback / incident
- Contracts are **immutable**: a bug requires redeploy + migration. Keep the Safe able to
  `setKeeper`/`setAllowedTarget`/`setFee` and, in the worst case, pause by setting `feeBps = 0` or
  revoking targets. Document an incident channel and the Safe recovery steps.
