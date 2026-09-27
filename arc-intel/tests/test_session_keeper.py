import json
import unittest

from bot.store import SubscriptionStore
from execution import sessions as S
from execution.session_keeper import run_session_keeper, session_order_arg

USDC = "0x3600000000000000000000000000000000000000"
TOK = "0x" + "a" * 40
USER = "0x" + "b" * 40
EXEC = "0x" + "e" * 40
KEY = {"currency0": USDC, "currency1": TOK, "fee": 10000, "tick_spacing": 200, "hooks": "0x" + "0" * 40}
POOL_ID = "0x" + "1" * 64


class SessionKeeperTests(unittest.TestCase):
    def setUp(self):
        self.store = SubscriptionStore(":memory:")
        self.enckey = S.new_enc_key()
        self.sk = S.new_session_key()
        self.store.save_session(1, self.sk["address"],
                                S.encrypt_secret(self.sk["private_key"], self.enckey),
                                EXEC, POOL_ID, USDC, 100, 200, 0, 9999999999, status="active")
        intent = {"mode": "session", "pool_id": POOL_ID, "token_in": USDC, "key": KEY,
                  "zero_for_one": True, "amount_in": 50, "min_out": 10, "recipient": USER}
        self.pid = self.store.create_preorder(1, USER, TOK, 0, 0, 10, 9999999999, 5,
                                              status="armed", kind="session")
        self.store.save_sig_payload(self.pid, json.dumps(intent))

    def tearDown(self):
        self.store.close()

    def test_signs_and_executes(self):
        captured = {}

        def fake_submit(po, intent, sig, executor, rpc, relayer):
            captured["sig"] = sig
            return "0xtx"

        r = run_session_keeper(self.store, submit=fake_submit, now=1, enc_key=self.enckey,
                               executor=EXEC, relayer="0x" + "f" * 40, chain_id=5042002)
        self.assertEqual(r["submitted"], 1)
        td = S.session_order_typed_data(chain_id=5042002, executor=EXEC, user=USER, key=KEY,
                                        zero_for_one=True, amount_in=50, min_out=10, recipient=USER,
                                        order_nonce=5, deadline=9999999999)
        self.assertEqual(S.recover_session_signer(td, captured["sig"]).lower(),
                         self.sk["address"].lower())
        self.assertEqual(self.store.get_preorder(self.pid)["status"], "executed")

    def test_not_configured_is_noop(self):
        r = run_session_keeper(self.store, executor="", relayer="", enc_key="")
        self.assertEqual(r.get("skipped"), "not_configured")

    def test_no_session_leaves_order_armed(self):
        self.store.conn.execute("DELETE FROM sessions")
        self.store.conn.commit()
        r = run_session_keeper(self.store, submit=lambda *a: "0x", now=1, enc_key=self.enckey,
                               executor=EXEC, relayer="0x" + "f" * 40)
        self.assertEqual(r["submitted"], 0)
        self.assertEqual(self.store.get_preorder(self.pid)["status"], "armed")

    def test_session_order_arg(self):
        arg = session_order_arg({"user": USER, "key": KEY, "zero_for_one": True, "amount_in": 50,
                                 "min_out": 10, "recipient": USER, "order_nonce": 5, "deadline": 9},
                                "0xdead")
        self.assertIn("0xdead", arg)
        self.assertIn("true", arg)


if __name__ == "__main__":
    unittest.main()
