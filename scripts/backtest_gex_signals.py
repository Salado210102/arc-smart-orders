#!/usr/bin/env python3
"""Backtest GEX (Gamma Exposure) signals and translate them into Arc Smart Order intents.

Simulates a price series and dealer-positioning levels — **Call Wall**, **Put Wall** and **Zero Gamma** —
generates signals when price crosses / bounces at a wall, and, for every signal, builds the corresponding
**EIP-712 LIMIT intent** (Permit2 witness) with a signed ``minOut`` and an expected return, then simulates
the trade outcome.

Pure standard library (no deps). If ``eth-account`` + the Python SDK are available and ``--key`` is given,
the generated intents are actually signed (off-chain, 0 gas).

    python scripts/backtest_gex_signals.py --steps 600 --seed 7
    python scripts/backtest_gex_signals.py --key 0x... --out scripts/backtest_gex_signals.json
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple

# --- optional: use the repo's Python SDK for signing / constants ---
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sdk", "python"))
try:
    import arc_smart_orders as sdk  # type: ignore

    HAVE_SDK = True
except Exception:  # pragma: no cover - SDK optional
    sdk = None
    HAVE_SDK = False

# Constants (fallbacks if the SDK is not importable).
CHAIN_ID = getattr(sdk, "ARC_MAINNET_CHAIN_ID", 5042) if HAVE_SDK else 5042
USDC = getattr(sdk, "USDC", "0x3600000000000000000000000000000000000000") if HAVE_SDK else "0x3600000000000000000000000000000000000000"
EURC = "0xbEf5f6d51CB62b58e6A8f77868681825C6fe21c1"
EXECUTOR = "0x9b3a990d1a31Ff5E01ddB8702e10F2529811FDb7"
PERMIT2 = "0x000000000022D473030F116dDEE9F6B43aC78BA3"

WITNESS_TYPES = {
    "PermitWitnessTransferFrom": [
        {"name": "permitted", "type": "TokenPermissions"},
        {"name": "spender", "type": "address"},
        {"name": "nonce", "type": "uint256"},
        {"name": "deadline", "type": "uint256"},
        {"name": "witness", "type": "OrderIntent"},
    ],
    "TokenPermissions": [
        {"name": "token", "type": "address"},
        {"name": "amount", "type": "uint256"},
    ],
    "OrderIntent": [
        {"name": "tokenOut", "type": "address"},
        {"name": "minOut", "type": "uint256"},
    ],
}


# --------------------------------------------------------------------------- models
@dataclass
class GexLevels:
    spot: float
    put_wall: float
    call_wall: float
    zero_gamma: float
    regime: str  # "positive" | "negative"


@dataclass
class Signal:
    idx: int
    kind: str  # BUY_SUPPORT | SELL_RESISTANCE | BUY_BREAKOUT | SELL_BREAKDOWN
    side: str  # BUY | SELL
    levels: GexLevels
    entry: float
    target: float
    stop: float


# --------------------------------------------------------------------------- simulation
def simulate_prices(start: float, steps: int, vol: float, seed: int) -> List[float]:
    """Mean-reverting random walk (deterministic for a given seed)."""
    rng = random.Random(seed)
    px = [start]
    anchor = start
    for _ in range(steps):
        reversion = 0.08 * (anchor - px[-1]) / anchor
        shock = rng.gauss(0.0, vol)
        nxt = px[-1] * (1.0 + reversion + shock)
        px.append(max(0.05, nxt))
    return px


def gex_levels(spot: float, anchor: float) -> GexLevels:
    """Dealer levels: walls ~1% around the anchor, Zero Gamma between them."""
    put = round((anchor * 0.99) / 0.001) * 0.001
    call = round((anchor * 1.01) / 0.001) * 0.001
    zero = (put + call) / 2.0
    regime = "positive" if spot > zero else "negative"
    return GexLevels(spot=spot, put_wall=put, call_wall=call, zero_gamma=zero, regime=regime)


def detect_signal(px: List[float], i: int, anchor: float) -> Optional[Signal]:
    """Signal rules around the walls / zero gamma (fade touches, follow breakouts)."""
    prev, cur = px[i - 1], px[i]
    lv = gex_levels(cur, anchor)
    band = 0.0015 * anchor

    # fade: bounce off support / reject at resistance (mean-revert to Zero Gamma)
    if prev > lv.put_wall and cur <= lv.put_wall + band:
        return Signal(i, "BUY_SUPPORT", "BUY", lv, cur, lv.zero_gamma, lv.put_wall - band)
    if prev < lv.call_wall and cur >= lv.call_wall - band:
        return Signal(i, "SELL_RESISTANCE", "SELL", lv, cur, lv.zero_gamma, lv.call_wall + band)
    # trend: breakout / breakdown through a wall
    if prev <= lv.call_wall and cur > lv.call_wall + band:
        return Signal(i, "BUY_BREAKOUT", "BUY", lv, cur, lv.call_wall + 3 * band, lv.call_wall - band)
    if prev >= lv.put_wall and cur < lv.put_wall - band:
        return Signal(i, "SELL_BREAKDOWN", "SELL", lv, cur, lv.put_wall - 3 * band, lv.put_wall + band)
    return None


def simulate_trade(px: List[float], sig: Signal, horizon: int) -> Tuple[float, float, int]:
    """Return ``(realized_return, exit_price, exit_idx)``."""
    entry = sig.entry
    end = min(len(px), sig.idx + 1 + horizon)
    for j in range(sig.idx + 1, end):
        p = px[j]
        if sig.side == "BUY":
            if p >= sig.target:
                return (sig.target - entry) / entry, sig.target, j
            if p <= sig.stop:
                return (p - entry) / entry, p, j
        else:
            if p <= sig.target:
                return (entry - sig.target) / entry, sig.target, j
            if p >= sig.stop:
                return (entry - p) / entry, p, j
    exit_p = px[end - 1]
    ret = (exit_p - entry) / entry if sig.side == "BUY" else (entry - exit_p) / entry
    return ret, exit_p, end - 1


# --------------------------------------------------------------------------- order construction
def build_limit_intent(sig: Signal, amount_in_usdc: float, slip: float, fee: float, nonce: int, deadline: int) -> Dict[str, Any]:
    """Build the Permit2-witness EIP-712 intent + minOut for a signal."""
    amount_in = int(round(amount_in_usdc * 1e6))
    # expected EURC out from the entry price, then a signed minimum after fee + slippage.
    expected_out = amount_in_usdc * sig.entry * (1.0 - fee)
    min_out = int(round(expected_out * (1.0 - slip) * 1e6))
    message = {
        "permitted": {"token": USDC, "amount": amount_in},
        "spender": EXECUTOR,
        "nonce": nonce,
        "deadline": deadline,
        "witness": {"tokenOut": EURC, "minOut": min_out},
    }
    full = {
        "primaryType": "PermitWitnessTransferFrom",
        "domain": {"name": "Permit2", "chainId": CHAIN_ID, "verifyingContract": PERMIT2},
        "types": WITNESS_TYPES,
        "message": message,
    }
    return {
        "type": "LIMIT",
        "tokenIn": USDC,
        "tokenOut": EURC,
        "amountIn": str(amount_in),
        "minOut": str(min_out),
        "rate": round(sig.entry, 6),
        "nonce": str(nonce),
        "deadline": deadline,
        "typedData": full,
    }


def maybe_sign(intent: Dict[str, Any], key: Optional[str]) -> Optional[str]:
    if not key:
        return None
    if not HAVE_SDK:
        raise SystemExit("--key given but the Python SDK / eth-account is not importable")
    msg = intent["typedData"]["message"]
    sig, _ = sdk.sign_limit_order(  # type: ignore[union-attr]
        key,
        chain_id=CHAIN_ID,
        spender=EXECUTOR,
        token_in=USDC,
        token_out=EURC,
        amount_in=int(msg["permitted"]["amount"]),
        min_out=int(msg["witness"]["minOut"]),
        nonce=int(msg["nonce"]),
        deadline=int(msg["deadline"]),
    )
    return sig


# --------------------------------------------------------------------------- runner
def run(args: argparse.Namespace) -> Dict[str, Any]:
    px = simulate_prices(args.start, args.steps, args.vol, args.seed)
    anchor = args.start
    horizon = args.horizon
    fee = 0.003  # 0.30% platform fee (input side)
    slip = args.slip
    base_deadline = int(1_790_000_000)

    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    trades: List[Dict[str, Any]] = []

    for i in range(1, len(px)):
        sig = detect_signal(px, i, anchor)
        if not sig:
            continue
        realized, exit_p, exit_i = simulate_trade(px, sig, horizon)
        intent = build_limit_intent(sig, args.notional, slip, fee, nonce=i, deadline=base_deadline + i * 60)
        signature = maybe_sign(intent, args.key)

        equity *= 1.0 + realized
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak)

        expected_return = (sig.target - sig.entry) / sig.entry if sig.side == "BUY" else (sig.entry - sig.target) / sig.entry
        trades.append(
            {
                "idx": sig.idx,
                "kind": sig.kind,
                "side": sig.side,
                "regime": sig.levels.regime,
                "spot": round(sig.entry, 6),
                "put_wall": sig.levels.put_wall,
                "call_wall": sig.levels.call_wall,
                "zero_gamma": sig.levels.zero_gamma,
                "target": round(sig.target, 6),
                "stop": round(sig.stop, 6),
                "expected_return": round(expected_return, 6),
                "realized_return": round(realized, 6),
                "exit": round(exit_p, 6),
                "exit_idx": exit_i,
                "order": intent,
                "signature": signature,
            }
        )

    returns = [t["realized_return"] for t in trades]
    wins = [r for r in returns if r > 0]
    buys = [t for t in trades if t["side"] == "BUY"]
    sells = [t for t in trades if t["side"] == "SELL"]
    summary = {
        "params": asdict(args) if hasattr(args, "__dataclass_fields__") else vars(args),
        "signals": len(trades),
        "buys": len(buys),
        "sells": len(sells),
        "wins": len(wins),
        "win_rate": round(len(wins) / len(trades), 4) if trades else 0.0,
        "avg_return": round(sum(returns) / len(returns), 6) if returns else 0.0,
        "total_return": round(equity - 1.0, 6),
        "max_drawdown": round(max_dd, 6),
        "signed": bool(args.key),
        "sdk_available": HAVE_SDK,
    }
    return {"summary": summary, "trades": trades}


def print_report(result: Dict[str, Any]) -> None:
    s = result["summary"]
    print("=" * 68)
    print("GEX signal backtest - Arc Smart Orders (EIP-712 LIMIT intents)")
    print("=" * 68)
    print(f"signals       : {s['signals']}  (buys {s['buys']} / sells {s['sells']})")
    print(f"win rate      : {s['win_rate'] * 100:.1f}%  ({s['wins']}/{s['signals']})")
    print(f"avg return    : {s['avg_return'] * 100:.3f}% per trade")
    print(f"total return  : {s['total_return'] * 100:.3f}%  (compounded)")
    print(f"max drawdown  : {s['max_drawdown'] * 100:.3f}%")
    print(f"signed        : {s['signed']}  |  sdk: {s['sdk_available']}")
    print("-" * 68)
    if result["trades"]:
        t = result["trades"][0]
        print("example intent:")
        print(json.dumps({k: t[k] for k in ("idx", "kind", "side", "spot", "put_wall", "call_wall", "zero_gamma")}, indent=2))
        o = t["order"]
        print(
            f"  LIMIT {o['tokenIn'][:8]}..->{o['tokenOut'][:8]}..  amountIn={o['amountIn']}  minOut={o['minOut']}  "
            f"rate={o['rate']}  nonce={o['nonce']}"
        )
        if t["signature"]:
            print(f"  signature: {t['signature'][:34]}..")


def main() -> int:
    ap = argparse.ArgumentParser(description="Backtest GEX signals -> Arc Smart Order intents.")
    ap.add_argument("--steps", type=int, default=600)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--start", type=float, default=1.0, help="starting price (EURC per USDC)")
    ap.add_argument("--vol", type=float, default=0.004, help="per-step volatility")
    ap.add_argument("--notional", type=float, default=100.0, help="USDC per order")
    ap.add_argument("--slip", type=float, default=0.01, help="slippage buffer (fraction)")
    ap.add_argument("--horizon", type=int, default=25, help="max bars to hold")
    ap.add_argument("--key", default=os.environ.get("ARC_PK"), help="optional private key to sign intents")
    ap.add_argument("--out", default="", help="write the full result JSON to this path")
    args = ap.parse_args()

    result = run(args)
    print_report(result)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
