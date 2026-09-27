"""Typed rows and raw events."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RawEvent:
    source: str                       # "rpc" | "bitquery"
    kind: str                         # "dex_swap" | "launchpad"
    tx_hash: str
    log_index: int
    block_number: int
    block_time: int | None
    address: str                      # emitting contract (pool / launchpad)
    topics: list[str]
    data: str
    dex: str | None = None
    launchpad: str | None = None
    decoded: dict = field(default_factory=dict)

    @property
    def idempotency_key(self) -> tuple[str, int]:
        return (self.tx_hash.lower(), self.log_index)


@dataclass
class TokenRow:
    address: str
    symbol: str | None = None
    name: str | None = None
    creator: str | None = None
    launchpad: str | None = None
    created_ts: int | None = None
    pool_id: str | None = None


@dataclass
class SwapRow:
    tx_hash: str
    log_index: int
    block_number: int
    ts: int | None
    token: str | None
    wallet: str | None
    side: str | None                  # "buy" | "sell" | "unknown"
    amount_in: str | None
    amount_out: str | None
    price_implied: str | None
    dex: str | None
    pool: str | None


@dataclass
class DevBuyRow:
    tx_hash: str
    log_index: int
    token: str | None
    creator_wallet: str | None
    amount: str | None
    ts: int | None


@dataclass
class LaunchpadEventRow:
    tx_hash: str
    log_index: int
    launchpad: str
    event_name: str | None            # None until ABI supplied
    topic0: str
    token: str | None
    address: str
    block_number: int
    ts: int | None
    topics: list[str]
    data: str


@dataclass
class TokenTransferRow:
    tx_hash: str
    log_index: int
    token: str
    from_addr: str
    to_addr: str
    value: str
    block_number: int
    ts: int | None


@dataclass
class PoolV4Row:
    pool_id: str
    currency0: str
    currency1: str
    fee: int | None
    tick_spacing: int | None
    hooks: str | None
    sqrt_price_x96: str | None
    tick: int | None
    block_number: int
    ts: int | None


@dataclass
class V4LiquidityRow:
    tx_hash: str
    log_index: int
    pool_id: str
    sender: str
    tick_lower: int
    tick_upper: int
    liquidity_delta: str
    salt: str
    block_number: int
    ts: int | None


@dataclass
class V4EventRow:
    kind: str
    tx_hash: str
    log_index: int
    pool_id: str
    sender: str
    amount0: str
    amount1: str
    block_number: int
    ts: int | None


@dataclass
class ProcessResult:
    swaps: int = 0
    tokens: int = 0
    dev_buys: int = 0
    launchpad_events: int = 0
    pools_v4: int = 0
    transfers: int = 0
    duplicates: int = 0
    wallets_touched: int = 0
