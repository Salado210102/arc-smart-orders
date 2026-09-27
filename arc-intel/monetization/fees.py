"""Phase 7 — monetization math (pure): 1% standard fee + USDC cashback.

Arc is USDC-denominated, so cashback is paid in USDC (not a volatile native token).
Splits a fee into a user cashback (rewards) share and treasury share.
"""
from __future__ import annotations

DEFAULT_FEE_BPS = 100          # 1% standard, in basis points
DEFAULT_REWARD_SHARE_BPS = 5000  # 50% of the fee returned as USDC cashback


def fee_amount(notional_usdc: float, fee_bps: int = DEFAULT_FEE_BPS) -> float:
    if notional_usdc < 0:
        raise ValueError("notional_must_be_non_negative")
    if fee_bps < 0 or fee_bps > 10_000:
        raise ValueError("fee_bps_out_of_range")
    return notional_usdc * fee_bps / 10_000.0


def split_fee(fee: float, reward_share_bps: int = DEFAULT_REWARD_SHARE_BPS) -> dict:
    if reward_share_bps < 0 or reward_share_bps > 10_000:
        raise ValueError("reward_share_bps_out_of_range")
    rewards = fee * reward_share_bps / 10_000.0
    return {"rewards_usdc": rewards, "treasury_usdc": fee - rewards}


def round_trip_fee(notional_usdc: float, fee_bps: int = DEFAULT_FEE_BPS) -> float:
    """Fees on a buy then sell of the same notional."""
    return 2 * fee_amount(notional_usdc, fee_bps)


def net_buy_cost(notional_usdc: float, fee_bps: int = DEFAULT_FEE_BPS,
                 reward_share_bps: int = DEFAULT_REWARD_SHARE_BPS) -> dict:
    fee = fee_amount(notional_usdc, fee_bps)
    sp = split_fee(fee, reward_share_bps)
    return {"gross_usdc": notional_usdc, "fee_usdc": fee,
            "cashback_usdc": sp["rewards_usdc"], "net_usdc": notional_usdc + fee - sp["rewards_usdc"]}
