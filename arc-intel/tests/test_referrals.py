import unittest

from monetization import referrals as R


class ReferralMathTests(unittest.TestCase):
    def test_make_code_deterministic_and_valid(self):
        a = R.make_code(12345)
        self.assertEqual(a, R.make_code(12345))
        self.assertNotEqual(a, R.make_code(54321))
        self.assertEqual(len(a), R.CODE_LEN)
        self.assertTrue(all(ch in R._ALPHABET for ch in a))

    def test_normalize_code(self):
        c = R.make_code(999)
        self.assertEqual(R.normalize_code(c.lower()), c)
        self.assertEqual(R.normalize_code("abc0"), "")   # 0 not in alphabet
        self.assertEqual(R.normalize_code(""), "")

    def test_parse_ref_param(self):
        c = R.make_code(7)
        self.assertEqual(R.parse_ref_param(f"/start ref_{c}"), c)
        self.assertEqual(R.parse_ref_param(f"/start {c.lower()}"), c)
        self.assertEqual(R.parse_ref_param("/start"), "")
        self.assertEqual(R.parse_ref_param("hello"), "")

    def test_referral_link(self):
        self.assertEqual(R.referral_link("MyBot", "ABC"), "https://t.me/MyBot?start=ref_ABC")
        self.assertEqual(R.referral_link("@MyBot", "ABC"), "https://t.me/MyBot?start=ref_ABC")
        self.assertEqual(R.referral_link("", "ABC"), "")

    def test_fee_and_commission(self):
        self.assertAlmostEqual(R.fee_from_notional(100.0), 1.0)
        self.assertAlmostEqual(R.commission_usdc(1.0), 0.3)              # 30% of the fee
        self.assertAlmostEqual(R.commission_from_notional(100.0), 0.3)   # $100 trade -> $0.30
        self.assertAlmostEqual(R.commission_from_notional(1000.0), 3.0)

    def test_invalid(self):
        with self.assertRaises(ValueError):
            R.fee_from_notional(-1.0)
        with self.assertRaises(ValueError):
            R.commission_usdc(1.0, 20000)


if __name__ == "__main__":
    unittest.main()
