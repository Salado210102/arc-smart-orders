# Cross-chain smart orders (`CrossChainOrderExecutor`)

> ⚠️ **Draft — not audited, not deployed.** This module is additive and **does not modify**
> `OrderExecutor.sol` (which is live/verified on Arc mainnet).

A **cross-chain** smart order lets a user sign an order on a **source** chain (e.g. Base Sepolia),
while the fill happens on **Arc**. The input stablecoin (USDC) is delivered to the executor on Arc by
an interop / CCTP message, and the swap runs **atomically on arrival**, paying the output to the user's
wallet on Arc.

```
   SOURCE CHAIN (e.g. Base Sepolia)                 ARC (destination)
   ───────────────────────────────                  ─────────────────
   user signs CrossChainIntent ──► bridge/interop ──► CrossChainOrderExecutor (holds USDC)
        (EIP-712)                    (CCTP msg)              │  keeper.executeCrossChain(...)
                                                             ├─ verify source + destination chainId
                                                             ├─ verify signature (ECDSA / EIP-1271)
                                                             ├─ mark intent single-use (nonce)
                                                             ├─ retain 0.30% input-side fee
                                                             ├─ approve whitelisted swapTarget (net)
                                                             ├─ call swapData (output → owner)
                                                             └─ enforce minOut on the NET
```

## Why not Permit2

Permit2 signatures are **chain-bound**: the Permit2 domain includes `chainId`, so a signature made on
the source chain does **not** validate against Arc's Permit2. Instead the order is a signed
**`CrossChainIntent`**, and the funds are delivered to the executor by the bridge (no cross-chain pull).

## EIP-712 domain & intent

The domain is the **standard 4-field domain** so viem and wallets can sign it:

```
EIP712Domain(string name, string version, uint256 chainId, address verifyingContract)
```

- `name` = `"ArcCrossChainOrders"`, `version` = `"1"`
- `chainId` = **destination** chain (the chain where the executor lives)
- `verifyingContract` = the `CrossChainOrderExecutor` address

The signed intent commits **everything** the fill must satisfy:

```
CrossChainIntent(address owner, address tokenIn, address tokenOut, uint256 amountIn,
                 uint256 minOut, uint256 sourceChainId, uint256 destinationChainId,
                 uint256 nonce, uint256 deadline)
```

## Anti-replay

Three independent guards:

1. **Domain `chainId` = destination** → a signature can't be replayed on another chain.
2. **`sourceChainId` + `destinationChainId` in the intent**, both checked on execution
   (`sourceChainId` must equal the executor's configured origin; `destinationChainId` must equal
   `block.chainid`).
3. **Single-use nonce** → `usedIntent[intentHash]` is set on the first fill; a replay reverts
   `IntentUsed()`.

## Execution guarantees

- **onlyKeeper** (and, if configured, **onlyInterop**) can submit a fill.
- **Whitelisted `swapTarget`** only (defense in depth against a malicious keeper).
- **`minOut` is enforced on the NET** (after the input-side fee), measured by the **owner's** output-token
  balance delta — a keeper can never redirect the output or fill below the signed minimum.
- **Fee safety:** the 0.30% input-side fee is taken from the delivered `tokenIn` **before** the swap;
  raising the fee can never push a fill below the signer's `minOut` (it just reverts).
- **Reentrancy guard**; ECDSA (EOA) **and** EIP-1271 (smart wallets) signature verification.

## SDK / keeper helper

`keeper/src/crosschain-builder.ts`:

- `signCrossChainIntent(wallet, executor, intent)` — signs the intent (call on the source chain).
- `buildExecuteCrossChainData(intent, signature, swapTarget, swapData)` — encodes the keeper fill call.
- `crossChainDomain(executor, destinationChainId)` · `CROSS_CHAIN_TYPES` · `crossChainExecutorAbi`.

## Tests

`contracts/test/CrossChainOrderExecutor.t.sol` (6 tests):

- fills and **retains the input-side fee** (0.30%)
- rejects a **wrong source** chain id
- rejects a **wrong destination** chain id
- rejects a **replay** (single-use intent)
- rejects a **bad signature**
- rejects a **non-keeper** caller

```bash
cd contracts
forge test --match-contract CrossChainOrderExecutorTest -vvv
```

## Status

Draft, **not deployed**. It is ready to plug into a real interop/CCTP delivery + a whitelisted Arc swap
venue when both exist. Until then it runs in tests only.
