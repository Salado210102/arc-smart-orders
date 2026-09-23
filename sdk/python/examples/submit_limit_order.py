#!/usr/bin/env python3
"""Example: sign a LIMIT order (USDC -> EURC) and submit it to the keeper API.

    pip install -e ./sdk/python            # or: pip install eth-account
    export ARC_PK=0x...                    # the order owner's private key
    export KEEPER_API=http://127.0.0.1:8788
    python sdk/python/examples/submit_limit_order.py

Flags:
    --amount 1.0        # USDC to sell
    --min-out 0.90      # minimum EURC to receive (the limit)
    --testnet           # use Arc testnet (5042002)
    --approve           # send the one-time Permit2 approval if needed
    --no-submit         # only build + sign, print the payload (do not POST)
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from arc_smart_orders import ARC_TESTNET_CHAIN_ID, ArcSmartOrdersClient, to_units  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Submit an Arc Smart Order (LIMIT USDC->EURC).")
    ap.add_argument("--amount", default="1.0", help="USDC amount to sell (default 1.0)")
    ap.add_argument("--min-out", default="0.90", help="minimum EURC out (default 0.90)")
    ap.add_argument("--testnet", action="store_true", help="use Arc testnet")
    ap.add_argument("--approve", action="store_true", help="send the one-time Permit2 approval if needed")
    ap.add_argument("--no-submit", action="store_true", help="build + sign only (do not POST)")
    args = ap.parse_args()

    pk = os.environ.get("ARC_PK")
    if not pk:
        print("✗ set ARC_PK (the order owner's private key)", file=sys.stderr)
        return 1

    chain_id = ARC_TESTNET_CHAIN_ID if args.testnet else 5042
    client = ArcSmartOrdersClient(
        private_key=pk,
        chain_id=chain_id,
        keeper_url=os.environ.get("KEEPER_API"),
    )

    amount_in = to_units(args.amount)
    min_out = to_units(args.min_out)

    print("owner    :", client.address)
    print("executor :", client.executor)
    print("tokenIn  :", client.token_in)
    print("tokenOut :", client.token_out)
    print("balance  :", client.usdc_balance(), "USDC (base units)")
    print("allowance:", client.permit2_allowance(), "(Permit2)")

    if args.approve:
        tx = client.ensure_permit2_approval()
        print("approve  :", tx or "already approved")

    if args.no_submit:
        signed = client.sign_limit_order(amount_in=amount_in, min_out=min_out)
        payload = client.build_order_payload(
            amount_in=amount_in,
            min_out=min_out,
            nonce=signed["nonce"],
            deadline=signed["deadline"],
            signature=signed["signature"],
        )
        print("payload  :")
        print(json.dumps(payload, indent=2))
        return 0

    resp = client.submit_limit_order(amount_in=amount_in, min_out=min_out)
    order = resp.get("order", resp)
    order_id = order.get("id")
    print("submitted:", json.dumps(resp, indent=2))

    if order_id:
        print("waiting for fill…")
        final = client.wait_for_fill(order_id, timeout=180, interval=3)
        print("status   :", final.get("status"), "· tx", final.get("fill_tx"))
        return 0 if str(final.get("status", "")).upper() == "FILLED" else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
