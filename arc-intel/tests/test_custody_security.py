import os
import tempfile
import unittest

from bot.store import SubscriptionStore


class CustodySecurityStoreTests(unittest.TestCase):
    def setUp(self):
        self.s = SubscriptionStore(":memory:")

    def tearDown(self):
        self.s.close()

    def test_registered_addr_24h_delay(self):
        now = 1_000_000
        usable = self.s.add_custody_addr(1, "0x" + "a" * 40, delay_s=86400, now=now)
        self.assertEqual(usable, now + 86400)
        self.assertFalse(self.s.custody_addr_usable(1, "0x" + "a" * 40, now=now))
        self.assertTrue(self.s.custody_addr_usable(1, "0x" + "a" * 40, now=now + 86401))
        self.assertFalse(self.s.custody_addr_usable(1, "0x" + "b" * 40, now=now + 86401))

    def test_daily_withdraw_counter(self):
        now = 1_000_000
        self.assertEqual(self.s.withdraw_today(1, now=now), 0.0)
        self.s.add_withdraw_today(1, 10.0, now=now)
        self.s.add_withdraw_today(1, 5.0, now=now)
        self.assertEqual(self.s.withdraw_today(1, now=now), 15.0)
        # next day resets
        self.assertEqual(self.s.withdraw_today(1, now=now + 86400), 0.0)

    def test_freeze_and_totp_and_pause(self):
        self.assertFalse(self.s.is_frozen(1))
        self.s.set_frozen(1, True)
        self.assertTrue(self.s.is_frozen(1))
        self.s.set_frozen(1, False)
        self.assertFalse(self.s.is_frozen(1))
        self.s.save_totp(1, "ENC")
        self.assertEqual(self.s.get_totp(1), "ENC")
        self.s.clear_totp(1)
        self.assertEqual(self.s.get_totp(1), "")
        self.assertFalse(self.s.custody_paused())
        self.s.set_custody_paused(True)
        self.assertTrue(self.s.custody_paused())

    def test_key_audit_append_only(self):
        self.s.log_key_audit(1, "withdraw", "signer:withdraw", 111)
        self.s.log_key_audit(1, "swap", "signer:swap", 222)
        rows = self.s.list_key_audit()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["reason"], "swap")     # newest first
        self.assertNotIn("secret", str(rows).lower())


class SignerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        from cryptography.fernet import Fernet
        self.key = Fernet.generate_key().decode()
        os.environ["ARC_INTEL_DB"] = self.tmp.name
        os.environ["ARC_INTEL_SESSION_ENC_KEY"] = self.key

    def tearDown(self):
        os.environ.pop("ARC_INTEL_SESSION_ENC_KEY", None)
        os.environ.pop("ARC_INTEL_DB", None)
        try:
            os.unlink(self.tmp.name)
        except OSError:
            pass

    def test_encrypt_decrypt_and_audit(self):
        from execution import signer
        ct = signer.encrypt_secret("S3CRET")
        self.assertNotIn("S3CRET", ct)
        self.assertEqual(signer.decrypt(7, ct, "totp"), "S3CRET")
        # decryption was audited (uid/reason/caller; never the material)
        s = SubscriptionStore(self.tmp.name)
        try:
            rows = s.list_key_audit()
        finally:
            s.close()
        self.assertEqual(rows[0]["uid"], "7")
        self.assertEqual(rows[0]["reason"], "totp")
        self.assertNotIn("S3CRET", str(rows))

    def test_decrypt_error_leaks_no_material(self):
        from execution import signer
        with self.assertRaises(Exception) as cm:
            signer.decrypt(1, "not-a-valid-token", "x")
        msg = str(cm.exception)
        self.assertNotIn(self.key, msg)
        self.assertNotIn("not-a-valid-token", msg)

    def test_multi_key_rotation(self):
        from cryptography.fernet import Fernet
        from execution import signer
        new_key = Fernet.generate_key().decode()
        # encrypt with single old key
        ct = signer.encrypt_secret("X")
        # rotate: new primary + old secondary -> old ciphertext still decrypts
        os.environ["ARC_INTEL_SESSION_ENC_KEYS"] = f"{new_key},{self.key}"
        try:
            self.assertEqual(signer.decrypt(1, ct, "rot"), "X")
        finally:
            os.environ.pop("ARC_INTEL_SESSION_ENC_KEYS", None)


if __name__ == "__main__":
    unittest.main()
