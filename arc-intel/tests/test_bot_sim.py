import unittest

from bot.sim import demo_flow


class SimTests(unittest.TestCase):
    def test_demo_flow_runs_and_contains_expected(self):
        lines = demo_flow()
        text = "\n".join(lines)
        self.assertIn("why: dev_sell", text)
        self.assertIn("min_out=19.800", text)
        self.assertIn("2fa_required", text)
        self.assertIn("approved", text)
        self.assertIn("take_profit", text)
        self.assertIn("stop_loss", text)
        self.assertIn("trailing_stop", text)


if __name__ == "__main__":
    unittest.main()
