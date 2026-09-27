import unittest

from execution.intents import (
    build_intent, expected_out, min_out, is_expired, intent_digest, IntentError,
)


class IntentTests(unittest.TestCase):
    def test_build_valid(self):
        i = build_intent("0xUser", "0xToken", "buy", 100.0, now=1000, limit_price=2.0,
                         max_slippage_bps=100, ttl_seconds=300)
        self.assertEqual(i.deadline, 1300)
        self.assertEqual(i.side, "buy")
        self.assertAlmostEqual(expected_out(i), 200.0)
        self.assertAlmostEqual(min_out(i), 198.0)  # 1% slippage

    def test_require_limit(self):
        with self.assertRaises(IntentError):
            build_intent("0xu", "0xt", "buy", 1.0, now=0, require_limit=True)

    def test_invalid_inputs(self):
        with self.assertRaises(IntentError):
            build_intent("0xu", "0xt", "hold", 1.0, now=0)
        with self.assertRaises(IntentError):
            build_intent("0xu", "0xt", "buy", 0.0, now=0)
        with self.assertRaises(IntentError):
            build_intent("0xu", "0xt", "buy", 1.0, now=0, max_slippage_bps=6000)

    def test_expiry(self):
        i = build_intent("0xu", "0xt", "sell", 1.0, now=1000, ttl_seconds=300)
        self.assertFalse(is_expired(i, 1300))
        self.assertTrue(is_expired(i, 1301))

    def test_digest_is_canonical_and_keyless(self):
        i = build_intent("0xUSER", "0xTOKEN", "buy", 1.0, now=0, limit_price=1.0)
        d = intent_digest(i)
        self.assertEqual(d["user"], "0xuser")
        self.assertEqual(d["token"], "0xtoken")
        self.assertNotIn("key", d)
        self.assertNotIn("private", d)


if __name__ == "__main__":
    unittest.main()
