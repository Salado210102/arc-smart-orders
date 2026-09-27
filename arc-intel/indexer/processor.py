"""EventProcessor: turn RawEvents into normalized rows. Source-agnostic.

Honest scope: without the launchpad ABI we cannot name/decode TokenCreated/DevBuy, so
launchpad events are captured raw (event_name=None) and tokens/dev_buys stay empty until
the ABI is supplied. Swap decoding is minimal (amounts/sqrt/tick); token & side are not
fabricated when pool orientation/decimals are unknown.
"""
from __future__ import annotations

from typing import Callable

from .config import LaunchpadConfig, TRANSFER_TOPIC0, UNISWAP_V2_SWAP_TOPIC0, UNISWAP_V3_SWAP_TOPIC0, V4_DONATE_TOPIC0, V4_SWAP_TOPIC0
from .models import DevBuyRow, LaunchpadEventRow, PoolV4Row, ProcessResult, RawEvent, SwapRow, TokenRow, TokenTransferRow, V4EventRow
from .storage import Storage

TokenResolver = Callable[[str], tuple[str, str] | None]


def _words(data: str) -> list[str]:
    d = data[2:] if data.startswith("0x") else data
    return [d[i:i + 64] for i in range(0, len(d), 64)]


def _to_signed(v: int, bits: int) -> int:
    mod = 1 << bits
    half = mod >> 1
    return v - mod if v >= half else v


def _topic_address(topic: str) -> str:
    return "0x" + topic[-40:].lower()


def decode_v3_swap(log: RawEvent) -> dict:
    w = _words(log.data)
    if len(w) < 5:
        return {}
    return {
        "amount0": str(_to_signed(int(w[0], 16), 256)),
        "amount1": str(_to_signed(int(w[1], 16), 256)),
        "sqrt_price_x96": str(int(w[2], 16)),
        "liquidity": str(int(w[3], 16)),
        # tick is int24 sign-extended to a full 32-byte word (M0.8.2 fix)
        "tick": _to_signed(int(w[4], 16), 256),
        "sender": _topic_address(log.topics[1]) if len(log.topics) > 1 else None,
        "recipient": _topic_address(log.topics[2]) if len(log.topics) > 2 else None,
    }


def decode_v2_swap(log: RawEvent) -> dict:
    w = _words(log.data)
    if len(w) < 4:
        return {}
    return {
        "amount0_in": str(int(w[0], 16)),
        "amount1_in": str(int(w[1], 16)),
        "amount0_out": str(int(w[2], 16)),
        "amount1_out": str(int(w[3], 16)),
        "sender": _topic_address(log.topics[1]) if len(log.topics) > 1 else None,
    }


