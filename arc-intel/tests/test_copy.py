import unittest

from bot.store import SubscriptionStore
from execution.copy import CopyConfig, plan_buy, decide, MIN_COPY_USDC
from execution.copy_keeper import run_copy_engine

LEADER = "0x" + "f" * 40
TOKEN = "0x" + "a" * 40


class CopyDecisionTests(unittest.TestCase):
    def test_plan_buy_caps(self):
        cfg = CopyConfig(max_per_trade=25, max_total=100)
        self.assertEqual(plan_buy(10, cfg), 10)          # under both caps
        self.assertEqual(plan_buy(200, cfg), 25)         # per-trade cap
        self.assertEqual(plan_buy(2, cfg), 0.0)          # dust

    def test_plan_buy_budget(self):
        cfg = CopyConfig(max_per_trade=25, max_total=30, spent=25)
        self.assertEqual(plan_buy(20, cfg), 5)           # remaining budget
        cfg.spent = 30
        self.assertEqual(plan_buy(20, cfg), 0.0)         # exhausted

    def test_decide_buy_sell_skip(self):
        cfg = CopyConfig(max_per_trade=25, max_total=100)
        self.assertEqual(decide({"side": "buy", "stable_value": 10}, cfg)["action"], "buy")
        self.assertEqual(decide({"side": "sell", "stable_value": 10}, cfg, 5.0)["action"], "sell")
        self.assertEqual(decide({"side": "sell", "stable_value": 10}, cfg, 0.0)["reason"],
                         "no_position")
        self.assertEqual(decide({"side": "buy", "stable_value": MIN_COPY_USDC / 2}, cfg)["action"],
                         "skip")


class CopyStoreTests(unittest.TestCase):
    def setUp(self):
        self.s = SubscriptionStore(":memory:")

    def tearDown(self):
        self.s.close()

    def test_add_get_list_remove(self):
        self.s.add_copy_sub(1, LEADER, max_per_trade=10, max_total=50, now_block=90)
        sub = self.s.get_copy_sub(1)
        self.assertEqual(sub["leader"], LEADER)
        self.assertEqual(sub["max_per_trade"], 10)
        self.assertEqual(sub["max_total"], 50)
        self.assertTrue(sub["enabled"])
        self.assertEqual(self.s.list_copy_subs()[0]["follower_chat"], "1")
        self.assertTrue(self.s.set_copy_enabled(1, False))
        self.assertEqual(self.s.list_copy_subs(enabled_only=True), [])
        self.s.bump_copy_spent(1, 3.5)
        self.assertAlmostEqual(self.s.get_copy_sub(1)["spent"], 3.5)
        self.s.set_copy_last_block(1, 123)
        self.assertEqual(self.s.get_copy_sub(1)["last_block"], 123)
        self.assertTrue(self.s.remove_copy_sub(1))
        self.assertIsNone(self.s.get_copy_sub(1))


class _FakeStorage:
    def __init__(self, trades):
        self.trades = trades

    def recent_wallet_legs(self, wallet, since, limit=20):
        return [t for t in self.trades.get(wallet.lower(), []) if t["block"] > since][:limit]


class CopyEngineTests(unittest.TestCase):
    def setUp(self):
        self.s = SubscriptionStore(":memory:")
        self.calls = []

    def tearDown(self):
        self.s.close()

    def _exec(self, sub, trade, decision):
        self.calls.append(decision)
        res = {"tx": "0xdead"}
        if decision["action"] == "buy":
            self.s.record_fill("0xdead:copybuy", sub["follower_chat"], trade["token"], "buy",
                               1.0, float(decision["usdc"]))
        return res

    def test_buy_mirrors_and_bumps_spent(self):
        self.s.add_copy_sub(1, LEADER, max_per_trade=25, max_total=100, now_block=90)
        st = _FakeStorage({LEADER: [{"token": TOKEN, "side": "buy", "stable_value": 10.0,
                                     "block": 100}]})
        out = run_copy_engine(self.s, st, head=100, executor=self._exec, logger=lambda d: None)
        self.assertEqual(out["executed"], 1)
        self.assertEqual(self.calls[0]["usdc"], 10.0)
        sub = self.s.get_copy_sub(1)
        self.assertAlmostEqual(sub["spent"], 10.0)
        self.assertEqual(sub["last_block"], 100)
        self.assertGreater(self.s.get_position(1, TOKEN)["qty"], 0)

    def test_budget_bounds_successive_buys(self):
        self.s.add_copy_sub(1, LEADER, max_per_trade=5, max_total=8, now_block=90)
        st = _FakeStorage({LEADER: [
            {"token": TOKEN, "side": "buy", "stable_value": 20.0, "block": 100},
            {"token": TOKEN, "side": "buy", "stable_value": 20.0, "block": 101},
            {"token": TOKEN, "side": "buy", "stable_value": 20.0, "block": 102},
        ]})
        out = run_copy_engine(self.s, st, head=102, executor=self._exec, logger=lambda d: None)
        self.assertEqual([c["usdc"] for c in self.calls], [5.0, 3.0])   # 5 then remaining 3, then 0
        self.assertEqual(out["skipped"], 1)

    def test_sell_without_position_skips(self):
        self.s.add_copy_sub(1, LEADER, now_block=90)
        st = _FakeStorage({LEADER: [{"token": TOKEN, "side": "sell", "stable_value": 5.0,
                                     "block": 100}]})
        out = run_copy_engine(self.s, st, head=100, executor=self._exec, logger=lambda d: None)
        self.assertEqual(out["executed"], 0)
        self.assertEqual(out["skipped"], 1)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.s.get_copy_sub(1)["last_block"], 100)

    def test_dry_run_does_not_execute(self):
        self.s.add_copy_sub(1, LEADER, now_block=90)
        st = _FakeStorage({LEADER: [{"token": TOKEN, "side": "buy", "stable_value": 10.0,
                                     "block": 100}]})
        out = run_copy_engine(self.s, st, head=100, dry_run=True, executor=self._exec,
                              logger=lambda d: None)
        self.assertEqual(out["executed"], 1)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.s.get_copy_sub(1)["last_block"], 100)
        self.assertEqual(self.s.get_copy_sub(1)["spent"], 0.0)

    def test_no_recopy_after_advance(self):
        self.s.add_copy_sub(1, LEADER, now_block=90)
        st = _FakeStorage({LEADER: [{"token": TOKEN, "side": "buy", "stable_value": 10.0,
                                     "block": 100}]})
        run_copy_engine(self.s, st, head=100, executor=self._exec, logger=lambda d: None)
        out = run_copy_engine(self.s, st, head=100, executor=self._exec, logger=lambda d: None)
        self.assertEqual(out["trades"], 0)
        self.assertEqual(out["executed"], 0)

    def test_first_run_jumps_to_head(self):
        self.s.add_copy_sub(1, LEADER, now_block=0)   # last_block=0 -> first run initializes
        st = _FakeStorage({LEADER: [{"token": TOKEN, "side": "buy", "stable_value": 10.0,
                                     "block": 100}]})
        out = run_copy_engine(self.s, st, head=100, executor=self._exec, logger=lambda d: None)
        self.assertEqual(out["executed"], 0)
        self.assertEqual(self.s.get_copy_sub(1)["last_block"], 100)


if __name__ == "__main__":
    unittest.main()
