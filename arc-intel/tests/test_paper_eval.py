import unittest
from unittest import mock

import indexer.paper_eval as pe
from indexer.alerts import Alert


class PaperEvalTests(unittest.TestCase):
    def test_bootstrap_median_ci(self):
        vals = [1.0, 2.0, 3.0, 4.0, 5.0]
        lo, hi = pe.bootstrap_median_ci(vals, iters=500, seed=1)
        self.assertLessEqual(lo, 3.0)
        self.assertGreaterEqual(hi, 3.0)
        self.assertEqual(pe.bootstrap_median_ci([7.0]), (7.0, 7.0))
        self.assertEqual(pe.bootstrap_median_ci([]), (None, None))

    def test_stats_has_ci_and_fat_tail(self):
        # one big positive, several small negatives -> positive median? check fields exist
        outcomes = []
        for bd in (0.05, 0.04, 0.03, -0.5):
            outcomes.append({"horizons": {"1h": {"benefit_delayed": bd, "benefit_instant": bd}}})
        s = pe._stats(outcomes, "1h")
        self.assertEqual(s["n_real"], 4)
        self.assertIn("median_ci95_pct", s)
        self.assertEqual(s["mean_delayed_pct"], round(sum([0.05, 0.04, 0.03, -0.5]) / 4 * 100, 2))

    def test_stale_horizons_excluded(self):
        outcomes = [
            {"horizons": {"1h": {"benefit_delayed": 0.5, "benefit_instant": 0.5, "stale": True}}},
            {"horizons": {"1h": {"benefit_delayed": 0.02, "benefit_instant": 0.03, "stale": False}}},
        ]
        s = pe._stats(outcomes, "1h")
        self.assertEqual(s["n_real"], 1)     # the stale (frozen) one is NOT counted
        self.assertEqual(s["n_stale"], 1)

    def test_evaluate_multi_signal(self):
        alerts = [Alert(token="0xt", kind="dev_sell", severity="high", block=0),
                  Alert(token="0xt", kind="dev_sell", severity="high", block=100)]
        series = [(0, 1.0), (100, 0.8), (50000, 0.5)]
        with mock.patch.object(pe, "load_creator_sells", return_value=[]), \
             mock.patch.object(pe, "dev_sell_alerts", return_value=alerts), \
             mock.patch.object(pe, "load_volume_buckets", return_value={}), \
             mock.patch.object(pe, "volume_collapse_alerts", return_value=[]), \
             mock.patch.object(pe, "compound_alerts", return_value=[]), \
             mock.patch.object(pe, "load_price_series", return_value=series):
            rep = pe.evaluate(object(), delay_seconds=45)
        self.assertEqual(rep["dev_sell"]["n_alerts"], 2)
        self.assertIn("1h", rep["dev_sell"]["horizons"])
        self.assertIn("median_ci95_pct", rep["dev_sell"]["horizons"]["1h"])


if __name__ == "__main__":
    unittest.main()
