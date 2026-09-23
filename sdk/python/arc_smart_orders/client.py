"""ArcSmartOrdersClient — build/sign EIP-712 Arc Smart Orders and submit them to the keeper API.

Example
-------
    from arc_smart_orders import ArcSmartOrdersClient, to_units

    client = ArcSmartOrdersClient(private_key=os.environ["PK"])           # Arc mainnet
    client.ensure_permit2_approval()                                     # one-time (gas)
    order = client.submit_limit_order(amount_in=to_units("1"), min_out=to_units("0.90"))  # 0 gas
    filled = client.wait_for_fill(order["order"]["id"])
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from eth_account import Account
from eth_utils import keccak

from .constants import (
    ARC_MAINNET_CHAIN_ID,
    ARC_TESTNET_CHAIN_ID,
    KEEPER_API,
    PERMIT2,
    USDC,
    executor_for,
    eurc_for,
    rpc_for,
)
from .rpc import JsonRpc
from .signer import owner_address, sign_limit_order, sign_twap_order

MAX_UINT256 = 2**256 - 1

_APPROVE_SELECTOR = keccak(text="approve(address,uint256)")[:4]
_BALANCE_OF_SELECTOR = keccak(text="balanceOf(address)")[:4]
_ALLOWANCE_SELECTOR = keccak(text="allowance(address,address)")[:4]


def to_units(amount: str | float, decimals: int = 6) -> int:
    """Human amount -> base units (e.g. ``to_units('1.5')`` -> ``1500000``)."""
    scaled = round(float(amount) * (10**decimals))
    return int(scaled)


def from_units(amount: int, decimals: int = 6) -> float:
    return int(amount) / (10**decimals)


def _addr_arg(a: str) -> bytes:
    return bytes.fromhex(a[2:].lower()).rjust(32, b"\x00")


def _uint_arg(n: int) -> bytes:
    return int(n).to_bytes(32, "big")


def _net(chain_id: int) -> str:
    return "mainnet" if chain_id == ARC_MAINNET_CHAIN_ID else "testnet"


def _http(method: str, url: str, body: Optional[dict] = None, timeout: int = 30) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"content-type": "application/json", "user-agent": "arc-smart-orders-python/0.1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:  # pragma: no cover - network
        detail = e.read().decode(errors="replace")
        raise RuntimeError(f"keeper http {e.code}: {detail}") from e


class ArcSmartOrdersClient:
    def __init__(
        self,
        private_key: str,
        *,
        chain_id: int = ARC_MAINNET_CHAIN_ID,
        rpc_url: Optional[str] = None,
        keeper_url: Optional[str] = None,
        executor: Optional[str] = None,
        token_in: str = USDC,
        token_out: Optional[str] = None,
        permit2: str = PERMIT2,
    ) -> None:
        self.private_key = private_key
        self.chain_id = chain_id
        self.rpc = JsonRpc(rpc_url or rpc_for(chain_id))
        self.keeper_url = (keeper_url or KEEPER_API[_net(chain_id)]).rstrip("/")
        self.executor = executor or executor_for(chain_id)
        self.token_in = token_in
        self.token_out = token_out or eurc_for(chain_id)
        self.permit2 = permit2

    # ------------------------------------------------------------------ identity
    @property
    def address(self) -> str:
        return owner_address(self.private_key)

    # ------------------------------------------------------------------ reads
    def erc20_balance(self, token: str, owner: Optional[str] = None) -> int:
        owner = owner or self.address
        data = "0x" + (_BALANCE_OF_SELECTOR + _addr_arg(owner)).hex()
        return int(self.rpc.eth_call(token, data), 16)

    def usdc_balance(self, owner: Optional[str] = None) -> int:
        return self.erc20_balance(self.token_in, owner)

    def permit2_allowance(self, token: Optional[str] = None, owner: Optional[str] = None) -> int:
        token = token or self.token_in
        owner = owner or self.address
        data = "0x" + (_ALLOWANCE_SELECTOR + _addr_arg(owner) + _addr_arg(self.permit2)).hex()
        return int(self.rpc.eth_call(token, data), 16)

    # ------------------------------------------------------------------ approve (one-time, gas)
    def ensure_permit2_approval(self, token: Optional[str] = None, amount: Optional[int] = None) -> Optional[str]:
        """Approve Permit2 for ``token`` if needed. Returns the tx hash, or ``None`` if already approved."""
        token = token or self.token_in
        amount = MAX_UINT256 if amount is None else int(amount)
        if self.permit2_allowance(token) >= amount:
            return None
        data = _APPROVE_SELECTOR + _addr_arg(self.permit2) + _uint_arg(amount)
        unsigned = self._build_tx(token, data)
        signed = Account.sign_transaction(unsigned, self.private_key)
        raw = getattr(signed, "raw_transaction", None) or getattr(signed, "rawTransaction")
        tx_hash = self.rpc.send_raw_transaction("0x" + raw.hex())
        self._wait_receipt(tx_hash)
        return tx_hash

    # ------------------------------------------------------------------ signing
    def sign_limit_order(
        self,
        *,
        amount_in: int,
        min_out: int,
        token_in: Optional[str] = None,
        token_out: Optional[str] = None,
        nonce: Optional[int] = None,
        deadline: Optional[int] = None,
    ) -> Dict[str, Any]:
        now = int(time.time())
        nonce = nonce if nonce is not None else now
        deadline = deadline if deadline is not None else now + 3600
        signature, typed = sign_limit_order(
            self.private_key,
            chain_id=self.chain_id,
            spender=self.executor,
            token_in=token_in or self.token_in,
            token_out=token_out or self.token_out,
            amount_in=int(amount_in),
            min_out=int(min_out),
            nonce=int(nonce),
            deadline=int(deadline),
        )
        return {"signature": signature, "typedData": typed, "nonce": int(nonce), "deadline": int(deadline)}

    def build_order_payload(
        self,
        *,
        amount_in: int,
        min_out: int,
        nonce: int,
        deadline: int,
        signature: str,
        token_in: Optional[str] = None,
        token_out: Optional[str] = None,
        job_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = {
            "maker": self.address,
            "tokenIn": token_in or self.token_in,
            "tokenOut": token_out or self.token_out,
            "amountIn": str(int(amount_in)),
            "minOut": str(int(min_out)),
            "nonce": str(int(nonce)),
            "deadline": int(deadline),
            "signature": signature,
        }
        if job_id:
            payload["jobId"] = job_id
        return payload

    # ------------------------------------------------------------------ submit
    def submit_order(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return _http("POST", f"{self.keeper_url}/v1/orders", payload)

    def submit_limit_order(
        self,
        *,
        amount_in: int,
        min_out: int,
        token_in: Optional[str] = None,
        token_out: Optional[str] = None,
        nonce: Optional[int] = None,
        deadline: Optional[int] = None,
        job_id: Optional[str] = None,
        check_allowance: bool = True,
    ) -> Dict[str, Any]:
        """Validate off-chain (balance + Permit2 allowance), sign, and POST to the keeper."""
        token_in = token_in or self.token_in
        amount_in = int(amount_in)
        min_out = int(min_out)
        if amount_in <= 0 or min_out <= 0:
            raise ValueError("amount_in and min_out must be > 0")

        now = int(time.time())
        deadline = int(deadline if deadline is not None else now + 3600)
        if deadline <= now + 30:
            raise ValueError("deadline must be at least 30s in the future")

        balance = self.erc20_balance(token_in)
        if balance < amount_in:
            raise ValueError(f"insufficient balance: have {balance}, need {amount_in}")
        if check_allowance:
            allowance = self.permit2_allowance(token_in)
            if allowance < amount_in:
                raise ValueError(
                    f"Permit2 allowance too low ({allowance}); call ensure_permit2_approval() first"
                )

        signed = self.sign_limit_order(
            amount_in=amount_in, min_out=min_out, token_in=token_in, token_out=token_out, nonce=nonce, deadline=deadline
        )
        payload = self.build_order_payload(
            amount_in=amount_in,
            min_out=min_out,
            nonce=signed["nonce"],
            deadline=signed["deadline"],
            signature=signed["signature"],
            token_in=token_in,
            token_out=token_out,
            job_id=job_id,
        )
        return self.submit_order(payload)

    # ------------------------------------------------------------------ status
    def get_order(self, order_id: str) -> Dict[str, Any]:
        return _http("GET", f"{self.keeper_url}/v1/orders/{order_id}")

    def wait_for_fill(self, order_id: str, *, timeout: int = 180, interval: float = 3.0) -> Dict[str, Any]:
        """Poll ``GET /v1/orders/:id`` until FILLED/FAILED/EXPIRED or timeout."""
        deadline = time.time() + timeout
        last: Dict[str, Any] = {}
        while time.time() < deadline:
            last = self.get_order(order_id)
            status = str(last.get("status", "")).upper()
            if status in ("FILLED", "FAILED", "EXPIRED"):
                return last
            time.sleep(interval)
        return last

    # ------------------------------------------------------------------ internals
    def _build_tx(self, to: str, data: bytes, value: int = 0) -> Dict[str, Any]:
        owner = self.address
        hexdata = "0x" + data.hex()
        gas = self.rpc.estimate_gas({"from": owner, "to": to, "data": hexdata, "value": hex(value)})
        base = self.rpc.gas_price()
        tip = 1_000_000_000  # 1 gwei
        return {
            "chainId": self.chain_id,
            "nonce": self.rpc.get_transaction_count(owner),
            "to": to,
            "value": value,
            "data": hexdata,
            "gas": int(gas * 12 // 10),
            "maxFeePerGas": base * 2 + tip,
            "maxPriorityFeePerGas": tip,
            "type": 2,
        }

    def _wait_receipt(self, tx_hash: str, timeout: int = 60) -> Optional[dict]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            rcpt = self.rpc.get_transaction_receipt(tx_hash)
            if rcpt:
                return rcpt
            time.sleep(2)
        return None
