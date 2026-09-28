import unittest

from bot.store import SubscriptionStore
from execution.copy import CopySettings, plan_size, decide
from execution.copy_keeper import run_copy_engine

LEADER = "0x" + "f" * 40
LEADER2 = "0x" + "e" * 40
TOKEN = "0x" + "a" * 40
TOKEN2 = "0x" + "b" * 40


class CopyDecisionTests(unittest.TestCase):
    def test_plan_size(self):
        self.assertEqual(plan_size(100, CopySettings(sizing="flat", flat_usdc=25)), 25)
        self.assertEqual(plan_size(100, CopySettings(sizing="proportional")), 100)

    def test_decide_filters(self):
        s = CopySettings(min_buy_usdc=50, max_open=2, sizing="flat", flat_usdc=25)
        self.assertEqual(decide({"side": "buy", "stable_value": 10}, s)["reason"], "below_min")
        self.assertEqual(decide({"side": "buy", "stable_value": 100}, s, open_positions=2)["reason"],
                         "max_open")
        self.assertEqual(decide({"side": "buy", "stable_value": 100}, s, open_positions=2,
                                holding=True)["action"], "buy")   # adding to a held token is allowed
        self.assertEqual(decide({"side": "buy", "stable_value": 100}, s)["usdc"], 25)

    def test_decide_sells(self):
        self.assertEqual(decide({"side": "sell"}, CopySettings(mirror_sells=False), 5.0)["reason"],
                         "mirror_off")
        self.assertEqual(decide({"side": "sell"}, CopySettings(mirror_sells=True), 0.0)["reason"],
                         "no_position")
        self.assertEqual(decide({"side": "sell"}, CopySettings(mirror_sells=True), 5.0)["action"],
                         "sell")


class CopyStoreTests(unittest.TestCase):
    def setUp(self):
        self.s = SubscriptionStore(":memory:")

    def tearDown(self):
        self.s.close()

    def test_wallets(self):
        self.s.add_copy_wallet(1, LEADER, flat_usdc=7, now_block=90)
        w = self.s.get_copy_wallet(1, LEADER)
        self.assertEqual(w["flat_usdc"], 7.0)
        self.assertTrue(w["enabled"])
        self.s.add_copy_wallet(1, LEADER2)
        self.assertIsNone(self.s.get_copy_wallet(1, LEADER2)["flat_usdc"])
        self.assertEqual(len(self.s.list_copy_wallets(1)), 2)
        self.assertTrue(self.s.set_copy_wallet_enabled(1, LEADER2, False))
        self.assertEqual(len(self.s.list_all_copy_wallets(enabled_only=True)), 1)
        self.assertTrue(self.s.remove_copy_wallet(1, LEADER))
        self.assertEqual(len(self.s.list_copy_wallets(1)), 1)

    def test_settings_upsert_preserves(self):
        st = self.s.get_copy_settings(1)
        self.assertEqual(st["flat_usdc"], 25.0)
        self.assertTrue(st["mirror_sells"])
        self.s.set_copy_settings(1, min_buy_usdc=10, max_open=3)
        self.s.set_copy_settings(1, sizing="proportional")
        st2 = self.s.get_copy_settings(1)
        self.assertEqual(st2["sizing"], "proportional")
        self.assertEqual(st2["min_buy_usdc"], 10)      # preserved
        self.assertEqual(st2["max_open"], 3)
        self.s.set_copy_settings(1, mirror_sells=False)
        self.assertFalse(self.s.get_copy_settings(1)["mirror_sells"])


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

    def _exec(self, chat, wallet, trade, decision, settings):
        self.calls.append(decision)
        res = {"tx": "0xdead"}
        if decision["action"] == "buy":
            self.s.record_fill("0xdead:copybuy", chat, trade["token"], "buy", 1.0,
                               float(decision["usdc"]), ts=0)
        return res

    def test_buy_uses_flat_size(self):
        self.s.add_copy_wallet(1, LEADER, now_block=90)
        st = _FakeStorage({LEADER: [{"token": TOKEN, "side": "buy", "stable_value": 100.0,
                                     "block": 100}]})
        out = run_copy_engine(self.s, st, head=100, executor=self._exec, logger=lambda d: None)
        self.assertEqual(out["executed"], 1)
        self.assertEqual(self.calls[0]["usdc"], 25.0)              # default flat
        self.assertEqual(self.s.get_copy_wallet(1, LEADER)["last_block"], 100)

    def test_per_wallet_flat_override(self):
        self.s.add_copy_wallet(1, LEADER, flat_usdc=7, now_block=90)
        st = _FakeStorage({LEADER: [{"token": TOKEN, "side": "buy", "stable_value": 100.0,
                                     "block": 100}]})
        run_copy_engine(self.s, st, head=100, executor=self._exec, logger=lambda d: None)
        self.assertEqual(self.calls[0]["usdc"], 7.0)

    def test_min_buy_skips(self):
        self.s.add_copy_wallet(1, LEADER, now_block=90)
        self.s.set_copy_settings(1, min_buy_usdc=200)
        st = _FakeStorage({LEADER: [{"token": TOKEN, "side": "buy", "stable_value": 100.0,
                                     "block": 100}]})
        out = run_copy_engine(self.s, st, head=100, executor=self._exec, logger=lambda d: None)
        self.assertEqual(out["executed"], 0)
        self.assertEqual(out["skipped"], 1)

    def test_mirror_off_skips_sell(self):
        self.s.add_copy_wallet(1, LEADER, now_block=90)
        self.s.set_copy_settings(1, mirror_sells=False)
        st = _FakeStorage({LEADER: [{"token": TOKEN, "side": "sell", "stable_value": 5.0,
                                     "block": 100}]})
        out = run_copy_engine(self.s, st, head=100, executor=self._exec, logger=lambda d: None)
        self.assertEqual(out["executed"], 0)
        self.assertEqual(out["skipped"], 1)

    def test_proportional_and_multi_wallet(self):
        self.s.add_copy_wallet(1, LEADER, now_block=90)
        self.s.add_copy_wallet(1, LEADER2, now_block=90)
        self.s.set_copy_settings(1, sizing="proportional")
        st = _FakeStorage({LEADER: [{"token": TOKEN, "side": "buy", "stable_value": 40.0, "block": 100}],
                           LEADER2: [{"token": TOKEN2, "side": "buy", "stable_value": 60.0, "block": 100}]})
        out = run_copy_engine(self.s, st, head=100, executor=self._exec, logger=lambda d: None)
        self.assertEqual(out["wallets"], 2)
        self.assertEqual(sorted(c["usdc"] for c in self.calls), [40.0, 60.0])

    def test_dry_run_no_execute(self):
        self.s.add_copy_wallet(1, LEADER, now_block=90)
        st = _FakeStorage({LEADER: [{"token": TOKEN, "side": "buy", "stable_value": 100.0,
                                     "block": 100}]})
        out = run_copy_engine(self.s, st, head=100, dry_run=True, executor=self._exec,
                              logger=lambda d: None)
        self.assertEqual(out["executed"], 1)
        self.assertEqual(self.calls, [])

    def test_first_run_jumps_to_head(self):
        self.s.add_copy_wallet(1, LEADER, now_block=0)
        st = _FakeStorage({LEADER: [{"token": TOKEN, "side": "buy", "stable_value": 100.0,
                                     "block": 100}]})
        out = run_copy_engine(self.s, st, head=100, executor=self._exec, logger=lambda d: None)
        self.assertEqual(out["executed"], 0)
        self.assertEqual(self.s.get_copy_wallet(1, LEADER)["last_block"], 100)


if __name__ == "__main__":
    unittest.main()
