"""Buy (purchase) quoting for the Mini App. Pure, testable.

The executor is direction-agnostic: a BUY is the same `execute` with `token_in` = the stable
(USDC) and `tokenOut` = the token. This module:
- resolves which pool currency is the stable,
- computes the expected token out and the `minOut` floor from the current price + slippage,
- assembles the exact signed payload (via `execution.preorders.build_sign_payload`, the single
  source of truth shared with the signing UX and the keeper).

No persistence, no network, no signing here.
"""
from __future__ import annotations

from .preorders import build_sign_payload

STABLE_DECIMALS = 6  # USDC on Arc


def stable_side(pool: dict, stable: str) -> tuple[bool, bool]:
    """Return (zero_for_one, token_is_currency0) for a BUY paying with `stable`.

    zero_for_one=True means currency0 is the input side, i.e. stable == currency0.
    Raises ValueError if the stable is not one of the pool's currencies.
    """
    c0 = (pool.get("currency0") or "").lower()
    c1 = (pool.get("currency1") or "").lower()
    s = (stable or "").lower()
    if s == c0:
        return True, False    # stable = currency0 -> token = currency1
    if s == c1:
        return False, True    # stable = currency1 -> token = currency0
    raise ValueError("stable_not_in_pool")


def buy_quote(*, amount_in_base: int, token_price: float, token_decimals: int,
              slippage_pct: float) -> dict:
    """Expected token out and `minOut` floor, both in token base units."""
    if int(amount_in_base) <= 0:
        raise ValueError("bad_amount")
    if float(token_price) <= 0:
        raise ValueError("bad_price")
    amount_usd = int(amount_in_base) / (10 ** STABLE_DECIMALS)
    token_qty = amount_usd / float(token_price)
    min_qty = token_qty * max(0.0, 1.0 - float(slippage_pct) / 100.0)
    scale = 10 ** int(token_decimals)
    return {
        "amount_in_base": int(amount_in_base),
        "expected_out": token_qty,
        "expected_out_base": int(token_qty * scale),
        "min_out": min_qty,
        "min_out_base": int(min_qty * scale),
        "slippage_pct": float(slippage_pct),
    }


def build_buy_payload(*, chain_id: int, executor: str, pool: dict, stable: str,
                      amount_in_base: int, min_out_base: int, recipient: str,
                      order_nonce: int, permit_nonce: int, deadline: int) -> dict:
    """Assemble the exact EIP-712 payload the wallet signs to buy `token` with `stable`."""
    stable_side(pool, stable)  # validates the stable is in the pool (raises otherwise)
    return build_sign_payload(
        chain_id=int(chain_id), executor=executor, pool_id=pool["pool_id"],
        currency0=pool["currency0"], currency1=pool["currency1"], fee=int(pool["fee"]),
        tick_spacing=int(pool["tick_spacing"]), hooks=pool["hooks"], token_in=stable,
        amount_in=int(amount_in_base), min_out=int(min_out_base), recipient=recipient,
        order_nonce=int(order_nonce), permit_nonce=int(permit_nonce), deadline=int(deadline))
