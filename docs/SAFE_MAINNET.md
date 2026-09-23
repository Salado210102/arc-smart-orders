# Safe Multisig on Arc **Mainnet** — verify, deploy & wire `feeRecipient`

Operational guide for the production **2/2 Safe** that owns and receives fees from
`OrderExecutor v2` on **Arc mainnet (5042)**.

> Companion doc (background + testnet): [`SAFE_TREASURY.md`](SAFE_TREASURY.md).
> Chain **5042** · RPC `https://rpc.mainnet.arc.io` · Explorer `https://explorer.arc.io`.
> Gas is paid in **USDC** (`0x3600…0000`, ERC-20, 6 dec).

---

## 0 · Production addresses (current)

| Role | Address |
|---|---|
| **Safe 2/2** (owner + feeRecipient) | `0x0FBFAF7069B45Dd9c16AdD8a04Bf556046EA7e93` |
| Owner 1 — **A** (deployer) | `0x3df362854B3981b1367aC2DFa41533386628c977` |
| Owner 2 — **C** (validator) | `0xE34AA475d6F606671DB886fE9db3baFA428a1279` |
| **OrderExecutor v2** | `0x9b3a990d1a31Ff5E01ddB8702e10F2529811FDb7` |
| Keeper (hot wallet **B**) | `0x327fF705C1De5Ffd071bDF7E43069398507E50bC` |
| USDC (ERC-20) | `0x3600000000000000000000000000000000000000` |
| EURC | `0xbEf5f6d51CB62b58e6A8f77868681825C6fe21c1` |

> ⚠️ **Checksum warning:** the executor is `0x9b3a990d1a31Ff5E01ddB8702e10F2529811FDb7`.
> Any other casing is a **different string**; always copy it verbatim.

Safe v1.4.1 stack (already deployed on Arc — **do not redeploy**):

| Contract | Address |
|---|---|
| SafeProxyFactory | `0x4e1DCf7AD4e460CfD30791CCC4F9c8a4f820ec67` |
| Safe singleton (v1.4.1) | `0x41675C099F32341bf84BFc5382aF534df5C7461a` |
| CompatibilityFallbackHandler | `0xfd0732Dc9E303f09fCEf3a7388Ad10A83459Ec99` |
| MultiSendCallOnly | `0x9641d764fc13c8B624c04430C7356C1C7C8102e2` |

---

## 1 · Verify the Safe on mainnet

The Safe address is **deterministic** (CREATE2 from the proxy factory + `setup` initializer + salt
nonce), so it is identical on testnet and mainnet. Confirm it is actually deployed and configured:

```bash
SAFE=0x0FBFAF7069B45Dd9c16AdD8a04Bf556046EA7e93
RPC=https://rpc.mainnet.arc.io

# 1) It has contract code (i.e. was actually broadcast on mainnet)
cast code $SAFE --rpc-url $RPC | head -c 20      # must NOT be 0x

# 2) Threshold = 2
cast call $SAFE "getThreshold()(uint256)" --rpc-url $RPC           # 2

# 3) Owners = [A, C]
cast call $SAFE "getOwners()(address[])" --rpc-url $RPC            # [A, C]

# 4) Nonce (number of executed Safe txs) + version
cast call $SAFE "nonce()(uint256)" --rpc-url $RPC                  # 0, 1, …
cast call $SAFE "VERSION()(string)" --rpc-url $RPC                 # optional
```

**Pass criteria:** `code != 0x`, `threshold == 2`, owners are exactly **A** and **C**.

> If `code == 0x`, the Safe is **not** on mainnet yet → go to §2.

---

## 2 · Deploy the Safe 2/2 (only if §1 failed)

`contracts/script/CreateSafe.s.sol` calls
`SafeProxyFactory.createProxyWithNonce(SINGLETON, setup(owners, 2, …), saltNonce)` and logs the address.
Owner **A** must hold mainnet USDC for gas.

```bash
cd contracts
export SAFE_OWNER_1=0x3df362854B3981b1367aC2DFa41533386628c977
export SAFE_OWNER_2=0xE34AA475d6F606671DB886fE9db3baFA428a1279
forge script script/CreateSafe.s.sol \
  --rpc-url https://rpc.mainnet.arc.io --broadcast
# → prints: Safe 2/2: 0x0FBFAF7069B45Dd9c16AdD8a04Bf556046EA7e93
```

Then re-run the §1 checks. (This repo already recorded the Safe as created on mainnet — treat §2 as the
idempotent fallback.)

### Fund the Safe
Send a small amount of mainnet **USDC** to the Safe so it can pay gas when it is the caller of a
multisig transaction. `onlyOwner` calls made **through** the Safe (`execTransaction`) are paid by the
executing owner (A) in USDC.

---

## 3 · Verify `OrderExecutor v2` points at the Safe

