import unittest

from indexer.shrinkage import wilson_lower_bound, eb_shrink_win_rate, population_win_rate


class ShrinkageTests(unittest.TestCase):
    def test_wilson_penalizes_small_n(self):
        # a 40/45 wallet must rank above an 8/8 one
        self.assertLess(wilson_lower_bound(8, 8), wilson_lower_bound(40, 45))

    def test_wilson_bounds(self):
        self.assertEqual(wilson_lower_bound(0, 0), 0.0)
        self.assertAlmostEqual(wilson_lower_bound(0, 10), 0.0)
        self.assertGreater(wilson_lower_bound(1, 10), wilson_lower_bound(0, 10))

    def test_eb_shrink_order(self):
        self.assertLess(eb_shrink_win_rate(8, 8, 0.5, 10),
                        eb_shrink_win_rate(40, 45, 0.5, 10))

    def test_population_win_rate(self):
        rows = [{"win_rate": 1.0, "trades": 8}, {"win_rate": 0.5, "trades": 12}]
        self.assertAlmostEqual(population_win_rate(rows), (8 + 6) / 20)


if __name__ == "__main__":
    unittest.main()
