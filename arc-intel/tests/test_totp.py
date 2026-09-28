import unittest

from bot import totp as T

# RFC 6238 test secret: ASCII "12345678901234567890" -> base32
RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"


class TotpTests(unittest.TestCase):
    def test_rfc6238_vectors(self):
        # 6-digit codes for the SHA1 vectors (times in the RFC table)
        self.assertEqual(T.code(RFC_SECRET, at=59), "287082")
        self.assertEqual(T.code(RFC_SECRET, at=1111111109), "081804")
        self.assertEqual(T.code(RFC_SECRET, at=1111111111), "050471")
        self.assertEqual(T.code(RFC_SECRET, at=1234567890), "005924")
        self.assertEqual(T.code(RFC_SECRET, at=2000000000), "279037")

    def test_verify_window(self):
        at = 1_000_000
        c = T.code(RFC_SECRET, at=at)
        self.assertTrue(T.verify(RFC_SECRET, c, at=at))
        self.assertTrue(T.verify(RFC_SECRET, c, at=at + 30))     # within +/-1 window
        self.assertFalse(T.verify(RFC_SECRET, c, at=at + 120))   # too far
        self.assertFalse(T.verify(RFC_SECRET, "000000", at=at))
        self.assertFalse(T.verify("", c, at=at))

    def test_secret_and_uri(self):
        s = T.new_secret()
        self.assertTrue(len(s) >= 16)
        uri = T.provisioning_uri(s, "42")
        self.assertTrue(uri.startswith("otpauth://totp/"))
        self.assertIn("secret=" + s, uri)


if __name__ == "__main__":
    unittest.main()
