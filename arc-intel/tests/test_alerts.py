import unittest

from indexer.alerts import (
    pct_of_position, is_significant_sell, severity_for, detect_compound,
    dev_sell_alerts, volume_collapse_alerts, compound_alerts, liquidity_removal_alerts,
    is_thin_market, Alert,
)


class AlertTests(unittest.TestCase):
    def test_pct_of_position(self):
        self.assertAlmostEqual(pct_of_position(50, 100), 0.5)
        self.assertIsNone(pct_of_position(10, 0))

    def test_significant_sell(self):
        self.assertTrue(is_significant_sell(50, 100, 10, min_pct=0.4, min_usdc=1000))
        self.assertTrue(is_significant_sell(5, 1000, 5000, min_pct=0.5, min_usdc=1000))
        self.assertFalse(is_significant_sell(5, 1000, 10, min_pct=0.5, min_usdc=1000))

    def test_severity(self):
        self.assertEqual(severity_for(0.9, 10), "high")
        self.assertEqual(severity_for(0.5, 600), "medium")
        self.assertEqual(severity_for(0.1, 5), "low")

    def test_dev_sell_alerts(self):
        rows = [
            {"token": "0xt", "wallet": "0xdev", "block": 100, "sell_qty": 90.0,
             "usdc": 900.0, "pos_before": 100.0},
            {"token": "0xt2", "wallet": "0xdev", "block": 100, "sell_qty": 1.0,
             "usdc": 1.0, "pos_before": 1000.0},
        ]
        alerts = dev_sell_alerts(rows, min_pct=0.5, min_usdc=100)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].token, "0xt")
        self.assertAlmostEqual(alerts[0].pct_position, 0.9)
        self.assertIn("sold 90%", alerts[0].message)

    def test_volume_collapse_alerts(self):
        vals = [9, 10, 11, 10, 9, 10, 11, 10, 9, 10, 11, 10, 0]
        series = {"0xt": [(i * 1000, float(v)) for i, v in enumerate(vals)]}
        alerts = volume_collapse_alerts(series, z_threshold=-2.0, lookback=12)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].kind, "volume_collapse")

    def test_compound(self):
        dev = [Alert(token="0xt", kind="dev_sell", severity="high", block=100,
                     wallet="0xdev", role="creator", pct_position=0.9)]
        collapse = [Alert(token="0xt", kind="volume_collapse", severity="high", block=1200,
                          context={"z": -3.0})]
        comp = compound_alerts(dev, collapse, window_blocks=2000)
        self.assertEqual(len(comp), 1)
        self.assertEqual(comp[0].kind, "compound")
        self.assertIn("dev-sell", comp[0].message)

    def test_compound_out_of_window(self):
        dev = [Alert(token="0xt", kind="dev_sell", severity="high", block=100)]
        collapse = [Alert(token="0xt", kind="volume_collapse", severity="high", block=999999)]
        self.assertEqual(compound_alerts(dev, collapse, window_blocks=2000), [])

    def test_liquidity_removal_alerts(self):
        rows = [
            {"pool_id": "0xp", "sender": "0xdev", "block": 100, "delta": -100.0,
             "creator": "0xdev", "token": "0xt", "added": 100.0},
            {"pool_id": "0xp2", "sender": "0xrouter", "block": 100, "delta": -5.0,
             "creator": "0xdev2", "token": "0xt2", "added": 1000.0},
        ]
        alerts = liquidity_removal_alerts(rows, min_ratio=0.5)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].token, "0xt")
        self.assertEqual(alerts[0].role, "creator")
        self.assertEqual(alerts[0].severity, "high")

    def test_thin_market(self):
        # too young -> None
        self.assertIsNone(is_thin_market(0, 0, 10, no_trade_blocks=100))
        # old, never traded
        self.assertEqual(is_thin_market(0, 0, 200, no_trade_blocks=100), "no_trades")
        # old, traded but single wallet
        self.assertEqual(is_thin_market(5, 1, 200, no_trade_blocks=100), "single_wallet")
        # healthy
        self.assertIsNone(is_thin_market(5, 4, 200, no_trade_blocks=100))


if __name__ == "__main__":
    unittest.main()
