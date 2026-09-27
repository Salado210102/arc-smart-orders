import unittest

from bot.store import SubscriptionStore
from monetization import referrals as R


class ReferralStoreTests(unittest.TestCase):
    def setUp(self):
        self.s = SubscriptionStore(":memory:")

    def tearDown(self):
        self.s.close()

    def test_code_is_stable_and_unique(self):
        c1 = self.s.ensure_referral_code(1, R.make_code(1))
        c2 = self.s.ensure_referral_code(1, "OTHERCODE")   # idempotent: keeps the first
        self.assertEqual(c1, c2)
        self.assertEqual(self.s.get_referral_code(1), c1)
        self.assertEqual(self.s.referral_owner(c1), "1")

    def test_bind_no_self_first_wins(self):
        code = self.s.ensure_referral_code(1, R.make_code(1))
        self.assertTrue(self.s.bind_referral(2, 1, code))
        self.assertFalse(self.s.bind_referral(2, 1, code))        # already bound
        self.assertFalse(self.s.bind_referral(1, 1, code))        # no self-referral
        self.assertEqual(self.s.get_referrer(2), "1")
        self.assertEqual(self.s.list_referred(1), ["2"])

    def test_fill_accrues_30pct_of_fee(self):
        code = self.s.ensure_referral_code(1, R.make_code(1))
        self.s.bind_referral(2, 1, code)
        # buyer 2 buys $100 -> fee $1.00 -> referrer 1 earns $0.30
        added = self.s.record_fill("txA:buy", 2, "0x" + "a" * 40, "buy", 10.0, 100.0)
        self.assertTrue(added)
        s = self.s.referral_summary(1)
        self.assertEqual(s["referred"], 1)
        self.assertEqual(s["fills"], 1)
        self.assertAlmostEqual(s["accrued"], 0.30)
        self.assertAlmostEqual(s["pending"], 0.30)

    def test_fill_idempotent_no_double_credit(self):
        code = self.s.ensure_referral_code(1, R.make_code(1))
        self.s.bind_referral(2, 1, code)
        self.s.record_fill("txA:buy", 2, "0x" + "a" * 40, "buy", 10.0, 100.0)
        self.s.record_fill("txA:buy", 2, "0x" + "a" * 40, "buy", 10.0, 100.0)  # duplicate
        self.assertAlmostEqual(self.s.referral_summary(1)["accrued"], 0.30)

    def test_paper_fills_never_pay(self):
        code = self.s.ensure_referral_code(1, R.make_code(1))
        self.s.bind_referral(2, 1, code)
        self.s.record_fill("paperbuy:2:0xabc:1", 2, "0x" + "a" * 40, "buy", 10.0, 100.0)
        self.assertEqual(self.s.referral_summary(1)["accrued"], 0.0)

    def test_no_referrer_no_credit(self):
        self.s.record_fill("txB:buy", 9, "0x" + "b" * 40, "buy", 1.0, 50.0)
        self.assertEqual(self.s.referral_summary(1)["accrued"], 0.0)

    def test_capture_referral_wires_start_param(self):
        from bot import commands
        code = self.s.ensure_referral_code(1, R.make_code(1))
        commands.capture_referral(self.s, 2, f"/start ref_{code}")
        self.assertEqual(self.s.get_referrer(2), "1")
        commands.capture_referral(self.s, 1, f"/start ref_{code}")   # self-referral ignored
        self.assertEqual(self.s.get_referrer(1), "")

    def test_credits_listed(self):
        code = self.s.ensure_referral_code(1, R.make_code(1))
        self.s.bind_referral(2, 1, code)
        self.s.record_fill("txC:buy", 2, "0x" + "c" * 40, "buy", 5.0, 200.0)
        credits = self.s.list_referral_credits(1)
        self.assertEqual(len(credits), 1)
        self.assertEqual(credits[0]["buyer"], "2")
        self.assertAlmostEqual(credits[0]["fee_usdc"], 2.0)
        self.assertAlmostEqual(credits[0]["commission_usdc"], 0.60)


if __name__ == "__main__":
    unittest.main()
