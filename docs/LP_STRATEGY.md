# LP strategy — a passive "fee drip" on Arc (design)

> **Draft / design only.** Goal: a small, steady **fee drip** — "poco a poco se llena el saco" — using
> Arc's real DEX volume, instead of competing in the rare, red-ocean liquidation race.

## Why LP (the data)

| Metric (Arc, current) | Value |
|---|---|
| **DEX volume** | **~$66.8M / 24h** · ~$460M / 7d |
| Breakdown | **Uniswap v4 ~$40.6M**, **Uniswap v3 ~$23.3M**, Uniswap v2 ~$81k, GMGN ~$1.7M |
| Chain TVL | ~$397M |
| **Morpho liquidations** | ~**0 in 28h** (rare → not a reliable drip) |

**Takeaway:** there *is* swap volume → **fees are being paid**; a well-placed liquidity position can capture
a slice of it passively. Liquidations are too rare to be the main drip (keep the bot armed as a bonus).

## Options (least → most effort)

### Option D — Curated vault (lowest effort, no code)
Deposit USDC into a **curated yield vault** (e.g. **Arc EarnKit / Morpho Vaults**, Steakhouse-curated USDC/EURC
vaults). Passive yield, no active management, no smart-contract code to write. **Recommended first step** for
a "drip" with minimal risk and zero engineering.

### Option A — Single-range concentrated liquidity (recommended MVP if we want on-chain control)
- Mint **one** Uniswap v3/v4 position on a **high-volume, low-volatility pool** (e.g. **USDC/EURC**, fee 0.05%)
  with a **wide range** around spot (e.g. ±2–5%).
- **Collect fees** periodically to the **Safe**. Low maintenance; low impermanent loss on a stable pair.
- Non-custodial: the **Safe owns the NFT position**; a keeper only calls `collect` (and optionally rebalances).

### Option B — Active rebalancing agent (pro LP)
- A bot that **rebalances the range** as the price moves (mint new range, withdraw old, collect), maximizing
  time-in-range and fee capture — like professional LP managers.
- Higher fee capture, but more complexity, gas, and IL risk. **Later phase.**

## Recommended MVP — "wide single range" on a stable pair

```
Safe (owner) ── owns the NFT ──► Uniswap v3/v4 position (USDC/EURC, wide range)
                                    ▲
keeper (hot key) ── collect() ──────┘   → fees (USDC/EURC) drip into the Safe
   (optionally rebalance the range when price exits it)
```

**Contract sketch** (`ArcLiquidityManager.sol`, draft):
- `owner` = Safe; `keeper` = hot key (only `collect`/`rebalance`).
- `open(params)` — mint the position (owner-funded capital), store `tokenId`.
- `collect()` — collect fees to the Safe (keeper-callable).
- `rebalance(newLower, newUpper)` — decrease+burn the old position and mint a new range (owner-only or capped).
- `emergencyWithdraw()` — owner pulls the position back.

**Bot sketch** (`bots/lp_manager.py`):
- Reads pool price (slot0) + the position range; if price exits the range → alert (or rebalance if enabled).
- Periodically calls `collect()` and reports accrued fees to Telegram.
- Tracks fees over time in a JSON history (the "drip" ledger).

## Risks (honest)
- **Impermanent loss** — smallest on a **stable pair** (USDC/EURC); larger on volatile pairs.
- **Time out of range** — in a narrow range, price can leave it → no fees until rebalanced.
- **Competition** — JIT/MEV bots can capture fees around large swaps (Arc limits classic MEV, but not zero).
- **Thin pools** — some pools have volume but little liquidity; pick where **fees/IL** ratio is favorable.
- **Capital** — LP needs capital (unlike the flash-loan MEV modules). Returns are **not guaranteed**.

## Next steps
1. **Quick win:** deposit idle USDC into a **curated vault** (Option D) → immediate, code-free drip.
2. **MVP:** build `ArcLiquidityManager` + `bots/lp_manager.py` (Option A) on a USDC/EURC pool, owner=Safe.
3. **Later:** active rebalancing (Option B) once the MVP proves positive fees/IL.

> Prefer the **stable pair** and a **wide range** to keep IL tiny; treat LP as a **slow drip**, not a
> high-yield play. Ship with small capital first and measure over ≥2 weeks.
