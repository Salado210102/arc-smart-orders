import unittest

from indexer.paper import price_at, paper_outcome, blocks_for, PAPER_TAG, paper_message


class PaperTests(unittest.TestCase):
    def test_price_at(self):
        series = [(0, 1.0), (100, 0.8), (200, 0.5)]
        self.assertEqual(price_at(series, 0), 1.0)
        self.assertEqual(price_at(series, 150), 0.8)
        self.assertEqual(price_at(series, 999), 0.5)
        self.assertIsNone(price_at([], 10))

    def test_paper_outcome_drop(self):
        # price falls 1.0 -> 0.8 by ~1h; selling avoids the drop
        series = [(0, 1.0), (100, 0.8), (10000, 0.5)]
        out = paper_outcome(series, alert_block=0, delay_seconds=45)
        h1 = out["horizons"]["1h"]
        self.assertGreater(h1["benefit_delayed"], 0)

    def test_delay_changes_result(self):
        # price drops inside the simulated delay window, then recovers
        series = [(0, 1.0), (50, 0.9), (100, 1.2)]
        out = paper_outcome(series, alert_block=0, delay_seconds=45)  # ~87 blocks delay
        h1 = out["horizons"]["1h"]
        self.assertAlmostEqual(out["act_price_instant"], 1.0)
        self.assertAlmostEqual(out["act_price_delayed"], 0.9)
        # delayed (worse fill) differs from instant -> delay matters, bias visible
        self.assertNotAlmostEqual(h1["benefit_delayed"], h1["benefit_instant"])

    def test_blocks_for(self):
        self.assertAlmostEqual(blocks_for(3600), round(3600 / 0.52))

    def test_message_tagged_paper(self):
        series = [(0, 1.0), (100, 0.8), (20000, 0.6)]
        out = paper_outcome(series, 0)
        msg = paper_message("0xtok", out)
        self.assertTrue(msg.startswith(PAPER_TAG))
        self.assertIn("benefit vs hold", msg)


if __name__ == "__main__":
    unittest.main()
