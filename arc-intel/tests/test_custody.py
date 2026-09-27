import unittest

from execution import custody as C
from execution import sessions as S


class CustodyTests(unittest.TestCase):
    def test_new_wallet_roundtrip(self):
        w = C.new_wallet()
        self.assertTrue(w["address"].startswith("0x"))
        self.assertEqual(C.address_of(w["private_key"]).lower(), w["address"].lower())

    def test_encrypt_roundtrip(self):
        w = C.new_wallet()
        key = S.new_enc_key()
        enc = S.encrypt_secret(w["private_key"], key)
        self.assertNotIn(w["private_key"], enc)
        self.assertEqual(S.decrypt_secret(enc, key), w["private_key"])

    def test_store_custody(self):
        from bot.store import SubscriptionStore
        s = SubscriptionStore(":memory:")
        try:
            w = C.new_wallet()
            s.save_custody(7, w["address"], "enc")
            got = s.get_custody(7)
            self.assertEqual(got["address"], w["address"].lower())
            s.delete_custody(7)
            self.assertIsNone(s.get_custody(7))
        finally:
            s.close()


if __name__ == "__main__":
    unittest.main()
