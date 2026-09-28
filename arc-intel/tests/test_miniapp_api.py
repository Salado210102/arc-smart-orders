import unittest

from bot.miniapp_api import (age_text, alert_view, alerts_view, build_token_card, copy_view,
                             format_price, format_usd, portfolio_summary, position_view,
                             position_views, wallet_view)
from bot.store import SubscriptionStore
from indexer.alerts import Alert

TOK = "0x" + "a" * 40


class FakeStore:
    def __init__(self, rows):
        self._rows = rows

    def list_positions(self, user):
        return self._rows


class MiniAppApiTests(unittest.TestCase):
    def test_format_price(self):
        self.assertEqual(format_price(0), "n/a")
        self.assertEqual(format_price(1.23456), "$1.2346")
        self.assertEqual(format_price(0.00001234), "$0.00001234")
        self.assertIn("e-", format_price(1e-9))

    def test_format_usd(self):
        self.assertEqual(format_usd(0), "n/a")
        self.assertEqual(format_usd(1234.6), "$1,235")

    def test_age_text(self):
        self.assertEqual(age_text(0), "0 min")
        self.assertEqual(age_text(166153), "24.0 h")
        self.assertEqual(age_text(170000), "1.0 d")

    def test_build_token_card(self):
        c = build_token_card(address=TOK.upper(), symbol="PEPE", name="Pepe", creator="0xdev",
                             created_block=1000, head_block=1000 + 170000, swaps=42, wallets=7,
                             vol24=1500, price=0.002, supply=1_000_000, thin_reason="single_wallet",
                             creator_rep={"created": 3, "dumped": 1})
        self.assertEqual(c["address"], TOK.lower())
        self.assertEqual(c["market_cap"], 2000.0)
        self.assertEqual(c["market_cap_text"], "$2,000")
        self.assertEqual(c["status"], "thin market (single_wallet)")
        self.assertEqual(c["age_text"], "1.0 d")
        self.assertTrue(c["explorer"].endswith(TOK.lower()))

    def test_position_view_pnl_and_reconcile(self):
        row = {"token": TOK, "qty": 100.0, "cost": 50.0, "realized": 5.0, "avg_cost": 0.5,
               "last_block": 10}
        v = position_view(row, price=1.0, onchain_qty=100.0)
        self.assertAlmostEqual(v["value"], 100.0)
        self.assertAlmostEqual(v["unrealized"], 50.0)
        self.assertAlmostEqual(v["unrealized_pct"], 1.0)   # 0.5 -> 1.0
        self.assertTrue(v["reconciled"])

    def test_position_view_reconcile_mismatch(self):
        row = {"token": TOK, "qty": 100.0, "cost": 50.0, "realized": 0.0, "avg_cost": 0.5}
        v = position_view(row, price=1.0, onchain_qty=40.0)
        self.assertFalse(v["reconciled"])
        self.assertAlmostEqual(v["reconcile_diff"], 60.0)

    def test_position_view_no_onchain_is_none(self):
        v = position_view({"token": TOK, "qty": 1.0, "cost": 1.0, "avg_cost": 1.0}, price=2.0)
        self.assertIsNone(v["reconciled"])

    def test_position_views_with_fakes(self):
        store = FakeStore([{"token": TOK, "qty": 10.0, "cost": 10.0, "realized": 0.0,
                            "avg_cost": 1.0, "last_block": 3}])
        views = position_views(store, "1", price_fn=lambda t: 2.0, balance_fn=lambda t: 10.0)
        self.assertEqual(len(views), 1)
        self.assertAlmostEqual(views[0]["unrealized"], 10.0)

    def test_portfolio_summary(self):
        views = [{"cost": 10.0, "value": 15.0, "realized": 1.0},
                 {"cost": 10.0, "value": 5.0, "realized": 2.0}]
        s = portfolio_summary(views)
        self.assertEqual(s["positions"], 2)
        self.assertAlmostEqual(s["unrealized"], 0.0)
        self.assertAlmostEqual(s["realized"], 3.0)

    def test_alert_view_from_object_and_dict(self):
        a = Alert(token=TOK.upper(), kind="dev_sell", severity="high", block=5,
                  context={"symbol": "PEPE"})
        a.message = "dev sold"
        v = alert_view(a)
        self.assertEqual(v["token"], TOK.lower())
        self.assertEqual(v["kind"], "dev_sell")
        self.assertEqual(v["context"]["symbol"], "PEPE")
        v2 = alert_view({"token": TOK, "kind": "volume_spike", "block": 9, "severity": "medium"})
        self.assertEqual(v2["kind"], "volume_spike")
        self.assertEqual(len(alerts_view([a, {"token": TOK, "kind": "compound", "block": 1}])), 2)

    def test_wallet_view(self):
        store = SubscriptionStore(":memory:")
        try:
            store.link_wallet(7, TOK)
            store.add_auto_sub(7, TOK, now_block=5)
            v = wallet_view(store, 7)
            self.assertEqual(v["linked_wallet"], TOK.lower())
            self.assertIn(TOK.lower(), v["auto_subs"])
            self.assertEqual(v["count"], 1)
        finally:
            store.close()

    def test_copy_view(self):
        v = copy_view([{"leader": TOK.upper(), "flat_usdc": 10, "enabled": 1}],
                      {"min_buy_usdc": 5, "max_open": 2, "sizing": "flat", "mirror_sells": 0})
        self.assertEqual(v["wallets"][0]["leader"], TOK.lower())
        self.assertEqual(v["wallets"][0]["flat_usdc"], 10)
        self.assertEqual(v["settings"]["min_buy_usdc"], 5.0)
        self.assertEqual(v["settings"]["max_open"], 2)
        self.assertFalse(v["settings"]["mirror_sells"])
        self.assertEqual(copy_view([], None)["settings"]["flat_usdc"], 25.0)


if __name__ == "__main__":
    unittest.main()
