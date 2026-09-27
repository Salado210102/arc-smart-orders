import unittest

from execution.strategy import Position, ExitPlan, evaluate_exit, pnl_pct, update_high_water


class StrategyTests(unittest.TestCase):
    def test_stop_loss(self):
        pos = Position(entry_price=100.0, size=10.0)
        r = evaluate_exit(pos, 75.0, ExitPlan(stop_loss_pct=0.2))
        self.assertEqual(r["action"], "stop_loss")
        self.assertAlmostEqual(r["fraction"], 1.0)
        self.assertAlmostEqual(pnl_pct(pos, 75.0), -0.25)

    def test_take_profit(self):
        pos = Position(entry_price=100.0, size=10.0)
        r = evaluate_exit(pos, 160.0, ExitPlan(take_profit_pct=0.5))
        self.assertEqual(r["action"], "take_profit")

    def test_trailing_stop_after_high_water(self):
        pos = Position(entry_price=100.0, size=10.0)
        evaluate_exit(pos, 200.0, ExitPlan())          # sets high_water=200
        r = evaluate_exit(pos, 145.0, ExitPlan(trailing_stop_pct=0.25))
        self.assertEqual(r["action"], "trailing_stop")

    def test_trailing_not_before_profit(self):
        pos = Position(entry_price=100.0, size=10.0)
        r = evaluate_exit(pos, 90.0, ExitPlan(trailing_stop_pct=0.25))
        self.assertEqual(r["action"], "hold")

    def test_scale_out(self):
        pos = Position(entry_price=100.0, size=10.0)
        r = evaluate_exit(pos, 155.0, ExitPlan(scale_out=[(1.5, 0.5)]))
        self.assertEqual(r["action"], "scale_out")
        self.assertAlmostEqual(r["fraction"], 0.5)

    def test_hold(self):
        pos = Position(entry_price=100.0, size=10.0)
        r = evaluate_exit(pos, 101.0, ExitPlan(stop_loss_pct=0.2, take_profit_pct=0.5))
        self.assertEqual(r["action"], "hold")

    def test_high_water_update(self):
        pos = Position(entry_price=100.0, size=1.0)
        self.assertEqual(update_high_water(pos, 120.0), 120.0)
        self.assertEqual(update_high_water(pos, 110.0), 120.0)


if __name__ == "__main__":
    unittest.main()
