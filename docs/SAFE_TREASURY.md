# Mainnet treasury — Safe Multisig 2/2 on Arc

This guide creates the **Safe 2/2** that will be the `feeRecipient` (treasury) **and** `owner` of the
production `OrderExecutor` on **Arc mainnet**.

> **Verified:** the full Safe v1.4.1 stack is already deployed on Arc **mainnet (5042)** and
> **testnet (5042002)**. You do **not** need to deploy Safe contracts.

| Contract | Address (Arc) |
|---|---|
| SafeProxyFactory | `0x4e1DCf7AD4e460CfD30791CCC4F9c8a4f820ec67` |
| Safe singleton (v1.4.1) | `0x41675C099F32341bf84BFc5382aF534df5C7461a` |
| CompatibilityFallbackHandler | `0xfd0732Dc9E303f09fCEf3a7388Ad10A83459Ec99` |
| MultiSendCallOnly | `0x9641d764fc13c8B624c04430C7356C1C7C8102e2` |

---

## Status (recorded) — 2026-09-22

| Field | Value |
|---|---|
| **Safe address (2/2)** | `0x0FBFAF7069B45Dd9c16AdD8a04Bf556046EA7e93` |
| Owners | `0x3df362854B3981b1367aC2DFa41533386628c977` (A · deployer) · `0xE34AA475d6F606671DB886fE9db3baFA428a1279` (C · validator) |
| Threshold | 2 · Safe **v1.4.1** |
| Salt nonce | 0 |
| Testnet | ✅ created & verified on **Arc testnet** (`getThreshold=2`, `getOwners=[A,C]`) |
| Mainnet | ⏳ **deterministic → same address** once the deployer is funded (see below) |

> The CREATE2 address depends only on the ProxyFactory, the `setup` initializer and the salt — identical
> on testnet and mainnet — so the **mainnet Safe will be `0x0FBFAF…7e93`**.
>
> **Mainnet blocker:** the deployer keys currently hold **0 USDC** on Arc mainnet, so the Safe cannot be
> broadcast yet. Fund `0x3df362854B3981b1367aC2DFa41533386628c977` with mainnet USDC, then:
> ```bash
> cd contracts
> SAFE_OWNER_1=0x3df362854B3981b1367aC2DFa41533386628c977 \
> SAFE_OWNER_2=0xE34AA475d6F606671DB886fE9db3baFA428a1279 \
> forge script script/CreateSafe.s.sol --rpc-url https://rpc.mainnet.arc.io --broadcast
> ```

---

## Step 1 — Create the Safe 2/2

### Path A · Safe Web UI (if Arc is listed)
1. Go to **https://app.safe.global** and connect a wallet.
2. If **Arc** appears in the network selector → **Create new Safe**.
3. Add **2 owner** addresses, set **threshold = 2**, name it e.g. *BasePump/Arc Treasury*.
4. Deploy (pay gas in **USDC**). Note the **Safe address**.

> If Arc is **not** listed yet, use Path B.

### Path B · Foundry script (works today — no UI dependency)
```bash
cd contracts
export SAFE_OWNER_1=0xYourSigner1
export SAFE_OWNER_2=0xYourSigner2
forge script script/CreateSafe.s.sol \
  --rpc-url https://rpc.mainnet.arc.io --broadcast
# → prints: Safe 2/2: 0x…
```
The script calls `SafeProxyFactory.createProxyWithNonce(SINGLETON, setup(owners, 2, …), salt)` and
logs the new Safe address. Both owners must be able to sign on Arc (the Safe UI can *load* an
existing Safe by address + custom RPC; or manage it with `@safe-global/protocol-kit`).

---

## Step 2 — Fund the Safe (optional, for gas)
The Safe pays gas in **USDC** when executing. Send a small amount of testnet/mainnet **USDC** to the
Safe address so it can operate (its own txs are paid by the executing owner's account, so this is
mostly for flows where the Safe itself is the caller).

---

## Step 3 — Point the OrderExecutor at the Safe

Deploy `OrderExecutor` with:
- `owner` = **the Safe**
- `feeRecipient` = **the Safe**
- `keeper` = your keeper hot wallet

```bash
cd contracts
export EXECUTOR_OWNER=<SAFE_ADDRESS>
export EXECUTOR_KEEPER=<KEEPER_ADDRESS>
export EXECUTOR_FEE_RECIPIENT=<SAFE_ADDRESS>
export EXECUTOR_TARGET=<real swap venue>
forge script script/Deploy.s.sol --rpc-url https://rpc.mainnet.arc.io --broadcast
```

If the executor already exists, set the fee from the **owner (Safe)** — a multisig transaction:
```
setFee(30, <SAFE_ADDRESS>)   // 30 bps = 0.30%, cap 1000 (10%)
```

---

## Step 4 — Verify on-chain
```bash
cast call <EXECUTOR> 'feeBps()(uint256)'        --rpc-url https://rpc.mainnet.arc.io   # 30
cast call <EXECUTOR> 'feeRecipient()(address)'  --rpc-url https://rpc.mainnet.arc.io   # <SAFE>
cast call <EXECUTOR> 'owner()(address)'         --rpc-url https://rpc.mainnet.arc.io   # <SAFE>
```
Then every fill deposits `feeBps/10_000` of `tokenIn` (USDC/EURC) to the Safe. Confirm via the
`Transfer` logs of a fill tx.

---

## Security notes
- **`feeBps` cap is hard-coded at 1000 (10%)** in `setFee` — cannot be exceeded without a contract upgrade behind the Safe.
- **`onlyOwner`** (the Safe) controls `setFee`, `setAllowedTarget`, `setKeeper`; **`onlyKeeper`** executes.
- **Input-side fee** → stablecoin revenue, no market/slippage risk.
- **User protection:** the signed `minOut`/`minRate` is measured on the **net**, so a fee increase that would under-fill simply reverts.
- Keep the **keeper key** hot/low-privilege; keep the **Safe signers** cold and distinct.
- Mainnet checklist lives in [`REVENUE.md`](REVENUE.md) §3.3.
