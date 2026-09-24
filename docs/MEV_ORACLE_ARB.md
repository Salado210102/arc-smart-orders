# MEV module 2 — oracle arbitrage (capital-free, Uniswap v3 flash loans)

> **Draft / not audited / not deployed.** Flash-borrow USDC from a Uniswap v3 pool, arbitrage a
> price misalignment (pool lagging the oracle), repay + keep the profit. A strict profit check makes the
> whole tx revert if the route isn't profitable — **no capital at risk**.

## Components

| # | File | What |
|---|---|---|
| 1 | `contracts/src/mev/ArcOracleArbitrage.sol` | `IUniswapV3FlashCallback`: `executeArbitrage` → `pool.flash` → swap route (`exactInput`) → strict profit check → repay + profit to owner Safe |
| 2 | `contracts/test/mev/ArcOracleArbitrage.t.sol` | Mock v3 pool + router: 1.5% discrepancy success, mandatory `InsufficientProfit` revert, `onlyOwner`, `emergencyWithdraw` |
| 3 | `bots/oracle_arb_monitor.py` | AsyncWeb3: reads pool vs oracle price, ternary-searches the **optimal input** via `eth_call`, simulates + `estimate_gas`, Telegram alerts + history |

## Atomic flow (one tx)

```
1) pool.flash(USDC)               Uniswap v3 flash loan (fee = pool fee, e.g. 0.05%)
2) uniswapV3FlashCallback:
     - swap USDC -> ... -> USDC   via SwapRouter02.exactInput (the misaligned multi-hop route)
     - require(received >= amountIn + flashFee + minProfit)   <-- else REVERT
     - repay the pool (amountIn + fee)
     - send net profit to owner (Safe)
```

## Key functions
- `executeArbitrage(ArbParams{flashPool, path, amountIn, minProfit}) returns (uint256 profit)`
  — returns the profit (used by the off-chain `eth_call` sizing search).
- `emergencyWithdraw(token, to)` · `setConfig` · `transferOwnership` — `onlyOwner`.
- The flash callback is `nonReentrant` (prevents nested flash loans).

## Off-chain sizing
`bots/oracle_arb_monitor.py` compares `pool.slot0` price vs the oracle (Pyth/Chainlink) in bps and, when
above `THRESHOLD_BPS`, ternary-searches `executeArbitrage` through `eth_call` to find the input that
maximises profit, then simulates + `estimate_gas` before sending.

## Run
```bash
cd contracts && forge test --match-contract ArcOracleArbitrageTest -vvv
pip install -r bots/requirements.txt
cp bots/.env.example bots/.env && chmod 600 bots/.env   # fill addresses
python bots/oracle_arb_monitor.py                       # monitor-only unless KEEPER_PK is set
```
