# MEV module — capital-free liquidation keeper (Arc mainnet)

> **Draft / not audited / not deployed.** A self-contained module: liquidate insolvent borrowers with
> **flash-loaned USDC** (no upfront capital): if the trade isn't profitable, the whole tx reverts.

## Components

| # | File | What |
|---|---|---|
| 1 | `contracts/src/mev/ArcLiquidationKeeper.sol` | Flash loan → `liquidationCall` → Uniswap v3 swap → profit check → repay + send profit to the owner Safe |
| 2 | `contracts/test/mev/ArcLiquidationKeeper.t.sol` | Foundry tests with mocks (insolvent HF 0.95, profitable flow, mandatory revert, `onlyOwner`, emergency withdraw) |
| 3 | `bots/liquidation_monitor.py` | AsyncWeb3 monitor: scans HF, simulates via `eth_call`, Telegram alerts, optional auto-execution |

## Atomic flow (one tx)

```
1) flash-borrow USDC            (IFlashLoanProvider — Balancer-V2-style; on Arc point it at your provider/adapter)
2) pool.liquidationCall(user)   (Aave-v3 / Morpho-style; pulls the debt, sends collateral + bonus)
3) swap collateral -> USDC      (Uniswap v3 SwapRouter02.exactInputSingle)
4) require(usdc >= borrowed + fee + minProfit)   <-- else REVERT (no capital at risk)
5) repay the flash loan + send the net profit to the owner Safe
```

## Interfaces
- **Flash loan:** Balancer-V2 style `flashLoan(recipient, tokens, amounts, userData)` + `receiveFlashLoan`
  callback. Morpho Blue's `flashLoan(token, assets, data)` has a different shape — wrap it with a tiny
  adapter that implements the Balancer ABI (or adjust `IFlashLoanProvider`).
- **Lending pool:** any pool exposing `liquidationCall(collateral, debt, user, debtToCover, receiveAToken)`
  and `getUserAccountData(user)` (Aave v3 / Morpho markets).
- **Swap:** Uniswap v3 `SwapRouter02.exactInputSingle` (Arc mainnet `0x53BF6B0684Ec7eF91e1387Da3D1a1769bC5A6F77`).

## Run the tests
```bash
cd contracts
forge test --match-contract ArcLiquidationKeeperTest -vvv
```

## Run the monitor
```bash
pip install -r bots/requirements.txt
cp bots/.env.example bots/.env && chmod 600 bots/.env   # fill the addresses
python bots/liquidation_monitor.py
# monitor-only by default; set KEEPER_PK to enable sending
```

## Notes / risks
- The keeper's `owner` must be the hot key that calls `executeLiquidation` (or add a `keeper` role).
- Ensure the Uniswap v3 pool for collateral→USDC has enough liquidity, and set `SWAP_FEE` accordingly.
- Profit depends on the liquidation **bonus** minus the flash fee minus swap slippage.
