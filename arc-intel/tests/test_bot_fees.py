import unittest

from monetization.fees import fee_amount, split_fee, round_trip_fee, net_buy_cost


class FeeTests(unittest.TestCase):
    def test_fee_amount_1pct(self):
        self.assertAlmostEqual(fee_amount(100.0), 1.0)
        self.assertAlmostEqual(fee_amount(250.0, 100), 2.5)

    def test_split_fee(self):
        sp = split_fee(1.0, 5000)
        self.assertAlmostEqual(sp["rewards_usdc"], 0.5)
        self.assertAlmostEqual(sp["treasury_usdc"], 0.5)

    def test_round_trip(self):
        self.assertAlmostEqual(round_trip_fee(100.0), 2.0)

    def test_net_buy_cost(self):
        r = net_buy_cost(100.0, fee_bps=100, reward_share_bps=5000)
        self.assertAlmostEqual(r["fee_usdc"], 1.0)
        self.assertAlmostEqual(r["cashback_usdc"], 0.5)
        self.assertAlmostEqual(r["net_usdc"], 100.5)

    def test_invalid(self):
        with self.assertRaises(ValueError):
            fee_amount(-1.0)
        with self.assertRaises(ValueError):
            split_fee(1.0, 20000)


if __name__ == "__main__":
    unittest.main()
