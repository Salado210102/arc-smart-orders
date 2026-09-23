# Arc Testnet — deployments & E2E

**Chain ID** 5042002 · **RPC** https://rpc.testnet.arc.io · **Explorer** https://explorer.testnet.arc.io

## Contracts
| Contract | Address |
|---|---|
| **OrderExecutor** | [`0x9cb011A46A1127202Bc92F48f70Bf7010F1f9B6C`](https://explorer.testnet.arc.io/address/0x9cb011A46A1127202Bc92F48f70Bf7010F1f9B6C) |
| **MockStableRouter** (fixed-rate USDC→EURC, test-only) | [`0xcDeA0D5BcD78dB86D7A5f4E976976400a5b4dffc`](https://explorer.testnet.arc.io/address/0xcDeA0D5BcD78dB86D7A5f4E976976400a5b4dffc) |

- `owner` = `keeper` = `0x3df362854B3981b1367aC2DFa41533386628c977`
- Whitelisted `swapTarget` = MockStableRouter
- Permit2 = `0x000000000022D473030F116dDEE9F6B43aC78BA3` (canonical)
- USDC (ERC-20, 6 dec) = `0x3600000000000000000000000000000000000000`
- EURC (6 dec) = `0x89B50855Aa3bE2F677cD6303Cec089B5F319D72a`

## End-to-end run (2026-09-22)
| Step | Tx |
|---|---|
| Fund MockStableRouter with 10 EURC | [`0x035bdf2c65fa67a0c5748790a0c030cae18999b74ca93b1323c1477c79493184`](https://explorer.testnet.arc.io/tx/0x035bdf2c65fa67a0c5748790a0c030cae18999b74ca93b1323c1477c79493184) |
| Approve Permit2 for USDC (one-time) | [`0x9de71bd86f741476fcd48c54d3e3931e8aba35dad2ca82677c786395bd14f4fc`](https://explorer.testnet.arc.io/tx/0x9de71bd86f741476fcd48c54d3e3931e8aba35dad2ca82677c786395bd14f4fc) |
| **Fill LIMIT 1 USDC → minOut 0.92 EURC** | [`0x98f8459b8635037b64470eb92ace36446f88e5dcbf7232bb9b98dbfcc9c1ca2d`](https://explorer.testnet.arc.io/tx/0x98f8459b8635037b64470eb92ace36446f88e5dcbf7232bb9b98dbfcc9c1ca2d) |

**Result (verified on-chain):** user USDC 20 → 18.941775 · user EURC 10 → 10.92 · router USDC 0 → 1 · router EURC 10 → 9.08
(1 USDC swapped to 0.92 EURC; gas paid in USDC.)

### What the fill proves
- The keeper pulled the **exact** signed amount of USDC from the user via `Permit2.permitWitnessTransferFrom`,
  **enforcing the witness (`tokenOut=EURC`, `minOut`)** — the keeper cannot redirect or under-fill.
- Atomic: pull → swap (whitelisted target) → output to the user, in one transaction.

---

# Agentic E2E (ERC-8004 + ERC-8183) — 2026-09-22

**Roles (3 separate wallets):**
| Role | Address |
|---|---|
| **A — client / agent** (signs intent, creates job, funds escrow) | `0x3df362854B3981b1367aC2DFa41533386628c977` |
| **B — keeper / executor agent** (ERC-8004 identity, fills, submits) | `0x327fF705C1De5Ffd071bDF7E43069398507E50bC` |
| **C — validator / evaluator** (releases escrow, gives reputation) | `0xE34AA475d6F606671DB886fE9db3baFA428a1279` |

- **ERC-8004 agentId** (B): **896807**
- **ERC-8183 jobId**: **186648** → status **Completed**

## Tx tree (Arc testnet)
| Step | Tx |
|---|---|
| fund B (3 USDC) | `0xece7267e37563b8977621cb268f6acc445fb1f504a337af25c9d384cc9b9dc94` |
| fund C (3 USDC) | `0x9f9afac017ca61b63e3b2e9f51820b1e4c5b305b5fc3a8bed4576bcb0189faa7` |
| OrderExecutor `setKeeper(B)` (owner A) | `0x6e64fa37bf15d9cba126361d351e4a66a5d55e5b273ed6dc2e790ba3f936b723` |
| ERC-8004 `register` (B → agentId 896807) | `0xf6a2aefff5377404e81e5c7f55f3f72437c754c6d8fbbefc66388a055a36f8a5` |
| ERC-8183 `createJob(B, C)` (A) → job 186648 | `0xda8de4bd4a55a8400a24938c3be40cf42bba7117bb0972a57ddea02060e0b4cb` |
| ERC-8183 `setBudget(0.10 USDC)` (B) | `0xdb1e189547939ea00bb58a4e354ff1672aa13b20407b6fc84f9d1d0b7ea7301b` |
| ERC-8183 `approve+fund` escrow (A) | `0x33ec9c39bf9eaef8ad66dce3609173837d4491992d8491e441407eb6fdfd2fe0` |
| **OrderExecutor `executeOrder` fill** (B, keeper) | `0x4a1f3dd8b8ddcb8f73f5c2413f20e03ca086c22da08686c4860b40563efbc714` |
| ERC-8183 `submit(keccak256(fillTx))` (B) | `0x97019d04032f2edf6ce75012a53327bd632f653be58bb3c94d01aa0fdaee67a2` |
| ERC-8183 `complete` → escrow to B (C) | `0xafabb9745475091284065f464d096732d91f56ef31bfb85c161466350d158475` |
| ERC-8004 `giveFeedback` (C → agent 896807) | `0x7c171ad17e929392582edfc2ce07c562f418af1a86e4f326d21083a7679a24e3` |

**Verified on-chain:** `ownerOf(896807)` = B · B USDC 3 → **3.0878** (escrow released) · A USDC **11.8279**.
The link between the job and the fill is the **deliverable hash = keccak256(fillTxHash)** (non-hooked path, off-chain link).

---

# OrderExecutor v2 (input-side fee) — E2E — 2026-09-22

- **OrderExecutor v2**: [`0x5E9dCd592B37fda481Fc203756DA4D990cE438bA`](https://explorer.testnet.arc.io/address/0x5E9dCd592B37fda481Fc203756DA4D990cE438bA)
  - owner = A, keeper = B, **feeRecipient (treasury) = `0x59FbA0e7e3AAdfb766553D1c02f0b4ccC4D8d5C0`**, swapTarget = MockStableRouter
- **feeBps = 30 (0.30%)**, cap 1000 bps.

## Fee flow (job 186650, agent 896809)
Fill tx: [`0xb3bb5918340f2dad259f6a4b8aee122cd97ad7363e82b4f4225aa943b075da8c`](https://explorer.testnet.arc.io/tx/0xb3bb5918340f2dad259f6a4b8aee122cd97ad7363e82b4f4225aa943b075da8c) (status success)

| Movement (ERC-20 USDC/EURC, 6 dec) | From → To | Amount |
|---|---|---|
| Permit2 pull (gross) | A → executor | `1.000000` USDC |
| **Platform fee (0.30%)** | **executor → treasury T** | **`0.003000` USDC** |
| Swap input (**net**) | executor → router | `0.997000` USDC |
| Output | router → A | `0.917240` EURC |

`0.997 × 0.92 = 0.91724` ✓ · **treasury USDC = 0.003000** ✓

Other txs (v2 run): setKeeper `0x93b7ffea…2ebc` · setBudget `0x5e54d3c0…4728` · fund `0x33ccad2e…6a01` · submit `0xc1afd3f5…22b7` · complete `0x4fe16b20…df03` · reputation `0x96f3ba07…a27e`.

`feeBps` and `feeRecipient` are read live from the contract; `feeBps = 30`, `feeRecipient = 0x59FbA0e7…d5C0`.

---

# Agent Launchpad (P1) — 2026-09-22

| Contract | Address |
|---|---|
| **AgentFactory** | [`0x9960c81d15C7A3d5485C7a118f18Cf73ADC7320F`](https://explorer.testnet.arc.io/address/0x9960c81d15C7A3d5485C7a118f18Cf73ADC7320F) |
| Demo AgentToken (`DEMO`) | [`0xfB55528c953984218D8345ed62899bd53EFC141F`](https://explorer.testnet.arc.io/address/0xfB55528c953984218D8345ed62899bd53EFC141F) |
| Demo AgentBondingCurve | [`0x7a99BF1116cB67a9532f9be48cD5646BE6d8F110`](https://explorer.testnet.arc.io/address/0x7a99BF1116cB67a9532f9be48cD5646BE6d8F110) |

- **Deploy tx:** [`0x0bf463f506bcdcdd934ff673ae238c6e582196862a18e999c0e575b83c9f17f0`](https://explorer.testnet.arc.io/tx/0x0bf463f506bcdcdd934ff673ae238c6e582196862a18e999c0e575b83c9f17f0)
- **Launch (demo agent) tx:** [`0xf3f7c80051365401510b470255d34a89ca22edfb9faa9290c8082d803dbaa8fa`](https://explorer.testnet.arc.io/tx/0xf3f7c80051365401510b470255d34a89ca22edfb9faa9290c8082d803dbaa8fa)
- owner = `0x3df362854B3981b1367aC2DFa41533386628c977` · treasury = `0x59FbA0e7…d5C0` · identity = ERC-8004 `0x8004A818…BD9e`

**Verified on-chain:** `factory.owner()` = A · `token.owner()` = A · `token.curve()` = the curve · curve holds `1e24` tokens (full supply) · `price()` = `5000` (6-dec USDC per whole token = **0.005 USDC**) · `graduated()` = false.

> Curve params: `x0 = 5,000 USDC`, `y0 = 1,000,000` tokens, fee **1%** (50/50 protocol/agent), sniper **5%** for 30s, graduation `1,000,000 USDC`, maxWallet/maxTx `100,000` tokens.
> **Tests:** `test/Launchpad.t.sol` — 8/8 (buy/sell slippage, fee split, graduation, anti-sniper, max wallet/tx, access control). Full suite: **25/25**.

---

# Agent Launchpad (P2 — registry + graduation) — 2026-09-22

| Contract | Address |
|---|---|
| **AgentRegistry** | [`0x8a29Ca54c59e8853E5D15F9B4F42E1CC1650246c`](https://explorer.testnet.arc.io/address/0x8a29Ca54c59e8853E5D15F9B4F42E1CC1650246c) |
| **GraduationModule** | [`0x7D4c0013c770CA7b9ffA40D6a182c4d0fB0C8873`](https://explorer.testnet.arc.io/address/0x7D4c0013c770CA7b9ffA40D6a182c4d0fB0C8873) |
| **LiquidityLocker** | [`0x9A20D5f7856F936F7eEDBa0e46a6A839fbd70C57`](https://explorer.testnet.arc.io/address/0x9A20D5f7856F936F7eEDBa0e46a6A839fbd70C57) |
| MockDEX (LP, testnet AMM) | [`0x3f33d759B4755E6596EE922936d1ea394952748D`](https://explorer.testnet.arc.io/address/0x3f33d759B4755E6596EE922936d1ea394952748D) |
| **AgentFactory** (v2) | [`0x756DA207Bd7f15BAe616cB0cc10775e3bd1F3372`](https://explorer.testnet.arc.io/address/0x756DA207Bd7f15BAe616cB0cc10775e3bd1F3372) |
| Demo token | `0x5D6862CfE0b619BCE781c5fa88661e6CE28f889C` |
| Demo curve | `0xD5A04798D5caD6Df5aE1277DF178fbCa92396Ae2` |

Deploy txs: Locker `0x6eff9520…` · Registry `0x0eed1a11…` · MockDEX `0xbdb87563…` · Module `0xfca29b6b…` · Factory `0x01fb02a8…` · setFactory `0x0a8c5d72…` · launch `0xd01050eb…`.

**Verified on-chain:** `registry.count() == 1` · `registry.factory() == AgentFactory` · `curve.graduationModule() == GraduationModule` · `locker.lockCount() == 0` (not graduated yet).
**Full-cycle test:** `test/LaunchpadGraduation.t.sol` — buy past the threshold → `graduate()` → **LP locked in LiquidityLocker** for the creator (unlock `+365d`); withdraw reverts until unlock. **Full suite: 28/28.**

---

# Agent Launchpad (P3 — revenue split + staking) — 2026-09-22

| Contract | Address |
|---|---|
| **AgentStakingVault** (ERC-4626-style, asset = demo AgentToken) | [`0x8c58fee840EE397d59362B39A6Eb59F4EdcC1bD7`](https://explorer.testnet.arc.io/address/0x8c58fee840EE397d59362B39A6Eb59F4EdcC1bD7) |
| **RevenueSplitter** (70% stakers / 30% treasury) | [`0xFbfDa3712332347AF32ACeA10e981F36fb5734ED`](https://explorer.testnet.arc.io/address/0xFbfDa3712332347AF32ACeA10e981F36fb5734ED) |

Deploy txs: Vault `0x952803a5…` · Splitter `0x32b4d2bb…`. asset = demo token `0x5D6862Cf…889C`, owner = A, treasury = `0x59FbA0e7…d5C0`.

**Flow:** agent revenue (USDC) → `RevenueSplitter.distribute(amount)` → 70% to the vault (`notifyReward` → accrued pro-rata to stakers) + 30% to treasury. Stakers `deposit` the AgentToken and `claim()` USDC; `withdraw` returns the principal exactly.
**Tests:** `test/Staking.t.sol` — 5/5 (deposit, yield via splitter, proportional without precision loss, pool-before-stakers, second-yield accrual). **Full suite: 33/33.**

---

# `DeployMainnet.s.sol` DRY-RUN on Arc testnet — 2026-09-22

Ran the **exact mainnet script** (`CONFIRM_MAINNET=1`) on Arc testnet in **one execution** to validate the
sequence + ownership wiring.

| Contract | Address | tx |
|---|---|---|
| LiquidityLocker | `0xDf1592E1e6a6ABA13eF7c8821004a4011Bd90Aba` | `0x39f4158f…258c` |
| AgentRegistry | `0xAD5Bf8f7BA4A0e51092F4419CeF7D40308289e16` | `0x30bb61e9…9c1f` |
| GraduationModule | `0xBDF9BA264157EB634Dc65A61DfA512Fe5E3E1166` | `0xa9da5020…7169` |
| AgentFactory | `0x3d66d4abE251Aa2bC92B7842002Eb822469369A9` | `0x9ef9ceeb…7618` |
| OrderExecutor | `0x909102EAe94F964F33ea586aA8E215F170c1fde9` | `0xef09f9c9…cb985` |
| `registry.setFactory(factory)` | _(call)_ | `0x839b7b6d…390d` |

**Ownership/variable check (all ✅ in one run):** `factory.owner`=A · `factory.treasury`=T · `factory.registry`=AgentRegistry · `factory.graduationModule`=GraduationModule · `registry.factory`=AgentFactory · `module.dex`=MockDEX/`module.locker`=LiquidityLocker · `executor.owner`=A/`keeper`=B · `executor.feeBps`=30/`feeRecipient`=T · `allowedTargets(dex)`=true.

**Demo agent launched on the new factory:** token `0x23e904f3cba0a5a8b00612788650066e8cd49f99`, curve `0x69ce89460fbe341ee4ddc760e02874d17eae457d`, tx `0x26d80ccc86e218bdb6c895bface17b69f051432524bfc6f2022fa5f41abcaa81` · ERC-8004 identity minted · `registry.count()==1` · curve `price()==5000` (0.005 USDC).

**Per-agent vault+splitter:** `AgentStakingVault 0x5D5e48336589f3d9fdC4EABd986a526D7BF1FE6d` · `RevenueSplitter 0xad5ad6b09d52FA8BD5Acd7d0954da783e7a7b2dc`.

**UI:** repointed to the dry-run deployment and redeployed → **https://launchpad-neon-chi.vercel.app** (200; the Agents tab reads the new registry).

---

# Safe-owned `DeployMainnet` DRY-RUN (owner = Safe 2/2) — 2026-09-23

Re-ran the exact mainnet script on testnet but with **`LAUNCHPAD_OWNER` = `LAUNCHPAD_TREASURY` = `ORDERS_FEE_RECIPIENT` = the Safe 2/2 `0x0FBFAF7069B45Dd9c16AdD8a04Bf556046EA7e93`**, to validate the production ownership model (no EOA admin).

| Contract | Address |
|---|---|
| LiquidityLocker | `0x8410f54ad875B802135716F2BdFCb855478F33e7` |
| AgentRegistry | `0xD37Ca66d792927ED9220633d504D859E1B83aAf0` |
| GraduationModule | `0xf1255892220A02b11239118c3e78481DbB666b7e` |
| AgentFactory | `0x31De735997A7E430B6F11D619926509083dCD80A` |
| OrderExecutor | `0xbD66d0f7cDf01dF4281D90cbE6F24d5899a03a74` |
| **Safe `setFactory(factory)`** (execTransaction, signed A+C) | [`0xcbd367adcaa0a1dcfb54d549ad43e8c75092ebb3e7729821b037cd49e9a85ac7`](https://explorer.testnet.arc.io/tx/0xcbd367adcaa0a1dcfb54d549ad43e8c75092ebb3e7729821b037cd49e9a85ac7) |

**Verified on-chain:** `factory.owner`/`treasury` = Safe · `registry.owner` = Safe · `module.dex` = MockDEX · `module.locker` = Locker · `executor.owner`/`feeRecipient` = Safe, `keeper` = B, `feeBps` = 30, `allowedTargets(dex)` = true · **after** the Safe tx, `registry.factory` = AgentFactory.

> **Script change:** `DeployMainnet.s.sol` is now **Safe-aware** — when `owner` has code it does **not** call `setFactory` (which is `onlyOwner`); it prints the calldata the Safe must execute. Reusable executor: **`ops/safe-exec.mjs`** (signs with A + C, calls `execTransaction`).

---

# Soft-launch hardening DRY-RUN (dynamic addresses + guardrails) — 2026-09-23

`DeployMainnet.s.sol` now reads `USDC_MAINNET` / `DEX_ROUTER` / `ERC8004_REGISTRY` / `ERC8183_ESCROW` from
env and **reverts if a var is missing/zero or has no code**, and requires `owner`/`treasury`/`feeRecipient`
to be **contracts** (Safe). Re-ran on testnet (all post-deploy invariants passed; e.g. `locker/registry/
module/factory/exec.owner == Safe`, `exec.feeBps == 30`, `feeRecipient == Safe`).

| Contract | Address |
|---|---|
| LiquidityLocker | `0x0FCB434377cf1F3E4f2275282b4977E5e6CEC92a` |
| AgentRegistry | `0xD435e6aB455642fa8CEd73B296b48fCd28Bb2CBe` |
| GraduationModule | `0xbfBeF2cA0E494654517AE1966af94c618aF2362c` |
| AgentFactory | `0xE8C6E41A94941a1143d29a23E07EaD9D954578Dc` |
| OrderExecutor | `0xa47ecED9be785A64A2ac5819D6F509a6D8C423bE` |

**Guardrails verified (simulation reverts):** missing `CONFIRM_MAINNET` → revert · `DEX_ROUTER` = EOA →
`no contract code` · `LAUNCHPAD_OWNER` = EOA → `must be a contract (Safe)`.
**Soft-launch policy:** fee 30 bps · graduation cap **$10k/agent** (`SOFT_LAUNCH_MAX_GRADUATION_USDC`, applied
by the DApp default) · LP lock 365d · emergency brake = owner-only setters (no `Pausable` in contracts).

---

# Arc MAINNET deployment — 2026-09-23 🚀

Chain **5042** · RPC `https://rpc.mainnet.arc.io` · Explorer `https://explorer.arc.io`

| Contract | Address | Deploy tx |
|---|---|---|
| **Safe 2/2** (owner + treasury + feeRecipient) | `0x0FBFAF7069B45Dd9c16AdD8a04Bf556046EA7e93` | `0x…` (CreateSafe) |
| **LiquidityLocker** | `0x9cb011A46A1127202Bc92F48f70Bf7010F1f9B6C` | [`0xa8821a61…40d3`](https://explorer.arc.io/tx/0xa8821a6151dec8b5ec4735620d71d8f033b964d21c1a29248b5e3de4198340d3) |
| **AgentRegistry** | `0x8aE509565397C62a585c74aA44f7E3bFEab3Bb01` | [`0x725cda6b…1a47`](https://explorer.arc.io/tx/0x725cda6b6afd8a96043d92eec65db044a741e8e0379fc815bd506aa835e61a47) |
| **GraduationModule** | `0x1B8CA122DFd1100C0873A517b4875611Ed9De792` | [`0xab9e7cfb…6a9d`](https://explorer.arc.io/tx/0xab9e7cfb025e2672fa01a6e01efd9a7b6d086e19855849ec9d3f9a9a35ab6a9d) |
| **AgentFactory** | `0x4A80a4748A1d2AB37300780FcBC2FD28d2Ed393B` | [`0x0ead7a51…daae`](https://explorer.arc.io/tx/0x0ead7a51afc204a8d91f95acf8cf09ff9b5c0dd8109c092523d936051414daae) |
| **OrderExecutor** | `0x9b3a990d1a31Ff5E01ddB8702e10F2529811FDb7` | [`0xfebd8ce7…2d86`](https://explorer.arc.io/tx/0xfebd8ce7409551c5c2d41bb7f8ed40e1ecca464d0acd607fcd74764d91f12d86) |
| **Safe `setFactory(factory)`** | — | [`0x9ab16edb…bb14`](https://explorer.arc.io/tx/0x9ab16edba51a11f818ad8cf9f9cc07d2c5f86e20c95bef2201bbe24805bcbb14) |

**Config (verified on-chain):**
- `factory.owner`/`treasury` = Safe · `factory.registry` = AgentRegistry · **`factory.graduationModule` = 0x0 (gated V1)**.
- `registry.owner` = Safe · `registry.factory` = AgentFactory.
- `module.owner` = Safe · `module.dex` = StableFX FxEscrow `0xe2E5F173…DFe6` · `module.locker` = LiquidityLocker.
- `executor.owner` = Safe · `keeper` = `0x327f…50bC` · `feeBps` = 30 · `feeRecipient` = Safe · `allowedTargets(FxEscrow)` = true.
- `identity(8004)` = 0x0 (skip) · `escrow(8183)` = 0x0 (disabled).

**Safety notes:** deploy required the Safe to exist first (script correctly reverted until the Safe was
created on mainnet). Graduation is **gated**; enable later via Safe: `module.setConfig(<amm>,…)` +
`factory.setGraduationModule(module)`. ERC-8004 skipped until the registries ship on mainnet.

## Functional status (2026-09-23) — what works on Arc mainnet today

| Area | Status |
|---|---|
| **Agent Launchpad — launch** (`AgentFactory.launch`) | ✅ works (deploys token+curve, registers index) |
| **Bonding-curve buy/sell** | ✅ works (self-contained USDC↔token) |
| **Graduation** | ⏸️ gated — needs a real AMM (`fxEscrow` is RFQ, not an AMM) |
| **Smart-order fills** (`OrderExecutor`) | ⏸️ needs a swap venue (StableFX permissioned) — keeper runs `DRY=1` |
| **Staking / revenue vault** | ⏸️ per-agent; none deployed yet |

> ⚠️ **Freeze-risk fix (UI):** with graduation gated, a *reachable* graduation threshold would set
> `graduated=true` and permanently disable `buy`/`sell` on that curve. The DApp now launches with an
> **unreachable** `graduationUsdc` (1,000,000,000 USDC) so curve trading stays open indefinitely until a
> real venue is wired. (`AgentBondingCurve.buy/sell` revert once `graduated`.)

---

# OrderExecutor + MockStableRouter — fresh deploy + keeper E2E — 2026-09-23

Deployed **from the VPS (Ubuntu + Foundry)** because local Windows `forge` is blocked by WDAC.
Chain **5042002** (Arc Testnet).

| Contract | Address |
|---|---|
| **OrderExecutor** | `0xB19F1193BcC50c2aC0fdD9f1a28F95f7493f6Ee3` |
| **MockStableRouter** (USDC→EURC, test-only) | `0x228bea1763e9D52dF82714Cde250B12f1f175489` |

Config: owner = A, **keeper = B**, feeRecipient = A, swapTarget = router.

| Step | Tx |
|---|---|
| Fund router with **5 EURC** (from A) | `0xdf9db815a85e15dd3d71b219cf45117243a8a5988a2d373aa161895ae3178dbe` |
| Approve **Permit2** for USDC (from A) | `0xfe06dc9d8a9a61fdace594ec5fcd3b48f9278a10e1184b932c7afc38e2df94d1` |
| **Fill LIMIT 1 USDC → min 0.90 EURC** (keeper B, **DRY=0**) | `0xb075e97c8d7ce1693f750f8407e4b9785bec61a2011b289497069203dd6d71a8` |

**Verified on-chain:** fill tx success · A USDC `4.555472 → 3.552141` (−1 USDC −0.003 fee) ·
A EURC `8.674480 → 9.591720` (**+0.917240**, after funding the router with 5) ·
router EURC `5.0 → 4.082760`. The Permit2 **witness (`tokenOut=EURC`, `minOut`) was enforced**.

Keeper ran from the VPS (`/tmp/k`, port 8789, testnet RPC, keeper=B). Deploy key A was used on the VPS only.

## Testnet keeper — managed by PM2 (`arc-keeper-testnet`)

The ephemeral keeper was migrated to a **managed PM2 service**, isolated by port:

| | |
|---|---|
| **Process** | `arc-keeper-testnet` (PM2, autorestart + `pm2 save`) |
| **cwd / env** | `/var/www/arc-keeper/keeper-testnet/` (`.env`, chmod 600) |
| **Port** | `8789` (mainnet keeper stays on `8788`) |
| **Chain / RPC** | `5042002` · `https://rpc.testnet.arc.io` |
| **EXECUTOR / ROUTER** | `0xB19F1193BcC50c2aC0fdD9f1a28F95f7493f6Ee3` / `0x228bea1763e9D52dF82714Cde250B12f1f175489` |
| **Mode** | `DRY=0` (real testnet fills) · keeper = B |

```bash
pm2 list                              # arc-keeper (mainnet) + arc-keeper-testnet
pm2 logs arc-keeper-testnet
curl -s http://127.0.0.1:8789/health  # {"ok":true,"chainId":5042002,...}
```
Logs: `/var/www/arc-keeper/logs/arc-keeper-testnet.{out,err}.log`.

---

# Agent Launchpad — first MAINNET agent via the DApp (E2E) — 2026-09-23

Full DApp flow on **Arc mainnet (5042)**: connect wallet → create agent → buy on the bonding curve →
the `arc-alerts` Telegram bot fires automatically.

| | |
|---|---|
| **AgentToken** | `0xD81d4A4e6e91977cEf71b81259BF0a627e3E60De` |
| **AgentBondingCurve** | `0xf2da5A5F12E6a2f53C1Ee848988660044e94fd6F` |
| **Creator** | `0xA228372c79944e46c2972462f7849c66467e641b` (DApp user wallet) |
| **Buy** | 0.2 USDC → ≈ **39.6 tokens** (net raised `0.198 USDC`, `price = 5000`) |
| **Alert** | Telegram "🚀 New agent launched on Arc" delivered by `arc-alerts` (24/7) |

> `agentId = 0` because ERC-8004 is skipped on Arc mainnet (registry not deployed there yet), as designed.
> This is the first agent created through the production DApp on mainnet.






