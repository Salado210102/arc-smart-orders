import unittest

from bot.store import SubscriptionStore
from bot import approvals as ap
from indexer.paper import PAPER_TAG


class ApprovalTests(unittest.TestCase):
    def setUp(self):
        self.store = SubscriptionStore(":memory:")

    def tearDown(self):
        self.store.close()

    def test_propose_and_pending(self):
        aid = ap.propose(self.store, 1, "0xtok", "dev_sell", "sell", 5.0, 100, 1000,
                         cancel_seconds=60, ttl_seconds=600)
        self.assertGreater(aid, 0)
        p = ap.pending(self.store, 1, 1010)
        self.assertEqual(len(p), 1)
        self.assertEqual(p[0]["token"], "0xtok")

    def test_cancel_window_blocks_approve(self):
        aid = ap.propose(self.store, 1, "0xtok", "dev_sell", "sell", 5.0, 100, 1000,
                         cancel_seconds=300, ttl_seconds=3600)
        ok, reason = ap.approve(self.store, 1, aid, 1100)
        self.assertFalse(ok)
        self.assertIn("cancel window", reason)

    def test_approve_after_window(self):
        aid = ap.propose(self.store, 1, "0xtok", "dev_sell", "sell", 5.0, 100, 1000,
                         cancel_seconds=60, ttl_seconds=3600)
        ok, reason = ap.approve(self.store, 1, aid, 1100)
        self.assertTrue(ok)
        self.assertEqual(reason, "approved")

    def test_2fa_threshold(self):
        aid = ap.propose(self.store, 1, "0xtok", "dev_sell", "sell", 100.0, 100, 1000,
                         cancel_seconds=60, ttl_seconds=3600, threshold=50.0)
        a = self.store.get_approval(aid)
        self.assertTrue(a["requires_2fa"])
        ok, reason = ap.approve(self.store, 1, aid, 1100, code="0000")
        self.assertFalse(ok)
        self.assertEqual(reason, "2fa_required")
        ok2, _ = ap.approve(self.store, 1, aid, 1100, code=a["code"])
        self.assertTrue(ok2)

    def test_expiry(self):
        aid = ap.propose(self.store, 1, "0xtok", "dev_sell", "sell", 5.0, 100, 1000,
                         cancel_seconds=60, ttl_seconds=100)
        ok, reason = ap.approve(self.store, 1, aid, 2000)
        self.assertFalse(ok)
        self.assertEqual(reason, "expired")

    def test_cancel(self):
        aid = ap.propose(self.store, 1, "0xtok", "dev_sell", "sell", 5.0, 100, 1000)
        ok, reason = ap.cancel(self.store, 1, aid, 1010)
        self.assertTrue(ok)
        self.assertEqual(self.store.get_approval(aid)["status"], "cancelled")

    def test_paper_result_is_tagged(self):
        series = [(0, 1.0), (100, 0.8), (20000, 0.5)]
        msg = ap.paper_result(lambda t: series, "0xtok", 0)
        self.assertTrue(msg.startswith(PAPER_TAG))
        self.assertIn("benefit vs hold", msg)


if __name__ == "__main__":
    unittest.main()
