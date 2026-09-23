"""Minimal JSON-RPC client (stdlib only) — enough for balances, allowance and sending a raw tx."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, List, Optional


class JsonRpc:
    def __init__(self, url: str, timeout: int = 30) -> None:
        self.url = url
        self.timeout = timeout
        self._id = 0

    def call(self, method: str, params: Optional[List[Any]] = None) -> Any:
        self._id += 1
        body = json.dumps({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or []}).encode()
        req = urllib.request.Request(
            self.url,
            data=body,
            headers={"content-type": "application/json", "user-agent": "arc-smart-orders-python/0.1.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                resp = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:  # pragma: no cover - network
            raise RuntimeError(f"rpc http {e.code}: {e.read().decode(errors='replace')}") from e
        if isinstance(resp, dict) and resp.get("error"):
            raise RuntimeError(f"rpc error: {resp['error']}")
        return resp.get("result")

    # --- convenience wrappers ---
    def eth_call(self, to: str, data: str, block: str = "latest") -> str:
        return self.call("eth_call", [{"to": to, "data": data}, block])

    def chain_id(self) -> int:
        return int(self.call("eth_chainId"), 16)

    def get_transaction_count(self, address: str, block: str = "pending") -> int:
        return int(self.call("eth_getTransactionCount", [address, block]), 16)

    def gas_price(self) -> int:
        return int(self.call("eth_gasPrice"), 16)

    def estimate_gas(self, tx: dict) -> int:
        return int(self.call("eth_estimateGas", [tx]), 16)

    def send_raw_transaction(self, raw_hex: str) -> str:
        return self.call("eth_sendRawTransaction", [raw_hex])

    def get_transaction_receipt(self, tx_hash: str) -> Optional[dict]:
        return self.call("eth_getTransactionReceipt", [tx_hash])
