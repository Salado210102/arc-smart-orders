import unittest

from execution.sessions import (decrypt_secret, encrypt_secret, new_enc_key, new_session_key,
                                recover_session_signer, session_order_typed_data, sign_session_order)

USDC = "0x3600000000000000000000000000000000000000"
TOK = "0x" + "a" * 40
EXEC = "0x" + "e" * 40
KEY = {"currency0": USDC, "currency1": TOK, "fee": 10000, "tick_spacing": 200,
       "hooks": "0x" + "b" * 40}


class SessionsTests(unittest.TestCase):
    def test_new_session_key(self):
        k = new_session_key()
        self.assertTrue(k["address"].startswith("0x"))
        self.assertEqual(len(k["private_key"]), 66)

    def test_typed_data_shape(self):
        td = session_order_typed_data(chain_id=5042002, executor=EXEC, user=TOK, key=KEY,
                                      zero_for_one=True, amount_in=100, min_out=90, recipient=TOK,
                                      order_nonce=1, deadline=999)
        self.assertEqual(td["primaryType"], "ArcIntelSessionOrder")
        self.assertEqual(td["domain"]["name"], "ArcIntelExecutor")
        self.assertEqual(td["domain"]["version"], "2")
        self.assertEqual(td["domain"]["verifyingContract"], EXEC)
        self.assertEqual(td["message"]["key"]["tickSpacing"], 200)

    def test_sign_recovers_to_session_key(self):
        k = new_session_key()
        td = session_order_typed_data(chain_id=5042002, executor=EXEC, user=TOK, key=KEY,
                                      zero_for_one=True, amount_in=100, min_out=90, recipient=TOK,
                                      order_nonce=1, deadline=999)
        sig = sign_session_order(k["private_key"], td)
        self.assertEqual(recover_session_signer(td, sig).lower(), k["address"].lower())

    def test_signing_key_matches_generated_address(self):
        k = new_session_key()
        td = session_order_typed_data(chain_id=1, executor=EXEC, user=TOK, key=KEY, zero_for_one=False,
                                      amount_in=1, min_out=1, recipient=TOK, order_nonce=2, deadline=2)
        sig = sign_session_order(k["private_key"], td)
        self.assertEqual(recover_session_signer(td, sig).lower(), k["address"].lower())

    def test_encryption_roundtrip(self):
        key = new_enc_key()
        secret = "0x" + "ab" * 32
        token = encrypt_secret(secret, key)
        self.assertNotIn(secret, token)
        self.assertEqual(decrypt_secret(token, key), secret)

    def test_pool_id_deterministic(self):
        from execution.sessions import pool_id
        p = pool_id(KEY)
        self.assertTrue(p.startswith("0x"))
        self.assertEqual(len(p), 66)
        self.assertEqual(p, pool_id(KEY))

    def test_calldata_selectors(self):
        from execution.sessions import (calldata_approve, calldata_authorize_session,
                                        calldata_permit2_approve, calldata_revoke_session)
        from indexer.token_risk import selector
        self.assertTrue(calldata_approve(EXEC, 5).startswith(selector("approve(address,uint256)")))
        self.assertTrue(calldata_revoke_session(EXEC).startswith(selector("revokeSession(address)")))
        self.assertTrue(calldata_permit2_approve(USDC, EXEC, 1, 2)
                        .startswith(selector("approve(address,address,uint160,uint48)")))
        self.assertTrue(calldata_authorize_session(EXEC, "0x" + "1" * 64, USDC, 1, 2, 0, 3)
                        .startswith(selector(
                            "authorizeSession(address,bytes32,address,uint256,uint256,uint256,uint64)")))

    def test_store_sessions(self):
        from bot.store import SubscriptionStore
        s = SubscriptionStore(":memory:")
        try:
            s.save_session(1, "0x" + "b" * 40, "enc", "0x" + "e" * 40, "0x" + "1" * 64, USDC,
                           100, 200, 0, 999, status="active")
            got = s.get_session(1, "0x" + "1" * 64, USDC)
            self.assertIsNotNone(got)
            self.assertEqual(got["max_total"], 200)
            self.assertEqual(len(s.list_sessions(1)), 1)
            self.assertTrue(s.revoke_session(1, "0x" + "b" * 40))
            self.assertIsNone(s.get_session(1, "0x" + "1" * 64, USDC))
        finally:
            s.close()


if __name__ == "__main__":
    unittest.main()
