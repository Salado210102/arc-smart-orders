# arc-agent-treasury (Python)

Treasury & **micro-credit client** for AI agents on **Arc** (USDC). Lets a bot or agent:

1. check its **USDC balance**,
2. if below the minimum needed to operate (API/gas), **borrow a micro-loan** ($5–$50) from the
   **`AgentCreditPool`** in a single Arc block,
3. **repay** when its revenue lands (or let the keeper auto-repay from an ERC-8183 job escrow).

> Status: **draft**. The pool is invite-only (whitelisted agents + a small USDC bond). Not audited.

## Install

```bash
# once published to PyPI:
pip install arc-agent-treasury

# or from this repo:
pip install -e ./sdk-python
```

Requirements: Python 3.10+, `web3>=6`.

## Quick start

```python
import os
from arc_agent_treasury import ArcAgentTreasury

tr = ArcAgentTreasury(
    rpc_url="https://rpc.mainnet.arc.io",       # Arc mainnet (chain 5042)
    pool_address="0x...AgentCreditPool",
    agent_address="0x...myAgent",
    private_key=os.environ["AGENT_PK"],         # keep the key on the server
)

print("balance:", tr.usdc_balance(), "base units (6 dec)")
print("approved:", tr.is_approved())

# Borrow only if we're low on USDC (one Arc block):
tx = tr.ensure_credit(min_balance=1_000_000, amount=10_000_000, term_seconds=86_400)
print("borrowed:", tx)  # None if no credit was needed
```

### Check balance + request explicitly

```python
from arc_agent_treasury import ArcAgentTreasury

tr = ArcAgentTreasury(
    rpc_url="https://rpc.mainnet.arc.io",
    pool_address="0x...AgentCreditPool",
    agent_address="0x...myAgent",
    private_key=os.environ["AGENT_PK"],
)

if tr.needs_credit(min_balance=2_000_000):          # < 2 USDC
    lo, hi = tr.credit_limits()
    assert lo <= 10_000_000 <= hi
    tx = tr.request_credit(amount=10_000_000, term_seconds=86_400)  # 10 USDC / 1 day
    print("loan tx:", tx)
```

### Repay

```python
# Approve USDC to the pool first (once), then repay your loan:
#   usdc.functions.approve(pool_address, 2**256 - 1).transact(...)
tx = tr.repay(loan_id=0)
print("repay tx:", tx)
```

### Agent loop (minimal)

```python
def before_api_call(tr):
    # top up just-in-time: if USDC < X, borrow a micro-loan
    tr.ensure_credit(min_balance=500_000, amount=5_000_000, term_seconds=3_600)
```

## How it works

- The agent must be **whitelisted** by the pool's `riskManager` (`setAgent`), and hold a **minimum USDC bond**
  (`depositBond`) — the hybrid collateral (bond + ERC-8004 reputation).
- Loans are **short-term** and capped (per agent and per epoch). Interest is a **flat per-loan** rate.
- **Auto-repay**: once the ERC-8183 job escrow releases funds, the **keeper** settles the loan
  (`repayFrom`) — the agent usually doesn't have to do anything.

## Arc notes

- USDC ERC-20 (6 decimals): `0x3600000000000000000000000000000000000000`.
- Min base fee **20 gwei** (transactions below are dropped) — the client sets `maxFeePerGas` accordingly.
- Sub-second finality: a loan can be requested and confirmed in the same block window.

## API

| Method | Returns | Description |
|---|---|---|
| `usdc_balance()` | `int` | Agent USDC balance (base units, 6 dec) |
| `is_approved()` | `bool` | Whether the agent is whitelisted in the pool |
| `needs_credit(min_balance)` | `bool` | `True` if balance `< min_balance` |
| `credit_limits()` | `(min, max)` | Allowed loan size range |
| `ensure_credit(min_balance, amount, term_seconds=86400)` | `str \| None` | Borrow only if below `min_balance` |
| `request_credit(amount, term_seconds=86400)` | `str` | Request a micro-loan (tx hash) |
| `repay(loan_id)` | `str` | Repay a loan (tx hash) |

## License
MIT.
