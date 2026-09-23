"""AgentTreasuryClient — treasury & micro-credit client for AI agents on Arc (USDC).

DRAFT (not audited). Arc facts: USDC ERC-20 (6 dec) = 0x3600...0000; chain 5042.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Union

from web3 import Web3

USDC = "0x3600000000000000000000000000000000000000"  # Arc ERC-20 (6 dec)
USDC_DECIMALS = 6
CIRBTC = "0x171A4217b86A807A64eB94757Db6849fb4bDbAA0"  # Arc mainnet cirBTC (8 dec)
CIRBTC_DECIMALS = 8

_ERC20_ABI = [
    {"type": "function", "name": "balanceOf", "stateMutability": "view",
     "inputs": [{"name": "a", "type": "address"}], "outputs": [{"type": "uint256"}]},
    {"type": "function", "name": "approve", "stateMutability": "nonpayable",
     "inputs": [{"name": "s", "type": "address"}, {"name": "a", "type": "uint256"}],
     "outputs": [{"type": "bool"}]},
]

_POOL_ABI = [
    {"type": "function", "name": "minLoan", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]},
    {"type": "function", "name": "maxLoan", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]},
    {"type": "function", "name": "approvedAgent", "stateMutability": "view",
     "inputs": [{"name": "a", "type": "address"}], "outputs": [{"type": "bool"}]},
    {"type": "function", "name": "debtOf", "stateMutability": "view",
     "inputs": [{"name": "a", "type": "address"}], "outputs": [{"type": "uint256"}]},
    {"type": "function", "name": "requestLoan", "stateMutability": "nonpayable",
     "inputs": [{"name": "amount", "type": "uint256"}, {"name": "termSeconds", "type": "uint64"}],
     "outputs": [{"type": "uint256"}]},
    {"type": "function", "name": "repay", "stateMutability": "nonpayable",
     "inputs": [{"name": "loanId", "type": "uint256"}], "outputs": []},
    # cirBTC collateral
    {"type": "function", "name": "collateral", "stateMutability": "view",
     "inputs": [{"name": "a", "type": "address"}], "outputs": [{"type": "uint256"}]},
    {"type": "function", "name": "collateralValueUsdc", "stateMutability": "view",
     "inputs": [{"name": "a", "type": "address"}], "outputs": [{"type": "uint256"}]},
    {"type": "function", "name": "collateralDebtOwed", "stateMutability": "view",
     "inputs": [{"name": "a", "type": "address"}], "outputs": [{"type": "uint256"}]},
    {"type": "function", "name": "maxBorrowAgainstCollateral", "stateMutability": "view",
     "inputs": [{"name": "a", "type": "address"}], "outputs": [{"type": "uint256"}]},
    {"type": "function", "name": "depositCollateral", "stateMutability": "nonpayable",
     "inputs": [{"name": "amount", "type": "uint256"}], "outputs": []},
    {"type": "function", "name": "borrowAgainstCollateral", "stateMutability": "nonpayable",
     "inputs": [{"name": "usdcAmount", "type": "uint256"}], "outputs": []},
    {"type": "function", "name": "repayCollateral", "stateMutability": "nonpayable",
     "inputs": [], "outputs": []},
]

Number = Union[int, float, str, Decimal]


@dataclass
class LoanTerms:
    amount: int  # base units (6 dec)
    term_seconds: int = 86_400  # 1 day default


class AgentTreasuryClient:
    """Check USDC balance, borrow a micro-loan, and repay — from an AI agent on Arc."""

    def __init__(
        self,
        rpc_url: str,
        pool_address: str,
        agent_address: str,
        private_key: Optional[str] = None,
        usdc_address: str = USDC,
        cirbtc_address: str = CIRBTC,
    ) -> None:
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        self.pool = self.w3.eth.contract(address=Web3.to_checksum_address(pool_address), abi=_POOL_ABI)
        self.usdc = self.w3.eth.contract(address=Web3.to_checksum_address(usdc_address), abi=_ERC20_ABI)
        self.cirbtc = self.w3.eth.contract(address=Web3.to_checksum_address(cirbtc_address), abi=_ERC20_ABI)
        self.agent = Web3.to_checksum_address(agent_address)
        self._pk = private_key  # TODO: external signer / KMS in production

    # ---- unit helpers ----
    @staticmethod
    def usdc_to_base(amount_usdc: Number) -> int:
        return int(Decimal(str(amount_usdc)) * (10 ** USDC_DECIMALS))

    @staticmethod
    def base_to_usdc(amount_base: int) -> Decimal:
        return Decimal(amount_base) / (10 ** USDC_DECIMALS)

    @staticmethod
    def btc_to_base(amount_btc: Number) -> int:
        return int(Decimal(str(amount_btc)) * (10 ** CIRBTC_DECIMALS))

    @staticmethod
    def base_to_btc(amount_base: int) -> Decimal:
        return Decimal(amount_base) / (10 ** CIRBTC_DECIMALS)

    # ---- reads ----
    def usdc_balance(self) -> int:
        return self.usdc.functions.balanceOf(self.agent).call()

    def usdc_balance_usdc(self) -> Decimal:
        return self.base_to_usdc(self.usdc_balance())

    def is_approved(self) -> bool:
        return self.pool.functions.approvedAgent(self.agent).call()

    def debt(self) -> int:
        return self.pool.functions.debtOf(self.agent).call()

    def needs_credit(self, min_balance: int) -> bool:
        return self.usdc_balance() < min_balance

    def credit_limits(self) -> tuple[int, int]:
        return self.pool.functions.minLoan().call(), self.pool.functions.maxLoan().call()

    # ---- cirBTC collateral ----
    def cirbtc_balance(self) -> int:
        return self.cirbtc.functions.balanceOf(self.agent).call()

    def collateral_btc(self) -> int:
        return self.pool.functions.collateral(self.agent).call()

    def collateral_value_usdc(self) -> int:
        """USDC (6 dec) value of the agent's deposited cirBTC collateral."""
        return self.pool.functions.collateralValueUsdc(self.agent).call()

    def credit_capacity_usdc(self) -> int:
        """USDC (6 dec) the agent can still borrow against its cirBTC collateral."""
        return self.pool.functions.maxBorrowAgainstCollateral(self.agent).call()

    def deposit_collateral(self, amount_btc: Number) -> str:
        amount = self.btc_to_base(amount_btc)
        self._send(self.cirbtc.functions.approve(self.pool.address, amount))
        return self._send(self.pool.functions.depositCollateral(amount))

    def borrow_against_btc(self, amount_usdc: Number) -> str:
        """Borrow USDC backed by the deposited cirBTC collateral (checks LTV capacity)."""
        amount = self.usdc_to_base(amount_usdc)
        cap = self.credit_capacity_usdc()
        if amount > cap:
            raise ValueError(f"amount {amount} exceeds credit capacity {cap}")
        return self._send(self.pool.functions.borrowAgainstCollateral(amount))

    def repay_collateral(self) -> str:
        return self._send(self.pool.functions.repayCollateral())

    # ---- writes ----
    def ensure_credit(
        self,
        amount_usdc: Number,
        min_balance_usdc: Optional[Number] = None,
        term_seconds: int = 86_400,
    ) -> Optional[str]:
        """Borrow `amount_usdc` only if the agent's balance is below the threshold.

        Threshold defaults to `amount_usdc` (i.e. borrow when you can't cover that amount).
        Returns the tx hash, or ``None`` if no credit was needed.
        """
        amount = self.usdc_to_base(amount_usdc)
        threshold = self.usdc_to_base(min_balance_usdc) if min_balance_usdc is not None else amount
        if self.usdc_balance() >= threshold:
            return None
        return self.request_credit(amount, term_seconds)

    def request_credit(self, amount: int, term_seconds: int = 86_400) -> str:
        if not self.is_approved():
            raise PermissionError("agent not approved by the pool (invite-only) — request allowlisting")
        lo, hi = self.credit_limits()
        if not (lo <= amount <= hi):
            raise ValueError(f"amount {amount} out of range [{lo}, {hi}]")
        return self._send(self.pool.functions.requestLoan(amount, term_seconds))

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
                "maxFeePerGas": self.w3.to_wei(30, "gwei"),  # Arc: min base fee 20 gwei
                "maxPriorityFeePerGas": self.w3.to_wei(2, "gwei"),
            }
        )
        signed = self.w3.eth.account.sign_transaction(tx, private_key=self._pk)
        h = self.w3.eth.send_raw_transaction(signed.rawTransaction)
        return h.hex()
