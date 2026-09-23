# Phase 2 — Agentic credit & monetization (architecture)

> Status: **draft** (contracts in `contracts/src/credit/` are not audited or deployed).
> Complements the Core (smart orders + Agent Launchpad) with a **liquidity & credit layer** for the
> agentic economy.

## Components

| Contract | Role | Where |
|---|---|---|
| **AgentCreditPool** | Peer-to-contract USDC micro-credit: LPs earn yield, whitelisted agents borrow $5–$50 | `contracts/src/credit/AgentCreditPool.sol` |
| **RevenueRouter** | Enforces **repay-before-split**: settles an agent's debt, then forwards the rest to the splitter | `contracts/src/credit/RevenueRouter.sol` |
| **RevenueSplitter** | Splits an agent's USDC revenue **70% stakers / 30% treasury** | `contracts/src/launchpad/RevenueSplitter.sol` |
| **AgentStakingVault** | ERC-4626-style vault (asset = agent token) paying **USDC** yield (Synthetix accumulator) | `contracts/src/launchpad/AgentStakingVault.sol` |
| **Python SDK** | `arc-agent-treasury` — an agent checks balance / borrows / repays | `sdk-python/` |

## Economic flow (unified)

```
   AI agent needs gas/API
          │  borrow ($5–$50)
          ▼
   AgentCreditPool ──────────────► AI agent
        ▲                             │  does a job (ERC-8183 escrow)
        │  repayOnBehalf (auto)       ▼
        │                       RevenueRouter.route(agent, revenue)
        │                             │  1) repay debt FIRST
        └─────────────────────────────┤
                                      │  2) split the remainder
                                      ▼
                               RevenueSplitter
                                 ├─ 70% ─► AgentStakingVault (stakers earn USDC)
                                 └─ 30% ─► Safe treasury
```

**Ordering guarantee:** `RevenueRouter.route(agent, amount)` calls `pool.repayOnBehalf(agent, …)` **before**
`splitter.distribute(remainder)`, in the **same transaction**. So the credit pool is settled first and
dividends are computed only on the **net** revenue. (If revenue is smaller than the debt, the pool is paid
in full up to the revenue and nothing is split — the loan stays partially open.)

## Risk model (recap)
Whitelist (invite-only) → per-agent & per-epoch caps → max utilization → **first-loss reserve** →
**hybrid bond** (min USDC bond on-chain + ERC-8004 reputation, slashed on default) → **pause**.
Fees: flat per-loan interest; **15% performance fee → Safe**; a slice → reserve; the rest → LPs.

## Invite-only pilot (steps)
1. Deploy: `DeployMainnet.s.sol` (core) then `DeployCreditPool.s.sol` (pool + router, owner = Safe).
2. The **Safe** executes: `setRoles(riskManager, keeper)`, `setLP(<lp>, true)`, `setAgent(<agent>, true)`,
   `setPolicy(...)`, and `router.setConfig(pool, splitter)`.
3. Fund the pool with a **small** whitelisted LP deposit (TVL-capped).
4. Agent registers an ERC-8004 identity (when live), deposits the **USDC bond**, requests a micro-loan.
5. Jobs run via ERC-8183; on delivery the keeper routes revenue through the **RevenueRouter** → the loan
   is repaid before any dividend is split.
6. Monitor the alerts bot for `Loaned` / `Repaid` / `Defaulted`.

## Tests
```bash
cd contracts
forge test --match-contract AgentCreditPoolTest -vvv   # pool: 21 tests
forge test --match-contract RevenueRouterTest -vvv     # repay-before-split integration
```
