# Venue integration — enabling mainnet smart-order fills

> Goal: switch `OrderExecutor` from dry-run to **live USDC⇄EURC fills on Arc mainnet** by whitelisting
> an on-chain swap venue. **Update (2026-09-23): Arc now has a live venue — Uniswap v3 + v4 are deployed
> and there is a liquid USDC/EURC pool.** So the blocker is now just a Safe `setAllowedTarget` + keeper config.

## TL;DR — what to do to go live

1. **Whitelist Uniswap `SwapRouter02`** in the executor (via the Safe):
   `setAllowedTarget(0x53BF6B0684Ec7eF91e1387Da3D1a1769bC5A6F77, true)`
   calldata: `0xca1dd22e00000000000000000000000053bf6b0684ec7ef91e1387da3d1a1769bc5a6f770000000000000000000000000000000000000000000000000000000000000001`
2. Keeper: `ROUTER=0x53BF6B0684Ec7eF91e1387Da3D1a1769bC5A6F77`, `DRY=0` → `pm2 restart arc-keeper`.
3. Keep the keeper hot wallet funded with native USDC gas (already ~1 USDC).
4. Run one small order end-to-end and verify on the Arc explorer.

## Uniswap on Arc (mainnet 5042) — canonical addresses

Source: Uniswap `developers.uniswap.org/deployments.json` (+ UniswapX playbook). All verified to have code on Arc.

| Contract | Address |
|---|---|
| **SwapRouter02 (v3)** — recommended `swapTarget` | `0x53BF6B0684Ec7eF91e1387Da3D1a1769bC5A6F77` |
| **UniversalRouter (v4)** | `0x4fcA4a51Ab4F23A7447b3284fBd7D73289A89Fb1` |
| UniversalRouter v2.1.2 | `0x8702463e73f74d0b6765aBceb314Ef07aCb92650` |
| v4 PoolManager | `0x8366a39CC670B4001A1121B8F6A443A643e40951` |
| v4 PositionManager | `0x6049c9a0e26405C0985f9E3685C87d0aE917f82B` |
| v4 V4Quoter | `0x8Dc178eFB8111BB0973Dd9d722ebeFF267c98F94` |
| v4 StateView | `0xF3334192D15450CdD385c8B70e03f9A6bD9E673b` |
| v3 Factory | `0xf0db7b58379503491d857dB50AC9ece64c653918` |
| v3 QuoterV2 | `0x7DfD4F31be6814D2906BDE155c3e1B146EAc1468` |
| v2 Router02 | `0x1f7d7550B1b028f7571E69A784071F0205FD2EfA` |
| Permit2 (canonical) | `0x000000000022D473030F116dDEE9F6B43aC78BA3` |

## USDC/EURC liquidity (verified on-chain, 2026-09-23)

v3 pools (token0 = USDC `0x3600…0000`, token1 = EURC `0xbEf5…21c1`):

| Fee | Pool | Liquidity |
|---|---|---|
| 0.01% (100) | `0x7578d9136940c4E0d2551Fb053aea5f7DE030CFd` | 0 |
| **0.05% (500)** | **`0x6fd5F2fb831940DcD61A98c5B3aCB7D8C6f3bFc1`** | **776,457,545,063** ← use this |
| 0.30% (3000) | `0x88f97E21c423261244d6D661fBd569b2bd69539f` | 10,041,759,738 |
| 1.00% (10000) | `0x1BD75d68F648eC9C82f297c45B8ab9Ae6bB0F3f0` | 0 |

Implied price ≈ **0.876 EURC/USDC** (from `slot0.sqrtPriceX96 ≈ 7.43e28`).

## Swap call (the keeper builds `swapData`)

`SwapRouter02.exactInputSingle` (v3, single hop USDC→EURC, fee 500):

```solidity
struct ExactInputSingleParams {
    address tokenIn;            // USDC 0x3600…0000
    address tokenOut;           // EURC 0xbEf5…21c1
    uint24  fee;                // 500
    address recipient;          // = intent.owner  (the executor enforces the balance delta)
    uint256 amountIn;           // the NET (gross − 0.30% fee)
    uint256 amountOutMinimum;   // minOut
    uint160 sqrtPriceLimitX96;  // 0
}
```

The executor pre-approves the router for the **net** and, after the call, verifies that the **owner's EURC
balance increased by ≥ `minOut`** — so the keeper can never redirect the output or under-fill.

> (If you prefer the v4 UniversalRouter, use the `V4_SWAP` command with an exact-in-single action; more
> complex calldata, same guarantees. SwapRouter02 is the simplest live option.)

## Whitelist via the Safe (onlyOwner)

```bash
# Re-generate the calldata if needed:
cast calldata "setAllowedTarget(address,bool)" 0x53BF6B0684Ec7eF91e1387Da3D1a1769bC5A6F77 true
# -> 0xca1dd22e00000000000000000000000053bf6b0684ec7ef91e1387da3d1a1769bc5a6f770000000000000000000000000000000000000000000000000000000000000001

RPC=https://rpc.mainnet.arc.io \
SAFE=0x0FBFAF7069B45Dd9c16AdD8a04Bf556046EA7e93 \
SAFE_TO=0x9b3a990d1a31Ff5E01ddB8702e10F2529811FDb7 \
SAFE_DATA=0xca1dd22e00000000000000000000000053bf6b0684ec7ef91e1387da3d1a1769bc5a6f770000000000000000000000000000000000000000000000000000000000000001 \
node ops/safe-exec.mjs
```

Optional (for v4 later): whitelist `UniversalRouter` `0x4fcA4a51Ab4F23A7447b3284fBd7D73289A89Fb1` too.

## Keeper config

`keeper/.env`:
```ini
EXECUTOR=0x9b3a990d1a31Ff5E01ddB8702e10F2529811FDb7
ROUTER=0x53BF6B0684Ec7eF91e1387Da3D1a1769bC5A6F77
DRY=0
```
`pm2 restart arc-keeper`. Fund gas if low: `AMOUNT=1ether bash ops/fund-keeper.sh`.

## First live fill — verify

- Submit one small order (`POST /v1/orders` or the DApp Smart Swap on **mainnet**).
- Check the Arc explorer for: `OrderExecuted` event, the **0.30% fee → Safe** (0.003 USDC on a 1 USDC fill),
  EURC delivered to the owner, and `minOut` respected.

## Graduation — now unblocked too

Graduation was gated (`factory.graduationModule = 0x0`) pending an AMM. With Uniswap v3/v4 live on Arc,
the `GraduationModule` can seed a **USDC/agent-token** Uniswap pool and lock the LP. Enable via the Safe:
1. `GraduationModule.setConfig(<univ3-factory-or-v4-poolmanager>, locker, …)`.
2. `AgentFactory.setGraduationModule(module)`.
   (The module needs an AMM exposing `addLiquidity()` + an LP token; a small adapter may be required for v4.)

## Safety notes

- Whitelist **only** the vetted Uniswap routers; never a target that can move funds elsewhere.
- The user's signed `minOut`/`minRate` is measured on the **net**, so a fee change can only cause a revert.
- Start with a tiny mainnet fill before announcing; keep `feeBps = 30`.
- The keeper key stays hot/low-privilege; the treasury is the Safe.
