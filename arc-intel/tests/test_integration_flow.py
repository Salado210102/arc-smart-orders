import unittest

from indexer.alerts import dev_sell_alerts, volume_collapse_alerts, compound_alerts
from bot.messages import format_alert
from execution.intents import build_intent, min_out
from execution.strategy import Position, ExitPlan, evaluate_exit
from security.permissions import create_approval, confirm, can_execute, mark_executed


class IntegrationFlowTest(unittest.TestCase):
    def test_signal_to_execution_flow(self):
        # 1) data -> live alert engine (indexer.alerts) -> alert message
        rows = [{"token": "0xt", "wallet": "0xdev", "role": "creator", "block": 5000,
                 "sell_qty": 90.0, "pos_before": 100.0, "usdc": 900.0}]
        dev = dev_sell_alerts(rows, min_pct=0.5, min_usdc=100.0)
        self.assertTrue(dev)
        self.assertEqual(dev[0].severity, "high")
        msg = format_alert(dev[0].__dict__)
        self.assertIn("why:", msg)

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
