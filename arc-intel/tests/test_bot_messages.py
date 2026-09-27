import unittest

from bot.messages import format_wallet_context, format_alert, format_token_signal, format_alert_rich


class MessageTests(unittest.TestCase):
    def test_format_wallet_context(self):
        s = {"win_rate": 0.73, "trades": 18, "avg_mult": 2.1, "entry_pct": 0.8, "confidence": "media"}
        txt = format_wallet_context(s)
        self.assertIn("73% win rate in 18 trades", txt)
        self.assertIn("2.10x", txt)
        self.assertIn("media", txt)

    def test_format_alert_has_why(self):
        alert = {"token": "0xt", "severity": "high",
                 "reasons": [{"rule": "dev_sell", "severity": "high"}], "message": "x"}
        txt = format_alert(alert, score={"win_rate": 1.0, "trades": 9, "avg_mult": 1.6,
                                          "entry_pct": 0.8, "confidence": "baja"})
        self.assertIn("[HIGH]", txt)
        self.assertIn("why: dev_sell", txt)
        self.assertIn("100% win rate in 9 trades", txt)

    def test_format_token_signal(self):
        txt = format_token_signal("0xt", {"win_rate": 0.5, "trades": 8, "avg_mult": 1.0,
                                          "entry_pct": 0.5, "confidence": "baja"},
                                  ["volume_collapse", "dev_sell"])
        self.assertIn("risk: volume_collapse, dev_sell", txt)

    def test_format_alert_rich(self):
        a = {"token": "0xabc", "kind": "dev_sell", "severity": "high",
             "message": "creator sold 100%", "context": {"symbol": "BTS"}}
        s = format_alert_rich(a)
        self.assertIn("🔴", s)
        self.assertIn("<b>", s)
        self.assertIn("$BTS", s)
        self.assertIn("explorer.arc.io/address/0xabc", s)
        self.assertIn("Not financial advice", s)


if __name__ == "__main__":
    unittest.main()
