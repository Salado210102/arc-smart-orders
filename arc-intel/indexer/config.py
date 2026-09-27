"""Configuration for the Arc indexer (env-driven, no secrets in code)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class LaunchpadConfig:
    name: str
    address: str
    # topic0 -> canonical event name. Empty until the launchpad ABI is supplied.
    # Adding a launchpad = add an entry here (address + topic map); no pipeline change.
    topic_map: dict[str, str] = field(default_factory=dict)


@dataclass
class Config:
    rpc_url: str
    chain_id: int
    db_path: str
    log_path: str
    poll_seconds: int
    max_range_blocks: int
    launchpads: list[LaunchpadConfig]
    bitquery_oauth: str | None


# Known Arc mainnet addresses (verified on-chain in this session).
ARGUS_PORTAL = "0xb021be536808f551b31789422fd28a6c9c6e97da"

# Uniswap V3 Swap event topic0 (verified decoder in arcai/ M0.8.2).
UNISWAP_V3_SWAP_TOPIC0 = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"
# Uniswap V2 Swap event topic0.
UNISWAP_V2_SWAP_TOPIC0 = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"

# ERC-20 Transfer (standard).
TRANSFER_TOPIC0 = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

# Uniswap V4 PoolManager (singleton) + events, confirmed via official Uniswap/v4-core
# signatures and keccak256 (cross-checked against the real BTS launch tx).
POOLMANAGER_V4 = "0x8366a39cc670b4001a1121b8f6a443a643e40951"
V4_INITIALIZE_TOPIC0 = "0xdd466e674ea557f56295e2d0218a125ea4b4f0f6f3307b95f85e6110838d6438"
V4_MODIFYLIQUIDITY_TOPIC0 = "0xf208f4912782fd25c7f114ca3723a2d5dd6f3bcc3ac8db5af63baa85f711d5ec"
V4_SWAP_TOPIC0 = "0x40e9cecb9f5f1f1c5b9c97dec2917b7ee92e57ba5563708daca94dd84ad7112f"
V4_DONATE_TOPIC0 = "0x29ef05caaff9404b7cb6d1c0e9bbae9eaa7ab2541feba1a9c4248594c08156cb"


def default_launchpads() -> list[LaunchpadConfig]:
    """Argus topic map comes from the OFFICIAL repo (arguspad/argus-world,
    onchain/event-signatures.md) and was cross-checked with keccak256.

    Source confidence: official GitHub repo (NOT explorer-verified: the Arc
    Blockscout API is Cloudflare-blocked from this environment).
    """
    argus_topics = {
        "0x1d8917231579f8ce39407f0d616f36f357b07329b0ce5164d0754ac15145ce0a": "TokenCreated",
        "0xa54419a494ae20a1807712ab7a33ff0928b9a0e6e03e4562885aedb8e8fcd4da": "PartsDeployed",
        "0x55e45784ac0f1201c142dd0d2119dd11980e98f34cb682c49340d5c28c3a9aa0": "CurveOpened",
    }
    return [
        LaunchpadConfig(name="argus", address=ARGUS_PORTAL, topic_map=argus_topics),
    ]


def load_config(env: dict[str, str] | None = None) -> Config:
    e = env if env is not None else dict(os.environ)
    return Config(
        rpc_url=e.get("ARC_RPC", "https://rpc.mainnet.arc.io"),
        chain_id=int(e.get("ARC_CHAIN_ID", "5042")),
        db_path=e.get("INDEXER_DB", "arc_indexer.db"),
        log_path=e.get("INDEXER_LOG", "arc_indexer.log"),
        poll_seconds=int(e.get("INDEXER_POLL_SECONDS", "5")),
        max_range_blocks=int(e.get("INDEXER_MAX_RANGE", "200")),
        launchpads=default_launchpads(),
        bitquery_oauth=e.get("BITQUERY_OAUTH"),
    )
