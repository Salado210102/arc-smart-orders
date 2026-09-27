import unittest

from indexer.safety import safety_score


class SafetyTests(unittest.TestCase):
    def test_clean_is_safe(self):
        r = safety_score(risk={"level": "low"}, creator_rep={}, liquidity_usd=50000,
                         age_blocks=50000, holders_top10_pct=30, lp_locked=True)
        self.assertEqual(r["verdict"], "SAFE")
        self.assertGreaterEqual(r["score"], 70)

    def test_honeypot_is_danger(self):
        r = safety_score(risk={"level": "high", "honeypot_hint": True}, liquidity_usd=1000)
        self.assertEqual(r["verdict"], "DANGER")

    def test_creator_dump_cuts(self):
        bad = safety_score(risk={"level": "low"},
                           creator_rep={"created": 5, "dumped": 3, "rug_rate": 0.6}, liquidity_usd=50000)
        good = safety_score(risk={"level": "low"}, creator_rep={}, liquidity_usd=50000)
        self.assertLess(bad["score"], good["score"])

    def test_bounds_and_danger(self):
        r = safety_score(risk={"level": "high", "honeypot_hint": True,
                               "reasons": ["upgradeable_proxy"]},
                         creator_rep={"created": 9, "dumped": 9, "rug_rate": 1.0},
                         liquidity_usd=0, thin_market="no_trades", holders_top10_pct=90)
        self.assertGreaterEqual(r["score"], 0)
        self.assertEqual(r["verdict"], "DANGER")

    def test_no_liquidity_flag(self):
        r = safety_score(risk={"level": "low"}, liquidity_usd=0)
        self.assertIn("no_liquidity", [f["factor"] for f in r["factors"]])


if __name__ == "__main__":
    unittest.main()
