import unittest

from indexer.risk import (
    bucket_volumes, rolling_zscore, volume_collapse, smart_money_exit, dev_sell, anti_rug_report,
    build_alerts, evaluate_rules, Rule,
)


def leg(wallet, token, block, side, val=1.0):
    return {"wallet": wallet, "token": token, "block": block, "side": side, "stable_value": val}


class RiskTests(unittest.TestCase):
    def test_bucket_volumes(self):
        legs = [leg("0xw", "0xt", 100, "buy", 2.0), leg("0xw", "0xt", 110, "buy", 3.0),
                leg("0xw", "0xt", 2100, "sell", 1.0)]
        s = bucket_volumes(legs, bucket_blocks=2000)
        self.assertEqual(s["0xt"], [(0, 5.0), (2000, 1.0)])

    def test_rolling_zscore_and_collapse(self):
        vals = [9, 10, 11, 10, 9, 10, 11, 10, 9, 10, 11, 10, 0]
        series = [(i * 1000, float(v)) for i, v in enumerate(vals)]
        z = rolling_zscore(series, lookback=12)
        self.assertIsNone(z[0][1])
        self.assertLess(z[-1][1], -3)
        collapse = volume_collapse(series, lookback=12, z_threshold=-1.5)
        self.assertIsNotNone(collapse)
        steady = [(i * 1000, 10.0 + (i % 2)) for i in range(13)]
        self.assertIsNone(volume_collapse(steady, lookback=12, z_threshold=-1.5))

    def test_smart_money_exit(self):
        legs = [leg("0xSmart", "0xt", 100, "sell"), leg("0xother", "0xt", 100, "sell")]
        r = smart_money_exit(legs, {"0xsmart"}, "0xt", 0, 500)
        self.assertEqual(r["smart_sellers"], 1)

    def test_dev_sell(self):
        legs = [leg("0xDev", "0xt", 50, "sell"), leg("0xDev", "0xt", 80, "sell"),
                leg("0xbuyer", "0xt", 60, "buy")]
        r = dev_sell(legs, "0xdev", "0xt")
        self.assertEqual(r["dev_sells"], 2)
        self.assertEqual(r["first_block"], 50)

    def test_anti_rug_report_flags(self):
        vals = [9, 10, 11, 10, 9, 10, 11, 10, 9, 10, 11, 10, 0]
        legs = [leg("0xbuyer", "0xt", i * 1000, "buy", float(v)) for i, v in enumerate(vals)]
        legs.append(leg("0xdev", "0xt", 5000, "sell", 1.0))
        rep = anti_rug_report(legs, creators_by_token={"0xt": "0xdev"},
                              bucket_blocks=1000, lookback=12, z_threshold=-1.5)
        flags = rep["0xt"]["flags"]
        self.assertIn("dev_sell", flags)
        self.assertIn("volume_collapse", flags)

    def test_evaluate_rules_launchpad_filter(self):
        t = {"dev_sell": {"dev_sells": 1}, "smart_money_exit": {"smart_sellers": 0},
             "volume_collapse": None}
        rules = [Rule("only_argus", "high", lambda x: True, launchpads=("argus",))]
        self.assertEqual([r.name for r in evaluate_rules(t, "argus", rules)], ["only_argus"])
        self.assertEqual(evaluate_rules(t, "other", rules), [])

    def test_build_alerts_severity_and_message(self):
        report = {"0xt": {"dev_sell": {"dev_sells": 2}, "smart_money_exit": {"smart_sellers": 1},
                          "volume_collapse": {"block": 1, "z": -2.0}, "flags": ["dev_sell"]}}
        alerts = build_alerts(report)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["severity"], "high")
        self.assertIn("dev_sell", [r["rule"] for r in alerts[0]["reasons"]])
        self.assertIn("creator sold x2", alerts[0]["message"])


if __name__ == "__main__":
    unittest.main()
