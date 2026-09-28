import unittest

from monetization import tiers as T
from bot.miniapp_api import tier_view
from bot.store import SubscriptionStore


class TierPureTests(unittest.TestCase):
    def test_vip_tiers(self):
        self.assertEqual(T.vip_tier(0)["level"], "")
        self.assertEqual(T.vip_tier(10_000)["fee_bps"], 80)
        self.assertEqual(T.vip_tier(50_000)["fee_bps"], 70)
        self.assertEqual(T.vip_tier(250_000)["fee_bps"], 65)

    def test_welcome_active_then_expires(self):
        now = 1_000_000
        act = T.fee_bps_for(joined_ts=now - 100, now=now, referred=True, volume_30d=0)
        self.assertEqual(act["level"], "WELCOME")
        self.assertEqual(act["fee_bps"], 90)
        exp = T.fee_bps_for(joined_ts=now - 31 * 86400, now=now, referred=True, volume_30d=0)
        self.assertEqual(exp["level"], "STANDARD")

    def test_vip_overrides_welcome(self):
        now = 1_000_000
        t = T.fee_bps_for(joined_ts=now, now=now, referred=True, volume_30d=10_000)
        self.assertEqual(t["level"], "VIP1")

    def test_standard_when_not_referred(self):
        t = T.fee_bps_for(joined_ts=0, now=1, referred=False, volume_30d=0)
        self.assertEqual(t["fee_bps"], 100)


class TierViewTests(unittest.TestCase):
    def setUp(self):
        self.s = SubscriptionStore(":memory:")

    def tearDown(self):
        self.s.close()

    def test_new_user_sets_joined(self):
        self.s.ensure_subscriber(1)
        self.assertIsNotNone(self.s.get_state("joined:1"))
        v = tier_view(self.s, 1)
        self.assertIn(v["tier"], ("STANDARD", "WELCOME"))
        self.assertIn("fee_pct", v)


if __name__ == "__main__":
    unittest.main()
