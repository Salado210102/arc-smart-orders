"""arc-agent-treasury — DRAFT (not published yet).

Tiny client so any AI agent/bot on Arc can:
  1. check its USDC balance,
  2. if below the minimum needed to operate (API/gas), borrow a micro-loan from the
     AgentCreditPool in a single Arc block,
  3. repay later (ideally auto-repaid from the agent's USDC revenue).

Arc facts: USDC ERC-20 (6 dec) = 0x3600...0000 ; sub-second finality (1 confirmation).

Example
-------
    from arc_agent_treasury import ArcAgentTreasury

    tr = ArcAgentTreasury(
        rpc_url="https://rpc.mainnet.arc.io",
        pool_address="0x...AgentCreditPool",
        agent_address="0x...myAgent",
        private_key=os.environ["AGENT_PK"],   # or use a signer/callback
    )
    if tr.needs_credit(min_balance=1_000_000):          # < 1 USDC
        tx = tr.request_credit(amount=10_000_000)       # 10 USDC
        print("borrowed:", tx)
    print("balance:", tr.usdc_balance())
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from web3 import Web3

USDC = "0x3600000000000000000000000000000000000000"  # Arc ERC-20 (6 dec)

_ERC20_ABI = [
    {"type": "function", "name": "balanceOf", "stateMutability": "view",
     "inputs": [{"name": "a", "type": "address"}], "outputs": [{"type": "uint256"}]},
    {"type": "function", "name": "approve", "stateMutability": "nonpayable",
     "inputs": [{"name": "s", "type": "address"}, {"name": "a", "type": "uint256"}],
     "outputs": [{"type": "bool"}]},
]

# Minimal AgentCreditPool ABI (matches the draft contract's public surface).
_POOL_ABI = [
    {"type": "function", "name": "minLoan", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]},
    {"type": "function", "name": "maxLoan", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]},
    {"type": "function", "name": "approvedAgent", "stateMutability": "view",
     "inputs": [{"name": "a", "type": "address"}], "outputs": [{"type": "bool"}]},
    {"type": "function", "name": "requestLoan", "stateMutability": "nonpayable",
     "inputs": [{"name": "amount", "type": "uint256"}, {"name": "termSeconds", "type": "uint64"}],
     "outputs": [{"type": "uint256"}]},
    {"type": "function", "name": "repay", "stateMutability": "nonpayable",
     "inputs": [{"name": "loanId", "type": "uint256"}], "outputs": []},
]


@dataclass
class LoanTerms:
    amount: int          # base units (6 dec)
    term_seconds: int = 86_400  # 1 day default


class ArcAgentTreasury:
    def __init__(
        self,
        rpc_url: str,
        pool_address: str,
        agent_address: str,
        private_key: Optional[str] = None,
        usdc_address: str = USDC,
    ) -> None:
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        self.pool = self.w3.eth.contract(address=Web3.to_checksum_address(pool_address), abi=_POOL_ABI)
        self.usdc = self.w3.eth.contract(address=Web3.to_checksum_address(usdc_address), abi=_ERC20_ABI)
        self.agent = Web3.to_checksum_address(agent_address)
        self._pk = private_key  # TODO: support external signer / KMS in prod

    # ---- reads ----
    def usdc_balance(self) -> int:
        return self.usdc.functions.balanceOf(self.agent).call()

    def is_approved(self) -> bool:
        return self.pool.functions.approvedAgent(self.agent).call()

    def needs_credit(self, min_balance: int) -> bool:
        return self.usdc_balance() < min_balance

    def credit_limits(self) -> tuple[int, int]:
        return self.pool.functions.minLoan().call(), self.pool.functions.maxLoan().call()

    # ---- writes (single Arc block) ----
    def ensure_credit(self, min_balance: int, amount: int, term_seconds: int = 86_400) -> Optional[str]:
        """If below `min_balance`, request a micro-loan. Returns the tx hash or None."""
        if not self.needs_credit(min_balance):
            return None
        return self.request_credit(amount, term_seconds)

    def request_credit(self, amount: int, term_seconds: int = 86_400) -> str:
        if not self.is_approved():
            raise PermissionError("agent not approved by the pool (risk gate) — request allowlisting")
        lo, hi = self.credit_limits()
        if not (lo <= amount <= hi):
            raise ValueError(f"amount {amount} out of range [{lo}, {hi}]")
        fn = self.pool.functions.requestLoan(amount, term_seconds)
        return self._send(fn)

    def repay(self, loan_id: int) -> str:
        # TODO: approve USDC to the pool first if allowance is insufficient.
        return self._send(self.pool.functions.repay(loan_id))

    # ---- internal ----
    def _send(self, fn) -> str:
        if not self._pk:
            raise RuntimeError("no signer configured (TODO: external signer support)")
        tx = fn.build_transaction(
            {
                "from": self.agent,
                "nonce": self.w3.eth.get_transaction_count(self.agent),
                "chainId": self.w3.eth.chain_id,  # 5042 on mainnet
                "gas": 400_000,
                # Arc: min base fee 20 gwei — set maxFeePerGas accordingly in prod.
                "maxFeePerGas": self.w3.to_wei(30, "gwei"),
                "maxPriorityFeePerGas": self.w3.to_wei(2, "gwei"),
            }
        )
        signed = self.w3.eth.account.sign_transaction(tx, private_key=self._pk)
        h = self.w3.eth.send_raw_transaction(signed.rawTransaction)
        return h.hex()
