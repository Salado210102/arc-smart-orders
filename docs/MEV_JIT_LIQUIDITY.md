# MEV module 3 — JIT liquidity (Uniswap v3)

> **Draft / not audited / not deployed.** Just-In-Time liquidity: mint a 1-tick position right at the
> current price, let the target ("whale") swap pay it the bulk of the fee, then remove + burn — atomically.
> If the outcome doesn't beat capital + gas + `minProfit`, the whole tx reverts.

## Components

| # | File | What |
|---|---|---|
| 1 | `contracts/src/mev/ArcJITLiquidity.sol` | `executeJIT`: mint (NonfungiblePositionManager) → target swap → `decreaseLiquidity` → `collect` → `burn` → strict value/profit guard → return capital + profit to owner |
| 2 | `contracts/test/mev/ArcJITLiquidity.t.sol` | Mock pool/NFPM/swap: fees captured & paid to owner, mandatory `InsufficientProfit` revert, `TickOutOfRange`, `onlyOwner`, emergency withdraw |
| 3 | `bots/jit_liquidity_monitor.py` | Detects large swaps on the pool, computes the optimal tick range, simulates via `eth_call` + `estimate_gas`, Telegram + JSON history |

## Atomic flow (one call)

```
executeJIT(JITParams):
  1) require(currentTick in [tickLower, tickUpper))        (1-tick JIT)  else TickOutOfRange
  2) startValue = usdc + token1*price
  3) NFPM.mint(1-tick range at the current price)
  4) optional: call(swapTarget, swapData)                 (self-execute; else bundle it externally)
  5) NFPM.decreaseLiquidity(all) -> collect() -> burn()
  6) endValue = usdc + token1*price
     require(endValue >= startValue + gasCost + minProfit)  else InsufficientProfit
  7) transfer capital + net profit to owner (Safe)
```

## Valuation
`token1` is valued in USDC with `priceToken1InToken0` (USDC per whole token1, **6 decimals**):
`value = usdcBalance + token1Balance * price / 1e18`.

## Off-chain
`bots/jit_liquidity_monitor.py` watches the pool's `Swap` events; when a swap ≥ `MIN_SWAP_USD` is seen it
computes a 1-tick range around the current tick, simulates `executeJIT` (`eth_call`) and, if profitable,
sends it (`estimate_gas` first). Alerts to Telegram and logs `bots/jit_history.json`.

> **Reality check (honest):** true JIT requires minting *before* and burning *after* the target swap in the
> same block — on EVM that means a **bundler** (Flashbots-style) or the contract executing the swap itself
> (supported here via `swapTarget`/`swapData`). Arc runs a **permissioned validator set with no public
> mempool in the Ethereum sense**, so classic JIT is structurally limited — treat this as a design/backtest
> module until a bundler/ordering path is available.

## Run
```bash
cd contracts && forge test --match-contract ArcJITLiquidityTest -vvv
pip install -r bots/requirements.txt
cp bots/.env.example bots/.env && chmod 600 bots/.env
python bots/jit_liquidity_monitor.py
```
