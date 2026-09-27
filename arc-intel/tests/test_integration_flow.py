import unittest

from indexer.risk import anti_rug_report, build_alerts
from bot.messages import format_alert
from execution.intents import build_intent, min_out
from execution.strategy import Position, ExitPlan, evaluate_exit
from security.permissions import create_approval, confirm, can_execute, mark_executed


class IntegrationFlowTest(unittest.TestCase):
    def test_signal_to_execution_flow(self):
        # 1) data -> anti-rug report -> alert with context
        legs = [{"wallet": "0xsmart", "token": "0xt", "block": i * 1000, "side": "buy",
                 "stable_value": 10.0} for i in range(13)]
        legs.append({"wallet": "0xdev", "token": "0xt", "block": 5000, "side": "sell",
                     "stable_value": 1.0})
        rep = anti_rug_report(legs, creators_by_token={"0xt": "0xdev"},
                              smart_wallets={"0xsmart"}, bucket_blocks=1000, z_threshold=-1.5)
        alerts = build_alerts(rep, min_severity="medium")
        self.assertTrue(alerts)
        self.assertEqual(alerts[0]["severity"], "high")
        msg = format_alert(alerts[0], score={"win_rate": 0.8, "trades": 18, "avg_mult": 2.0,
                                             "entry_pct": 0.8, "confidence": "media"})
        self.assertIn("why:", msg)
        self.assertIn("win rate", msg)

        # 2) trade intent (non-custodial; no signing)
        intent = build_intent("0xuser", "0xt", "buy", 10.0, now=1000, limit_price=2.0,
                              max_slippage_bps=100)
        self.assertAlmostEqual(min_out(intent), 19.8)

        # 3) permission gate: cancel window + 2FA above threshold + execute
        approval = create_approval("ap1", "0xuser", {"token": "0xt", "side": "buy"},
                                   intent.amount * 2.0, now=1000, cancel_seconds=300,
                                   twofa_threshold=5.0)
        self.assertTrue(approval.requires_2fa)
        blocked, reason = confirm(approval, 1100, twofa_ok=True)   # window still open
        self.assertFalse(blocked)
        self.assertEqual(reason, "cancel_window_open")
        no2fa, reason2 = confirm(approval, 1400, twofa_ok=False)
        self.assertFalse(no2fa)
        self.assertEqual(reason2, "2fa_required")
        ok, _ = confirm(approval, 1400, twofa_ok=True)
        self.assertTrue(ok)
        self.assertTrue(can_execute(approval, 1500))
        self.assertTrue(mark_executed(approval, 1500))

        # 4) exit management
        pos = Position(entry_price=2.0, size=10.0)
        self.assertEqual(evaluate_exit(pos, 2.0 * 1.6, ExitPlan(take_profit_pct=0.5))["action"],
                         "take_profit")
        self.assertEqual(evaluate_exit(pos, 2.0 * 0.7, ExitPlan(stop_loss_pct=0.2))["action"],
                         "stop_loss")


if __name__ == "__main__":
    unittest.main()
