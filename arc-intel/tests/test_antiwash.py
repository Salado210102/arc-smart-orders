import unittest

from monetization import antiwash as A
from bot.store import SubscriptionStore


class AntiWashPureTests(unittest.TestCase):
    def _fills(self):
        return [
            {"fill_id": "1", "user": "u1", "token": "0xaaa", "side": "buy", "usdc": 100, "ts": 1000},
            {"fill_id": "2", "user": "u1", "token": "0xbbb", "side": "buy", "usdc": 2, "ts": 1001},   # dust
            {"fill_id": "3", "user": "u1", "token": "0xccc", "side": "buy", "usdc": 50, "ts": 1002},  # own token
            {"fill_id": "4", "user": "u2", "token": "0xddd", "side": "buy", "usdc": 30, "ts": 1003},
            {"fill_id": "5", "user": "u2", "token": "0xddd", "side": "sell", "usdc": 30, "ts": 1010}, # round-trip
        ]

    def test_min_notional_own_token_roundtrip(self):
        v = A.volume_by_user(self._fills(), min_notional=5.0, own_tokens=("0xccc",), window_s=60)
        self.assertEqual(v.get("u1"), 100.0)      # dust + own excluded
        self.assertNotIn("u2", v)                 # round-trip excluded

    def test_roundtrip_window_boundary(self):
        f = [{"fill_id": "a", "user": "u", "token": "t", "side": "buy", "usdc": 10, "ts": 0},
             {"fill_id": "b", "user": "u", "token": "t", "side": "sell", "usdc": 10, "ts": 100}]
        self.assertEqual(A.roundtrip_fill_ids(f, window_s=60), set())         # outside window
        self.assertEqual(A.roundtrip_fill_ids(f, window_s=200), {"a", "b"})   # inside window

    def test_same_funding_merge(self):
        v = {"w1": 10.0, "w2": 5.0, "w3": 7.0}
        m = A.merge_by_funding(v, lambda u: "fund1" if u in ("w1", "w2") else None)
        self.assertEqual(m.get("fund1"), 15.0)
        self.assertEqual(m.get("w3"), 7.0)


class ContestAntiwashStoreTests(unittest.TestCase):
    def setUp(self):
        self.s = SubscriptionStore(":memory:")

    def tearDown(self):
        self.s.close()

    def test_contest_volume_applies_min_notional(self):
        tok = "0x" + "a" * 40
        self.s.record_fill("t1:buy", "1", tok, "buy", 1.0, 100.0, ts=100)
        self.s.record_fill("t2:buy", "1", tok, "buy", 1.0, 2.0, ts=101)   # dust
        self.assertEqual(self.s.contest_volume_between(0, 200).get("1"), 100.0)

    def test_prize_payout_flag_default_off(self):
        from bot.contest_publish import settle_prizes
        self.assertFalse(self.s.prize_payout_enabled())
        self.assertEqual(settle_prizes(self.s, 123)["reason"], "disabled")
        self.s.set_prize_payout(True)
        self.assertTrue(self.s.prize_payout_enabled())


if __name__ == "__main__":
    unittest.main()
