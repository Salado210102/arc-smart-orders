"""Event sources. RPC is a working stopgap; Bitquery is the intended primary source.

The processor does not care which source produced a RawEvent.
"""
from __future__ import annotations

import json
import time
import urllib.request
from abc import ABC, abstractmethod

from .config import (
    POOLMANAGER_V4,
    UNISWAP_V2_SWAP_TOPIC0,
    UNISWAP_V3_SWAP_TOPIC0,
    V4_INITIALIZE_TOPIC0,
    V4_SWAP_TOPIC0,
    LaunchpadConfig,
)
from .models import RawEvent


class ConfigurationError(RuntimeError):
    pass


class EventSource(ABC):
    name: str = "base"

    @abstractmethod
    def poll(self, from_block: int, to_block: int) -> list[RawEvent]:
        """Return events in [from_block, to_block]. Must be pure read."""


class RpcEventSource(EventSource):
    name = "rpc"

    def __init__(self, rpc_url: str, launchpads: list[LaunchpadConfig], timeout: int = 30):
        self.rpc_url = rpc_url
        self.launchpads = launchpads
        self.timeout = timeout
        self._block_time_cache: dict[int, int | None] = {}

    def _rpc(self, method: str, params: list) -> object:
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
        req = urllib.request.Request(
            self.rpc_url, data=body,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "User-Agent": "arc-intel-indexer/0.1 (read-only)",
            },
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            payload = json.loads(resp.read().decode())
        if "error" in payload and payload["error"]:
            raise RuntimeError(f"rpc_error: {payload['error']}")
        return payload.get("result")

    def head(self) -> int:
        return int(self._rpc("eth_blockNumber", []), 16)

    def _block_time(self, block: int) -> int | None:
        if block not in self._block_time_cache:
            try:
                b = self._rpc("eth_getBlockByNumber", [hex(block), False])
                self._block_time_cache[block] = int(b["timestamp"], 16) if b else None
            except Exception:
                self._block_time_cache[block] = None
        return self._block_time_cache[block]

    def _logs(self, params: dict) -> list[dict]:
        res = self._rpc("eth_getLogs", [params])
        return res if isinstance(res, list) else []

    def _to_event(self, log: dict, kind: str, dex: str | None = None, launchpad: str | None = None) -> RawEvent:
        block = int(log["blockNumber"], 16)
        return RawEvent(
            source=self.name,
            kind=kind,
            tx_hash=log["transactionHash"],
            log_index=int(log["logIndex"], 16),
            block_number=block,
            block_time=self._block_time(block),
            address=log["address"].lower(),
            topics=list(log.get("topics", [])),
            data=log.get("data", "0x"),
            dex=dex,
            launchpad=launchpad,
        )

    def poll(self, from_block: int, to_block: int) -> list[RawEvent]:
        events: list[RawEvent] = []
        rng = {"fromBlock": hex(from_block), "toBlock": hex(to_block)}
        for topic, dex in (
            (UNISWAP_V3_SWAP_TOPIC0, "uniswap_v3"),
            (UNISWAP_V2_SWAP_TOPIC0, "uniswap_v2"),
        ):
            for log in self._logs({**rng, "topics": [topic]}):
                try:
                    events.append(self._to_event(log, "dex_swap", dex=dex))
                except Exception:
                    continue
        for lp in self.launchpads:
            for log in self._logs({**rng, "address": lp.address}):
                try:
                    events.append(self._to_event(log, "launchpad", launchpad=lp.name))
                except Exception:
                    continue
        # Uniswap v4 (singleton PoolManager): Initialize -> pools_v4; Swap -> dex_swap.
        for log in self._logs({**rng, "address": POOLMANAGER_V4, "topics": [V4_SWAP_TOPIC0]}):
            try:
                events.append(self._to_event(log, "dex_swap", dex="uniswap_v4"))
            except Exception:
                continue
        for log in self._logs({**rng, "address": POOLMANAGER_V4, "topics": [V4_INITIALIZE_TOPIC0]}):
            try:
                events.append(self._to_event(log, "pool_init"))
            except Exception:
                continue
        return events


class BitqueryEventSource(EventSource):
    """Primary intended source: Bitquery EVM(network: arc) DEXTrades + launchpad logs.

    NOT enabled by default: requires BITQUERY_OAUTH and independent confirmation that
    Bitquery indexes Arc (this could not be verified without a key).
    """

    name = "bitquery"

    def __init__(self, oauth: str | None, network: str = "arc"):
        if not oauth:
            raise ConfigurationError(
                "BITQUERY_OAUTH not set. Bitquery source disabled; set it to enable."
            )
        self.oauth = oauth
        self.network = network

    def build_subscription_query(self) -> str:
        # Field names must be validated against the live Bitquery schema for Arc.
        return (
            "subscription {\n"
            f'  EVM(network: {self.network}) {{\n'
            "    DEXTrades {\n"
            "      Block { Number Time }\n"
            "      Transaction { Hash }\n"
            "      Trade { Buy { Amount Currency { Symbol SmartContract } }"
            " Sell { Amount Currency { Symbol SmartContract } } Dex { ProtocolName } }\n"
            "    }\n"
            "  }\n"
            "}"
        )

    def connect(self):  # pragma: no cover - requires network + key
        try:
            import websockets  # noqa: F401
        except Exception as exc:  # pragma: no cover
            raise ConfigurationError("websockets package not installed") from exc
        raise ConfigurationError("Bitquery live ingestion not enabled in this environment")

    def poll(self, from_block: int, to_block: int) -> list[RawEvent]:  # pragma: no cover
        raise ConfigurationError("Bitquery source is push-based (WebSocket); use connect()")
