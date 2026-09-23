# Arc Agent Credit Pool & SDK — design proposal (DRAFT)

> Status: **design / draft**. The contract in `contracts/src/credit/AgentCreditPool.sol` and the Python
> SDK in `sdk-python/` are skeletons — **not audited, not deployed**.
> Thesis: **$0 own capital** (LPs fund, peer-to-contract) + **$0 paid marketing** (organic B2B/B2Agent).

---

## 1. What it is

A USDC liquidity pool on **Arc** where:
- **LPs** deposit USDC and earn yield by lending to **AI agents**.
- **Approved agents** take **micro-loans ($5–$50)** to pay for **API calls / gas** (x402-style) and repay
  shortly after (ideally auto-repaid from the agent's USDC revenue).
- The protocol takes a **15% performance fee on interest** → **Safe treasury**. No protocol capital at risk.

It's the "liquidity layer" for the agentic economy that complements the launchpad + order engine.

---

## 2. Honest feedback (read this first)

**Strong fits**
- Aligns exactly with Arc/Circle's push: **Agent Stack, Agent Wallets, nanopayments (x402), agentic economy**.
- **$0 capital is real**: LPs supply the USDC; the protocol only routes it.
- Arc's **sub-second finality** makes micro-loans that repay in the same/next block actually viable.

**The hard part — default risk**
- **Uncollateralized loans to bots = the whole problem.** If we can't recover on default, LPs lose and the
  pool dies. The security model (§4) is the product; the contract is easy.
- "Auto-repay from revenue" only works if the agent's revenue actually flows through something we can
  intercept (a `RevenueSplitter`, a vault, or a job escrow). Otherwise it's a promise.

**$0 marketing is optimistic**
- B2B/B2Agent is organic *in principle*, but agents' operators still have to discover and integrate it.
  Realistic path: ship the **Python SDK** (§3) where builders already are (PyPI/GitHub), not ads.

**Regulatory caution**
- Pooled lending of a stablecoin can touch **money-transmission / lending / securities** rules depending on
  jurisdiction. As a solo builder with no entity, this is a **flag**: start with a **whitelist** (no public
  deposit), keep it small, and get legal clarity before opening the LP side publicly.

**Verdict:** worth prototyping **as an MVP**, gated and small, *after* the current protocol is audited.
It's a strong narrative piece even as a "Phase 2" module.

---

## 3. Architecture

```
   LP (USDC) ──deposit──►  AgentCreditPool (USDC, Arc)
                              │  idle ──loan──► AI agent (pays API/gas)
                              │  ▲                        │
                              │  └────── repay (+ interest)┘
                              └── 15% of interest ──► Safe treasury
                                      85% ──► LPs (yield) + reserve buffer

   AI agent ──►  arc-agent-treasury (Python)  ──►  requestLoan / repay
```

### Contract — `AgentCreditPool.sol` (draft)
- USDC pool with **LP shares** (pro-rata of NAV).
- `deposit` / `withdraw`, `requestLoan` / `repay`, `markDefault`.
- **Risk gate:** `approvedAgent` mapping (MVP), per-agent exposure, per-epoch outstanding cap, max term.
- **Performance fee** (15% of interest) → treasury; a slice → **first-loss reserve**.
- Owner/treasury/riskManager = **Safe**.

### SDK — `arc-agent-treasury` (Python, draft)
- `ArcAgentTreasury`: `usdc_balance()`, `needs_credit(min)`, `request_credit(amount)`, `repay(id)`.
- Designed for agents: one call to **check + borrow if low** in a single Arc block.
- Publish to **PyPI** + GitHub; MIT.

### Keeper/agent integration (future)
- Reuse the existing **keeper** to trigger `repay` when the agent's USDC revenue arrives, and to watch
  `Loaned`/`Repaid`/`Defaulted` events (the **alerts bot** already posts events to Telegram/Discord).

---

## 4. Security & risk model (the crux)

Layered, from cheapest to strongest — MVP uses the top layers; ERC-8004 unlocks the rest:

1. **Whitelist of approved agent operators** (MVP): only vetted addresses can borrow. No public borrowing.
2. **Per-agent exposure cap + per-epoch outstanding cap + short max term** (e.g. ≤$50, ≤7d) — bounds loss.
3. **First-loss reserve** funded by part of the performance fee.
4. **Revenue interception / auto-repay**: route the agent's income through its `RevenueSplitter`/vault and
   have the **keeper** call `repay` automatically (or a `debt` hook that skims revenue before payout).
5. **Refundable bond / soft collateral**: an approved agent stakes a small USDC bond (or a % of its
   `AgentStakingVault` shares) that is **slashed on default** — cheap, and it prices in bad actors.
6. **ERC-8004 identity + reputation** (when it ships on Arc): credit only to identities with non-zero
   reputation; **reputation slashing** on default makes default costly off-chain too.
7. **ERC-8183 job escrow as revenue source**: many agent jobs are escrowed; repayment can be bound to job
   completion (`deliverable` hash), i.e. credit "against" pending, verifiable work.
8. **Circuit breaker / pause** (owner) + **max utilization** so LPs can always withdraw idle funds.

**Non-goals (for MVP):** uncollateralized *public* lending, long terms, large size. Those need a real credit
model and an audit.

---

## 5. Economics (draft defaults)
- Interest: simple, per-term (e.g. **2% / term**), `interestBps` configurable (cap enforced).
- **Performance fee: 15%** of interest → treasury (Safe). Remainder → LPs + reserve.
- LP yield = (interest − performanceFee − reserveSlice) / TVL, variable.
- All USDC, no token, no protocol equity, **non-dilutive**.

---

## 6. Repo layout (modular, mirrors `arc-smart-orders`)

```
contracts/
  src/credit/AgentCreditPool.sol        # new module (draft)
  test/AgentCreditPool.t.sol            # TODO
  script/DeployCreditPool.s.sol         # TODO (env-validated, Safe owner)
sdk-python/
  pyproject.toml                        # PyPI: arc-agent-treasury
  arc_agent_treasury/__init__.py        # ArcAgentTreasury client (draft)
  README.md                             # TODO
docs/
  AGENT_CREDIT_POOL.md                  # this design doc
ops/                                    # reuse alerts bot for Loaned/Repaid/Defaulted
```

---

## 7. Suggested MVP scope (Phase 1)
- [ ] Finalize the contract (interest math, reserve, per-epoch caps) + Foundry tests.
- [ ] **Whitelist-only**, TVL-capped, small loans (≤$50), short term (≤7d).
- [ ] Python SDK: `usdc_balance / needs_credit / request_credit / repay` + example agent.
- [ ] Keeper: auto‑`repay` on revenue; events → alerts bot.
- [ ] Audit the credit math + risk controls before opening any LP deposit.

## 8. Decisions locked (2026-09-23)

1. **Invite-only / whitelist** for the MVP — both LPs and agents are whitelisted (`approvedLP` / `approvedAgent`);
   **no public deposit** until traction + audit.
2. **Auto-repay via ERC-8183** (job escrow) is the primary mechanism: credit is extended against work whose
   funds are already locked in escrow; the **keeper** calls `repayFrom(loanId)` (pays from escrow/keeper) as
   soon as the deliverable is validated. `repay(loanId)` (pull from the borrower) remains as a fallback.
3. **Hybrid collateral**: a **minimum USDC bond** (`minBond`, default 10 USDC, held by the pool) **plus
   ERC-8004** identity/reputation — default **slashes the bond** (on-chain) and the **reputation** (off-chain).
4. **Contract finalized** in `contracts/src/credit/AgentCreditPool.sol` with: flat per-loan interest,
   first-loss **reserve**, **per-agent / per-epoch caps**, a **max utilization** guard, and **pause**.

### Draft parameters (defaults in code)
| Param | Default | Notes |
|---|---|---|
| `interestBps` | 100 (1%) | flat per loan, cap 2000 bps |
| `performanceFeeBps` | 1500 (15%) | on interest → treasury (cap 3000) |
| `reserveShareBps` | 2000 (20%) | of interest → first-loss reserve (cap 3000) |
| `minLoan` / `maxLoan` | 5 / 50 USDC | micro-loans |
| `maxTerm` | 7 days | short-term only |
| `maxPerAgent` | 50 USDC | per-agent outstanding cap |
| `epochCap` / `epochDuration` | 500 USDC / 1 day | origination cap per epoch |
| `maxUtilizationBps` | 8000 (80%) | LPs can always withdraw |
| `minBond` | 10 USDC | hybrid collateral |

### Tests
Foundry suite at `contracts/test/AgentCreditPool.t.sol` (deposit/withdraw shares, whitelist gates, bond,
loan caps, epoch/utilization caps, repay interest split, default slashing + reserve, pause, access control).

> ⚠️ **Compilation pending:** `forge.exe` is blocked by Windows Application Control in the dev environment,
> so the suite was written but **not executed** here. Run in your env:
> ```bash
> cd contracts && forge test --match-contract AgentCreditPoolTest -vvv
> ```

## 9. Notes
- The `keeper` role is reserved for ERC-8183 auto-repay (`repayFrom`).
- Reserve is held by the pool and **not** LP-withdrawable (first-loss buffer).
- ERC-8004 reputation slash on default remains an off-chain action (recorded via `Defaulted`).

