import unittest

from execution.positions import Position, apply_fill, sell_quantity, reconcile, PositionError
from bot.store import SubscriptionStore

TOK = "0x" + "a" * 40


class PositionLogicTests(unittest.TestCase):
    def test_buy_then_sell_half(self):
        p = Position(TOK)
        apply_fill(p, "buy", 100.0, 200.0)   # 100 tokens for 200 USDC -> avg 2.0
        self.assertAlmostEqual(p.qty, 100.0)
        self.assertAlmostEqual(p.cost, 200.0)
        self.assertAlmostEqual(p.avg_cost, 2.0)

        qty = sell_quantity(p, 0.5)          # 50% of the CURRENT position
        self.assertAlmostEqual(qty, 50.0)
        apply_fill(p, "sell", qty, 150.0)    # sell 50 for 150 -> realized +50
        self.assertAlmostEqual(p.qty, 50.0)
        self.assertAlmostEqual(p.cost, 100.0)
        self.assertAlmostEqual(p.realized, 50.0)

    def test_sell_all_closes(self):
        p = Position(TOK)
        apply_fill(p, "buy", 10.0, 10.0)
        apply_fill(p, "sell", 10.0, 12.0)
        self.assertAlmostEqual(p.qty, 0.0)
        self.assertAlmostEqual(p.cost, 0.0)
        self.assertAlmostEqual(p.realized, 2.0)

    def test_sell_without_position_raises(self):
        with self.assertRaises(PositionError):
            apply_fill(Position(TOK), "sell", 1.0, 1.0)

    def test_sell_pct_refused_with_pending(self):
        p = Position(TOK)
        apply_fill(p, "buy", 10.0, 10.0)
        with self.assertRaises(PositionError):
            sell_quantity(p, 0.5, has_pending=True)

    def test_sell_pct_refused_without_position(self):
        with self.assertRaises(PositionError):
            sell_quantity(Position(TOK), 0.5)
        with self.assertRaises(PositionError):
            sell_quantity(None, 0.5)

    def test_sell_pct_invalid(self):
        p = Position(TOK)
        apply_fill(p, "buy", 10.0, 10.0)
        for bad in (0, -0.1, 1.5):
            with self.assertRaises(PositionError):
                sell_quantity(p, bad)

    def test_reconcile(self):
        p = Position(TOK)
        apply_fill(p, "buy", 100.0, 100.0)
        ok, diff = reconcile(p, 100.0)
        self.assertTrue(ok)
        self.assertAlmostEqual(diff, 0.0)
        ok, diff = reconcile(p, 90.0)
        self.assertFalse(ok)
        self.assertAlmostEqual(diff, 10.0)


class StorePositionTests(unittest.TestCase):
    def setUp(self):
        self.store = SubscriptionStore(":memory:")

    def tearDown(self):
        self.store.close()

    def test_record_fill_idempotent(self):
        self.assertTrue(self.store.record_fill("0xtx:0", 1, TOK, "buy", 100.0, 200.0, block=5))
        # a duplicated event must NOT count twice
        self.assertFalse(self.store.record_fill("0xtx:0", 1, TOK, "buy", 100.0, 200.0, block=5))
        p = self.store.get_position(1, TOK)
        self.assertAlmostEqual(p["qty"], 100.0)
        self.assertAlmostEqual(p["cost"], 200.0)

    def test_sell_half_updates_realized(self):
        self.store.record_fill("t1", 1, TOK, "buy", 100.0, 200.0)
        self.store.record_fill("t2", 1, TOK, "sell", 50.0, 150.0)
        p = self.store.get_position(1, TOK)
        self.assertAlmostEqual(p["qty"], 50.0)
        self.assertAlmostEqual(p["cost"], 100.0)
        self.assertAlmostEqual(p["realized"], 50.0)

    def test_list_positions(self):
        self.store.record_fill("t1", 1, TOK, "buy", 10.0, 10.0)
        rows = self.store.list_positions(1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["token"], TOK)


if __name__ == "__main__":
    unittest.main()