def _abi_string(words: list[str], slot: int) -> str | None:
    """Decode a dynamic string ABI parameter located at head slot `slot`."""
    if slot >= len(words):
        return None
    try:
        offset_words = int(words[slot], 16) // 32
        if offset_words >= len(words):
            return None
        length = int(words[offset_words], 16)
        body = "".join(words[offset_words + 1: offset_words + 1 + (length + 31) // 32])
        return bytes.fromhex(body[: length * 2]).decode("utf-8", errors="replace").replace("\x00", "")
    except Exception:
        return None


def decode_token_created(log: RawEvent) -> dict:
    """Argus TokenCreated (v4): topics [sig, token, creator]; data:
    (string name, string symbol, bytes32 poolId, string imageURI, string website,
     string twitter, string telegram)."""
    if len(log.topics) < 3:
        return {}
    w = _words(log.data)
    if len(w) < 7:
        return {}
    return {
        "token": _topic_address(log.topics[1]),
        "creator": _topic_address(log.topics[2]),
        "name": _abi_string(w, 0),
        "symbol": _abi_string(w, 1),
        "pool_id": "0x" + w[2],
        "image_uri": _abi_string(w, 3),
        "website": _abi_string(w, 4),
        "twitter": _abi_string(w, 5),
        "telegram": _abi_string(w, 6),
    }


def decode_initialize(log: RawEvent) -> dict:
    """Uniswap v4 Initialize: topics [sig, poolId, currency0, currency1]; data:
    (uint24 fee, int24 tickSpacing, address hooks, uint160 sqrtPriceX96, int24 tick)."""
    if len(log.topics) < 4:
        return {}
    w = _words(log.data)
    if len(w) < 5:
        return {}
    return {
        "pool_id": log.topics[1].lower(),
        "currency0": _topic_address(log.topics[2]),
        "currency1": _topic_address(log.topics[3]),
        "fee": int(w[0], 16),
        "tick_spacing": _to_signed(int(w[1], 16), 256),
        "hooks": _topic_address(w[2]),
        "sqrt_price_x96": str(int(w[3], 16)),
        "tick": _to_signed(int(w[4], 16), 256),
    }


def decode_donate(log: RawEvent) -> dict:
    """Uniswap v4 Donate: topics [sig, poolId, sender]; data: (uint256 amount0, uint256 amount1)."""
    if len(log.topics) < 3:
        return {}
    w = _words(log.data)
    if len(w) < 2:
        return {}
    return {
        "pool_id": log.topics[1].lower(),
        "sender": _topic_address(log.topics[2]),
        "amount0": str(int(w[0], 16)),
        "amount1": str(int(w[1], 16)),
    }


def decode_modify_liquidity(log: RawEvent) -> dict:
    """Uniswap v4 ModifyLiquidity: topics [sig, poolId, sender]; data:
    (int24 tickLower, int24 tickUpper, int256 liquidityDelta, bytes32 salt)."""
    if len(log.topics) < 3:
        return {}
    w = _words(log.data)
    if len(w) < 4:
        return {}
    return {
        "pool_id": log.topics[1].lower(),
        "sender": _topic_address(log.topics[2]),
        "tick_lower": _to_signed(int(w[0], 16), 256),
        "tick_upper": _to_signed(int(w[1], 16), 256),
        "liquidity_delta": str(_to_signed(int(w[2], 16), 256)),
        "salt": "0x" + w[3],
    }


def decode_v4_swap(log: RawEvent) -> dict:
    """Uniswap v4 Swap: topics [sig, poolId, sender]; data:
    (int128 amount0, int128 amount1, uint160 sqrtPriceX96, uint128 liquidity, int24 tick, uint24 fee)."""
    if len(log.topics) < 3:
        return {}
    w = _words(log.data)
    if len(w) < 6:
        return {}
    return {
        "pool_id": log.topics[1].lower(),
        "sender": _topic_address(log.topics[2]),
        "amount0": str(_to_signed(int(w[0], 16), 256)),
        "amount1": str(_to_signed(int(w[1], 16), 256)),
        "sqrt_price_x96": str(int(w[2], 16)),
        "liquidity": str(int(w[3], 16)),
        "tick": _to_signed(int(w[4], 16), 256),
        "fee": int(w[5], 16),
    }


class EventProcessor:
    def __init__(
        self,
        storage: Storage,
        launchpads: list[LaunchpadConfig],
        token_resolver: TokenResolver | None = None,
    ):
        self.storage = storage
        self.topic_maps = {lp.name: lp.topic_map for lp in launchpads}
        self.token_resolver = token_resolver

    def process(self, ev: RawEvent) -> ProcessResult:
        res = ProcessResult()
        if ev.kind == "dex_swap":
            self._process_swap(ev, res)
        elif ev.kind == "launchpad":
            self._process_launchpad(ev, res)
        elif ev.kind == "pool_init":
            self._process_pool_init(ev, res)
        elif ev.kind == "token_transfer":
            self._process_transfer(ev, res)
        elif ev.kind == "v4_donate":
            self._process_v4_donate(ev, res)
        return res

    def _process_v4_donate(self, ev: RawEvent, res: ProcessResult) -> None:
        d = decode_donate(ev)
        if not d:
            return
        row = V4EventRow(
            kind="Donate", tx_hash=ev.tx_hash, log_index=ev.log_index, pool_id=d["pool_id"],
            sender=d["sender"], amount0=d["amount0"], amount1=d["amount1"],
            block_number=ev.block_number, ts=ev.block_time,
        )
        if self.storage.insert_v4_event(row):
            pass
        else:
            res.duplicates += 1

    def _process_transfer(self, ev: RawEvent, res: ProcessResult) -> None:
        topic0 = ev.topics[0].lower() if ev.topics else ""
        if topic0 != TRANSFER_TOPIC0 or len(ev.topics) < 3:
            return
        value = str(int(ev.data, 16)) if ev.data and ev.data != "0x" else "0"
        row = TokenTransferRow(
            tx_hash=ev.tx_hash, log_index=ev.log_index, token=ev.address,
            from_addr=_topic_address(ev.topics[1]), to_addr=_topic_address(ev.topics[2]),
            value=value, block_number=ev.block_number, ts=ev.block_time,
        )
        if self.storage.insert_token_transfer(row):
            res.transfers += 1
        else:
            res.duplicates += 1

    def _process_swap(self, ev: RawEvent, res: ProcessResult) -> None:
        topic0 = ev.topics[0].lower() if ev.topics else ""
        token: str | None = None
        pool_field: str = ev.address
        if topic0 == UNISWAP_V3_SWAP_TOPIC0:
            decoded = decode_v3_swap(ev)
            amount_in, amount_out = decoded.get("amount0"), decoded.get("amount1")
        elif topic0 == UNISWAP_V2_SWAP_TOPIC0:
            decoded = decode_v2_swap(ev)
            amount_in, amount_out = decoded.get("amount0_in"), decoded.get("amount0_out")
        elif topic0 == V4_SWAP_TOPIC0:
            decoded = decode_v4_swap(ev)
            amount_in, amount_out = decoded.get("amount0"), decoded.get("amount1")
            pool_id = decoded.get("pool_id")
            pool_field = pool_id or ev.address
            # Resolve the pair via pools_v4 (Initialize). Use currency0 unless it is the
            # native/zero address, in which case currency1.
            if pool_id:
                p = self.storage.get_pool_v4(pool_id)
                if p:
                    c0 = (p.get("currency0") or "").lower()
                    c1 = (p.get("currency1") or "").lower()
                    token = c0 if c0 and c0 != "0x" + "0" * 40 else c1
        else:
            return
        wallet = decoded.get("sender")
        row = SwapRow(
            tx_hash=ev.tx_hash, log_index=ev.log_index, block_number=ev.block_number,
            ts=ev.block_time, token=token, wallet=wallet, side="unknown",
            amount_in=amount_in, amount_out=amount_out, price_implied=None,
            dex=ev.dex, pool=pool_field,
        )
        if self.storage.insert_swap(row):
            res.swaps += 1
        else:
            res.duplicates += 1
        if wallet:
            self.storage.upsert_wallet(wallet, ev.block_time)
            res.wallets_touched += 1
        # v3/v2 only: real token rows via an optional pool->token0/token1 resolver.
        if self.token_resolver and topic0 != V4_SWAP_TOPIC0:
            pair = self.token_resolver(ev.address)
            if pair:
                for t in pair:
                    if self.storage.insert_token(TokenRow(address=t, pool_id=ev.address)):
                        res.tokens += 1

    def _process_pool_init(self, ev: RawEvent, res: ProcessResult) -> None:
        d = decode_initialize(ev)
        if not d:
            return
        row = PoolV4Row(
            pool_id=d["pool_id"], currency0=d["currency0"], currency1=d["currency1"],
            fee=d.get("fee"), tick_spacing=d.get("tick_spacing"), hooks=d.get("hooks"),
            sqrt_price_x96=d.get("sqrt_price_x96"), tick=d.get("tick"),
            block_number=ev.block_number, ts=ev.block_time,
        )
        if self.storage.insert_pool_v4(row):
            res.pools_v4 += 1
        else:
            res.duplicates += 1


    def _process_launchpad(self, ev: RawEvent, res: ProcessResult) -> None:
        topic0 = ev.topics[0].lower() if ev.topics else ""
        event_name = self.topic_maps.get(ev.launchpad or "", {}).get(topic0)
        token: str | None = None
        if event_name == "TokenCreated":
            d = decode_token_created(ev)
            token = d.get("token")
            if token and self.storage.insert_token(TokenRow(
                address=token, symbol=d.get("symbol"), name=d.get("name"),
                creator=d.get("creator"), launchpad=ev.launchpad,
                created_ts=ev.block_time, pool_id=d.get("pool_id"),
            )):
                res.tokens += 1
        elif event_name in ("CurveOpened", "PartsDeployed") and len(ev.topics) > 1:
            token = _topic_address(ev.topics[1])
        row = LaunchpadEventRow(
            tx_hash=ev.tx_hash, log_index=ev.log_index, launchpad=ev.launchpad or "unknown",
            event_name=event_name, topic0=topic0, token=token, address=ev.address,
            block_number=ev.block_number, ts=ev.block_time, topics=ev.topics, data=ev.data,
        )
        if self.storage.insert_launchpad_event(row):
            res.launchpad_events += 1
        else:
            res.duplicates += 1
