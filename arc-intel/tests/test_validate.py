import unittest

from indexer.validate import composite_signal


class ValidateTests(unittest.TestCase):
    def test_composite_signal_min_trades_and_order(self):
        stats = {
            "0xa": {"n": 10, "wins": 9, "avg_mult": 2.0, "variance": 0.1, "realized": 5.0},
            "0xb": {"n": 10, "wins": 3, "avg_mult": 1.0, "variance": 1.0, "realized": -5.0},
            "0xc": {"n": 2, "wins": 2, "avg_mult": 9.0, "variance": 0.0, "realized": 9.0},
        }
        entry = {"0xa": 0.9, "0xb": 0.1, "0xc": 1.0}
        sig = composite_signal(stats, entry, min_trades=8)
        self.assertEqual(set(sig), {"0xa", "0xb"})
        self.assertGreater(sig["0xa"], sig["0xb"])

    def test_composite_signal_empty(self):
        self.assertEqual(composite_signal({}, {}, 8), {})


if __name__ == "__main__":
    unittest.main()
