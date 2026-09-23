"""Signing tests — verify the SDK produces valid, recoverable EIP-712 signatures.

Run:  python sdk/python/tests/test_signing.py   (or: pytest sdk/python/tests)
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from eth_account import Account  # noqa: E402
from eth_account.messages import encode_typed_data  # noqa: E402

from arc_smart_orders import (  # noqa: E402
    ARC_TESTNET_CHAIN_ID,
    USDC,
    digest,
    eurc_for,
    executor_for,
    sign_limit_order,
    sign_twap_order,
)

# Well-known test key (anvil #1) — the same one used by examples/python/sign_limit_order.py.
PK = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
OWNER = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"


def test_limit_signature_recovers_owner() -> None:
    chain_id = ARC_TESTNET_CHAIN_ID
    sig, full = sign_limit_order(
        PK,
        chain_id=chain_id,
        spender=executor_for(chain_id),
        token_in=USDC,
        token_out=eurc_for(chain_id),
        amount_in=1_000_000,
        min_out=900_000,
        nonce=2,
        deadline=1_790_000_000,
    )
    assert sig.startswith("0x") and len(sig) == 132
    recovered = Account.recover_message(encode_typed_data(full_message=full), signature=sig)
    assert recovered == OWNER
    assert Account.from_key(PK).address == OWNER


def test_digest_is_deterministic() -> None:
    chain_id = ARC_TESTNET_CHAIN_ID
    _, full_a = sign_limit_order(
        PK, chain_id=chain_id, spender=executor_for(chain_id), token_in=USDC,
        token_out=eurc_for(chain_id), amount_in=1_000_000, min_out=900_000, nonce=2, deadline=1_790_000_000,
    )
    _, full_b = sign_limit_order(
        PK, chain_id=chain_id, spender=executor_for(chain_id), token_in=USDC,
        token_out=eurc_for(chain_id), amount_in=1_000_000, min_out=900_000, nonce=2, deadline=1_790_000_000,
    )
    assert digest(full_a) == digest(full_b)


def test_twap_signatures_recover_owner() -> None:
    chain_id = ARC_TESTNET_CHAIN_ID
    permit_sig, intent_sig, permit_full, intent_full = sign_twap_order(
        PK,
        chain_id=chain_id,
        spender=executor_for(chain_id),
        token_in=USDC,
        token_out=eurc_for(chain_id),
        max_amount_in=1_000_000,
        min_rate=900_000_000_000_000_000,
        deadline=1_790_000_000,
        permit_nonce=1,
        sig_deadline=1_790_000_000,
    )
    assert Account.recover_message(encode_typed_data(full_message=permit_full), signature=permit_sig) == OWNER
    assert Account.recover_message(encode_typed_data(full_message=intent_full), signature=intent_sig) == OWNER


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:  # pragma: no cover
                failures += 1
                print(f"FAIL {name}: {e}")
    raise SystemExit(1 if failures else 0)
