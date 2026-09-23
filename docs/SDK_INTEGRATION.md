# SDK integration — `arc-agent-treasury` (Python)

How an AI agent / bot integrates with the Arc **AgentCreditPool**.

## Install
```bash
# from the repo (editable):
pip install -e ./sdk-python

# or, once published to PyPI:
pip install arc-agent-treasury
```
Requires Python 3.10+ and `web3>=6`.

## Configure
```python
import os
from arc_agent_treasury import AgentTreasuryClient

tr = AgentTreasuryClient(
    rpc_url="https://rpc.mainnet.arc.io",   # Arc mainnet (chain 5042)
    pool_address="0x…AgentCreditPool",
    agent_address="0x…myAgent",
    private_key=os.environ["AGENT_PK"],     # keep the key on the server
)
```

## 1) Check balance / eligibility
```python
print("balance:", tr.usdc_balance_usdc(), "USDC")
print("approved:", tr.is_approved())        # whitelist gate (invite-only)
print("debt:", tr.base_to_usdc(tr.debt()), "USDC")
lo, hi = tr.credit_limits()                  # min/max loan (base units)
```

## 2) Borrow only when needed (one Arc block)
```python
tx = tr.ensure_credit(amount_usdc=10, min_balance_usdc=1, term_seconds=86_400)
# -> borrows 10 USDC only if the balance is below 1 USDC; returns None otherwise
print("loan tx:", tx)
```

## 3) Explicit borrow / repay
```python
tx = tr.request_credit(tr.usdc_to_base(10), term_seconds=86_400)  # 10 USDC / 1 day
print("credit tx:", tx)

# approve USDC to the pool once, then repay:
tx = tr.repay(loan_id=0)
print("repay tx:", tx)
```

## 4) Minimal agent loop (just-in-time top-up)
```python
def before_api_call(tr: AgentTreasuryClient):
    # if USDC is low, borrow a micro-loan to keep operating
    tr.ensure_credit(amount_usdc=5, min_balance_usdc=0.5, term_seconds=3_600)
```

## Auto-repay (no code in the agent)
Most of the time the agent **doesn't repay manually**: when its ERC-8183 job completes, the **keeper**
routes the revenue through the **RevenueRouter**, which repays the pool **before** splitting 70/30 to
stakers/treasury. The agent only needs to borrow; repayment is automatic.

## API

| Method | Returns | Description |
|---|---|---|
| `usdc_balance()` | `int` | Balance in base units (6 dec) |
| `usdc_balance_usdc()` | `Decimal` | Balance in USDC |
| `is_approved()` | `bool` | Whitelisted in the pool |
| `debt()` | `int` | Outstanding principal + interest |
| `needs_credit(min_balance)` | `bool` | `balance < min_balance` |
| `credit_limits()` | `(min, max)` | Allowed loan size |
| `ensure_credit(amount_usdc, min_balance_usdc=None, term_seconds=86400)` | `str \| None` | Borrow if low |
| `request_credit(amount, term_seconds=86400)` | `str` | Borrow (tx hash) |
| `repay(loan_id)` | `str` | Repay (tx hash) |
| `usdc_to_base(x)` / `base_to_usdc(x)` | `int` / `Decimal` | Unit conversion |

## Arc notes
- USDC ERC-20 (6 dec): `0x3600000000000000000000000000000000000000`.
- Min base fee **20 gwei** — transactions below are dropped; the client sets `maxFeePerGas` accordingly.
- Sub-second finality: a loan can be requested and confirmed in the same block window.

## License
MIT.
