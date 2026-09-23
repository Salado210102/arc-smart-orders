# Venue integration — enabling mainnet smart-order fills

> Goal: switch `OrderExecutor` from dry-run to **live USDC⇄EURC fills on Arc mainnet** by wiring a
> whitelisted swap venue. Until then the keeper runs `DRY=1` (no funds move).

## Current state (mainnet 5042)

- `OrderExecutor` `0x9b3a990d1a31Ff5E01ddB8702e10F2529811FDb7` is live and **Safe-owned** (`owner = feeRecipient = Safe`), `keeper = B`, `feeBps = 30`.
- `allowedTargets(StableFX FxEscrow 0xe2E5F173…DFe6) = true`, **but StableFX is permissioned** (RFQ) and not available to independent builders → **no fillable venue yet**.
- Keeper runs on the VPS in **`DRY=1`** (validates + logs, does not broadcast).
- The swap leg is a **pluggable `swapTarget`** — the executor calls an owner-whitelisted contract with pre-built `swapData`.

## What a usable venue must provide

An **on-chain callable router** with a swap that:
1. pulls `tokenIn` from the executor (the executor pre-approves the exact **net**),
2. sends `tokenOut` to a **recipient we pass** (the order owner),
3. reverts if the output is below `minOut`.

> A pure RFQ/API (e.g. StableFX, App Kit Swap) does **not** qualify unless its settlement is a single on-chain call. Graduation additionally needs an AMM with `addLiquidity()` + an LP token (see §Graduation).

## Integration steps (when a venue exists)

### 1. Obtain the venue
Options, in order of preference:
- **A public AMM on Arc** (Uniswap-v2/v3-style router) — ideal (also unlocks graduation).
- **StableFX FxEscrow** if Circle grants access (testnet `MockStableRouter` already proves the flow).
- Any owner-whitelisted router whose `swap` sends output to a supplied recipient.

### 2. Whitelist it (via the Safe — `onlyOwner`)
```bash
# build calldata
cast calldata "setAllowedTarget(address,bool)" <VENUE> true
# execute through the Safe (signers A + C)
RPC=https://rpc.mainnet.arc.io \
SAFE=0x0FBFAF7069B45Dd9c16AdD8a04Bf556046EA7e93 \
SAFE_TO=0x9b3a990d1a31Ff5E01ddB8702e10F2529811FDb7 \
SAFE_DATA=0x<calldata> \
node ops/safe-exec.mjs
```

### 3. Configure the keeper and go live
In `keeper/.env`:
```ini
EXECUTOR=0x9b3a990d1a31Ff5E01ddB8702e10F2529811FDb7
ROUTER=<VENUE>
DRY=0
```
`pm2 restart arc-keeper`. The keeper builds `swapData` per order with `recipient = orderOwner` and `minOut` on the **net** (`gross − 0.30% fee`).

### 4. Fund the keeper hot wallet (gas in native USDC)
Already done once; top up as needed:
```bash
AMOUNT=1ether bash ops/fund-keeper.sh
```

### 5. First live fill (small) + verify
- Put one small signed order through `POST /v1/orders` (or the DApp Smart Swap on **mainnet**).
- Verify on the Arc explorer: `OrderExecuted` event, **fee `0.003 USDC` → Safe** for a 1 USDC fill, output to the user, `minOut` enforced.

## swapData shapes (per venue type)
- **Uniswap-v2-style router:** `swapExactTokensForTokens(amountIn, amountOutMin, path=[USDC,EURC], to=orderOwner, deadline)`.
- **StableFX FxEscrow:** FxEscrow's settle/swap entrypoint with the recipient set to `orderOwner`.
- The executor does **not** trust the calldata: it re-checks the owner's `tokenOut` balance delta ≥ `minOut` after the call.

## Graduation (separate but related)
Graduation is **gated** on mainnet (`factory.graduationModule = 0x0`). To enable once an AMM exists (via Safe):
1. `GraduationModule.setConfig(amm, locker, …)` (owner = Safe).
2. `AgentFactory.setGraduationModule(module)` (owner = Safe).
The module needs an AMM exposing `addLiquidity()` and an LP token to lock for 365 days.

## Tests to mirror locally
- `contracts/test/OrderExecutor.t.sol` + `MockStableRouter` cover pull → swap → minOut → fee.
- `contracts/test/LaunchpadGraduation.t.sol` covers graduation + LP lock (with `MockDEX`).

## Safety notes
- **Whitelist only** vetted targets; never whitelist a target that can move funds elsewhere.
- Keep `feeBps` small; the user's signed `minOut`/`minRate` is measured on the **net**, so a fee change can only cause a revert, never a silent under-fill.
- Fund B with just enough gas; the treasury is the Safe, not the keeper.
- Mainnet fills stay **off** until the venue, whitelist, keeper `ROUTER`/`DRY=0` and a small live test are all confirmed.
