# Revenue Model — Arc Smart Orders

> Dual monetization: an **input-side platform fee** (protocol revenue) + a **keeper execution
> fee** (operator revenue, ERC-8183). Fees are collected in **stablecoins (USDC/EURC)**, on-chain,
> with **zero slippage exposure**.

---

## 1. Dual monetization model

### 1.1 Platform Fee — input-side (protocol revenue)
- **Rate:** `feeBps = 30` (**0.30%**) by default.
- **Where:** `OrderExecutor` (v2) takes the fee from **`tokenIn`** *before* the swap.
- **Currency:** the input token of the pair — **USDC / EURC** (both stablecoins).
- **Recipient:** `feeRecipient` → **the treasury** (mainnet: a **Safe multisig 2/2**).
- **Config:** `setFee(bps, recipient) onlyOwner`, hard cap **1000 bps (10%)** — see §3.
- **Why input-side:** the fee is fixed in the token pulled, so it carries **no slippage/PnL risk**,
  and it simplifies the Permit2 witness verification (the signed `minOut`/`minRate` is measured on
  the **net** amount). A fee change can never silently under-fill a user — it reverts instead.

### 1.2 Keeper Execution Fee — ERC-8183 (operator revenue)
- **Model:** per-task budget set by the client/agent via `setBudget(jobId, amount)` on the
  **AgenticCommerce** contract (ERC-8183), paid from escrow to the **keeper** on `complete`.
- **Purpose:** covers the keeper's operating cost (gas ≈ \$0.001/tx on Arc) **+ execution margin**.
- **Currency:** USDC.
- **Scales with:** number of executed jobs × per-job fee (independent of notional size).

> Two distinct rails: **(a)** protocol fee → treasury (scales with **volume**); **(b)** keeper fee →
> keeper wallet (scales with **number of tasks**).

**Verified on Arc testnet:** fill `0xb3bb5918…da8c` → treasury received exactly **0.003 USDC** on a
1.00 USDC order (0.30%), and the router received the **0.997 USDC** net.

---

## 2. Quantitative revenue projection

### 2.1 Formula
$$
\text{Fee} = \text{Volume}_{\text{gross}} \times \frac{\text{feeBps}}{10{,}000}
\qquad\text{e.g.}\qquad 30\text{ bps} \Rightarrow \text{Fee} = \text{Volume} \times 0.003
$$

Per fill: `fee_i = gross_i × 0.003` — collected in `tokenIn` (stablecoin), **libre de slippage**.

### 2.2 Protocol revenue vs. daily gross volume (feeBps = 30)

| Daily gross volume | Fee / day | Fee / month (~30d) | Fee / year (~365d) |
|---:|---:|---:|---:|
| **\$100,000** | \$300 | \$9,000 | \$109,500 |
| **\$1,000,000** | \$3,000 | \$90,000 | \$1,095,000 |
| **\$10,000,000** | \$30,000 | \$900,000 | \$10,950,000 |

**Monthly volume variants:**

| Monthly gross volume | Fee / month | Fee / year |
|---:|---:|---:|
| \$3,000,000 | \$9,000 | \$109,500 |
| \$30,000,000 | \$90,000 | \$1,095,000 |
| \$300,000,000 | \$900,000 | \$10,950,000 |

### 2.3 Sensitivity to the fee rate (at \$1M/day)

| feeBps | Rate | Fee / day | Fee / month | Fee / year |
|---:|---:|---:|---:|---:|
| 10 | 0.10% | \$1,000 | \$30,000 | \$365,000 |
| **30** | **0.30%** | **\$3,000** | **\$90,000** | **\$1,095,000** |
| 50 | 0.50% | \$5,000 | \$150,000 | \$1,825,000 |

### 2.4 Keeper execution fee (ERC-8183) — illustrative
Per-job fee \$0.05–\$0.50 × jobs/day:

| Jobs / day | @ \$0.05 | @ \$0.20 | @ \$0.50 |
|---:|---:|---:|---:|
| 100 | \$5 /day | \$20 /day | \$50 /day |
| 1,000 | \$50 /day | \$200 /day | \$500 /day |
| 10,000 | \$500 /day | \$2,000 /day | \$5,000 /day |

### 2.5 Combined (illustrative, \$1M/day volume + 1,000 jobs/day)
- Protocol fee: \$90,000/month.
- Keeper fee (agent-run at \$0.20/job): ~\$6,000/month.
- **Total ≈ \$96,000/month**, all in stablecoins, **no inventory/slippage risk**.

> **Assumptions & disclaimer:** figures are **illustrative** projections that depend on real order
> volume and job counts; they are **not** forecasts, promises, or financial advice. Fees are
> collected on-chain and are fully verifiable.

---

## 3. Mainnet security & treasury plan

### 3.1 Treasury migration
1. Deploy **OrderExecutor v3** on **Arc mainnet** with `feeRecipient` = **Safe multisig 2/2**.
2. The Safe is also the **owner** (`setFee`, `setAllowedTarget`, `setKeeper`).
3. Deploy the production `MockStableRouter` replacement (real venue) and whitelist it via
   `setAllowedTarget`.
4. Rotate the keeper key to a dedicated, low-privilege hot wallet (`setKeeper`).

### 3.2 Contract safety parameters
- **`feeBps` cap: 1000 (10%) — hard-coded in `setFee`** (`revert FeeTooHigh`). Not removable without
  a contract upgrade behind the Safe.
- **`onlyOwner`** for all config; **`onlyKeeper`** for execution; **whitelisted swap targets**.
- **Input-side fee** → stablecoin revenue, no market risk.
- **User protection:** the signed `minOut` (LIMIT) / `minRate` (TWAP) is measured on the **net**, so
  any fee increase that would under-fill a user simply reverts the transaction.
- Non-custodial: no funds held at rest; leftovers refunded to the user.

### 3.3 Ops checklist (pre-mainnet)
- [ ] Safe 2/2 created on Arc mainnet (owners = your signers).
- [ ] OrderExecutor deployed with `feeRecipient = Safe`, `owner = Safe`.
- [ ] Real swap venue whitelisted; mock router removed.
- [ ] `feeBps` set (default 30) and verified on-chain.
- [ ] Keeper key provisioned and set via `setKeeper`.
- [ ] Monitoring: fee accrual per token, treasury balance, keeper gas (USDC).

---

## 4. Fee collection summary

| Rail | Payer | Rate / basis | Token | Recipient | Scales with |
|---|---|---|---|---|---|
| Platform fee (input-side) | Order owner | 0.30% (30 bps), cap 10% | tokenIn (USDC/EURC) | Treasury Safe | Gross volume |
| Keeper execution fee | Job client (ERC-8183) | per-task `setBudget` | USDC | Keeper wallet | # of tasks |

Everything is enforced on-chain by `OrderExecutor` and verifiable on `explorer.arc.io`.