`OrderExecutor v2` on mainnet already sets `owner = feeRecipient = Safe` and `keeper = B`. Confirm:

```bash
EXEC=0x9b3a990d1a31Ff5E01ddB8702e10F2529811FDb7
RPC=https://rpc.mainnet.arc.io

cast call $EXEC "owner()(address)"        --rpc-url $RPC   # Safe  0x0FBFAF…7e93
cast call $EXEC "feeRecipient()(address)"  --rpc-url $RPC   # Safe  0x0FBFAF…7e93
cast call $EXEC "feeBps()(uint256)"        --rpc-url $RPC   # 30  (0.30%)
cast call $EXEC "keeper()(address)"        --rpc-url $RPC   # B  0x327f…50bC
```

**Pass criteria:** `owner == feeRecipient == Safe`, `feeBps == 30`, `keeper == B`.

---

## 4 · Set the Safe as `feeRecipient` (only if §3 differs)

`setFee(uint256 bps, address feeRecipient)` is **`onlyOwner`** → it must be executed **by the Safe**
(A + C both sign). Build the calldata, then run the Safe transaction with the reusable executor.

### 4.1 Build the calldata
```bash
RPC=https://rpc.mainnet.arc.io
SAFE=0x0FBFAF7069B45Dd9c16AdD8a04Bf556046EA7e93
EXEC=0x9b3a990d1a31Ff5E01ddB8702e10F2529811FDb7
cast calldata "setFee(uint256,address)" 30 $SAFE
# → 0x… (use the output as SAFE_DATA)
```

### 4.2 Execute via the Safe (signers A + C)
`ops/safe-exec.mjs` signs the `SafeTx` EIP-712 payload with **A** and **C** (sorted by signer address),
then calls `execTransaction`.

```powershell
$env:RPC       = "https://rpc.mainnet.arc.io"
$env:SAFE      = "0x0FBFAF7069B45Dd9c16AdD8a04Bf556046EA7e93"
$env:SAFE_TO   = "0x9b3a990d1a31Ff5E01ddB8702e10F2529811FDb7"   # the executor
$env:SAFE_DATA = "0x<calldata from 4.1>"
node ops/safe-exec.mjs
# → execTransaction: 0x…  status: success
```

Signer key files default to the two A/C JSONs in `.secrets/`; override with
`SAFE_SIGNER_1` / `SAFE_SIGNER_2` (paths). **Never commit keys.**

> Same flow is used for any other `onlyOwner` call on the executor or launchpad
> (`setKeeper`, `setAllowedTarget`, `AgentRegistry.setFactory`, …).

---

## 5 · Verify the fee actually reaches the Safe

After the next real fill, the executor takes `feeBps / 10_000` of `tokenIn` **before** the swap and
sends it to `feeRecipient`. To confirm a fill paid the Safe, read the `Transfer` logs of the fill tx:

```bash
# feeRecipient USDC balance over time (grows with every USDC-input fill)
cast call 0x3600000000000000000000000000000000000000 \
  "balanceOf(address)(uint256)" 0x0FBFAF7069B45Dd9c16AdD8a04Bf556046EA7e93 \
  --rpc-url https://rpc.mainnet.arc.io
```

For a `1.000000 USDC` gross fill at `feeBps = 30`, expect **`0.003000 USDC`** to the Safe, the **net**
`0.997000` to be swapped, and the output to go to the user. (Reference numbers:
[`DEPLOYMENTS.md`](../DEPLOYMENTS.md) → "OrderExecutor v2 (input-side fee)".)

Realtime monitoring of the treasury + fills: **`ops/keeper-metrics-bot.mjs`**.

---

## 6 · Security notes

- `feeBps` is hard-capped at **1000 bps (10%)** in `setFee` — it cannot be raised further without a
  contract change behind the Safe.
- **`onlyOwner`** (Safe) controls `setFee` / `setAllowedTarget` / `setKeeper`; **`onlyKeeper`** executes
  fills. The user's signed `minOut` / `minRate` is measured on the **net**, so a fee change can never
  silently under-fill (it reverts).
- Keep the **keeper key (B) hot and low-privilege**; keep the **Safe signers (A, C) cold and distinct**.
  A and C should live on different machines/seed phrases.
- To rotate the treasury: `setFee(30, <newRecipient>)` via the Safe — no redeploy needed.

## 7 · Mainnet checklist

- [ ] `cast code` on the Safe ≠ `0x`
- [ ] `getThreshold() == 2`, `getOwners() == [A, C]`
- [ ] `executor.owner == executor.feeRecipient == Safe`
- [ ] `executor.feeBps == 30`, `executor.keeper == B`
- [ ] Safe funded with USDC for gas
- [ ] `ops/keeper-metrics-bot.mjs` prints treasury + fill metrics
- [ ] Verified a real fill's `Transfer` to the Safe
