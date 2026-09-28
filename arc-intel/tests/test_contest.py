import unittest

from bot.store import SubscriptionStore
from monetization import contest as CT


class ContestMathTests(unittest.TestCase):
    def test_round_window(self):
        w = CT.round_window(0)
        self.assertEqual(w["start"], 0)
        self.assertEqual(w["end"], 43200)
        self.assertEqual(w["seconds_left"], 43200)
        w2 = CT.round_window(43200 + 100)
        self.assertEqual(w2["start"], 43200)
        self.assertEqual(w2["seconds_left"], 43100)

    def test_pozo_and_split(self):
        self.assertAlmostEqual(CT.pozo(1000.0), 1.0)     # 1% fee = $10 -> 10% = $1
        self.assertEqual(CT.split_prize(1.0), {"trader": 0.5, "affiliate": 0.5})

    def test_leaderboard_and_ties(self):
        lb = CT.leaderboard({"a": 10, "b": 30, "c": 0, "d": 10}, top=3)
        self.assertEqual([r["user"] for r in lb], ["b", "a", "d"])   # tie -> user asc
        self.assertEqual(lb[0]["rank"], 1)
        self.assertEqual(lb[2]["rank"], 3)

    def test_standings(self):
        st = CT.standings({"a": 10, "b": 10}, {"x": 5})
        self.assertAlmostEqual(st["total_volume"], 20.0)
        self.assertAlmostEqual(st["pozo"], 0.02)         # 1% of 20 = 0.2 -> 10% = 0.02
        self.assertAlmostEqual(st["prize"]["trader"], 0.01)
        self.assertEqual(st["affiliate_top"][0]["user"], "x")

    def test_rank_of_and_mask(self):
        v = {"a": 10, "b": 30}
        self.assertEqual(CT.rank_of(v, "b")["rank"], 1)
        self.assertEqual(CT.rank_of(v, "z")["rank"], 0)
        self.assertEqual(CT.mask_user("123456789"), "12\u202689")
        self.assertEqual(CT.mask_user("ab"), "ab")


class ContestStoreTests(unittest.TestCase):
    def setUp(self):
        self.s = SubscriptionStore(":memory:")
        self.tok = "0x" + "a" * 40

    def tearDown(self):
        self.s.close()

    def test_volume_window_excludes_paper(self):
        self.s.record_fill("tx1:buy", "1", self.tok, "buy", 1.0, 100.0, ts=1000)
        self.s.record_fill("tx2:buy", "2", self.tok, "buy", 1.0, 200.0, ts=1500)
        self.s.record_fill("paperbuy:1:tok:99", "1", self.tok, "buy", 1.0, 999.0, ts=1500)
        self.assertEqual(self.s.volume_by_user_since(1200), {"2": 200.0})
        self.assertEqual(self.s.volume_by_user_since(0), {"1": 100.0, "2": 200.0})

    def test_referred_volume(self):
        from monetization import referrals as R
        code = self.s.ensure_referral_code(10, R.make_code(10))
        self.s.bind_referral(1, 10, code)
        self.s.bind_referral(2, 10, code)
        self.s.record_fill("tx1:buy", "1", self.tok, "buy", 1.0, 100.0, ts=1000)  # before window
        self.s.record_fill("tx2:buy", "2", self.tok, "buy", 1.0, 200.0, ts=1500)
        self.assertEqual(self.s.referred_volume_by_user_since(1200), {"10": 200.0})


if __name__ == "__main__":
    unittest.main()
