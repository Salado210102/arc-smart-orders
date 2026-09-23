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




