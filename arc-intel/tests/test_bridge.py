import unittest

from bot.bridge import deposit_delta, bridge_link, poll_deposits
from bot.store import SubscriptionStore


class BridgePureTests(unittest.TestCase):
    def test_deposit_delta(self):
        self.assertEqual(deposit_delta(10, 25), 15)
        self.assertEqual(deposit_delta(25, 10), 0)
        self.assertEqual(deposit_delta(0, 0), 0)

    def test_bridge_link(self):
        self.assertEqual(bridge_link("https://b.io", "0xabc"), "https://b.io?to=0xabc&token=USDC")
        self.assertEqual(bridge_link("https://b.io?x=1", "0xabc"),
                         "https://b.io?x=1&to=0xabc&token=USDC")
        self.assertEqual(bridge_link("", "0xabc"), "")


class _T:
    def __init__(self):
        self.msgs = []

    def send(self, chat, text, **kw):
        self.msgs.append((chat, text))


class _Thr:
    def wait(self, chat):
        pass


class BridgePollTests(unittest.TestCase):
    def setUp(self):
        self.s = SubscriptionStore(":memory:")

    def tearDown(self):
        self.s.close()

    def test_detects_arrival_after_baseline(self):
        self.s.save_custody(1, "0x" + "a" * 40, "enc")
        t = _T()
        self.assertEqual(poll_deposits(self.s, t, _Thr(), balance_fn=lambda a: 10.0), 0)  # baseline
        self.assertEqual(t.msgs, [])
        n = poll_deposits(self.s, t, _Thr(), balance_fn=lambda a: 25.0)
        self.assertEqual(n, 1)
        self.assertIn("15.00", t.msgs[0][1])

    def test_no_notify_on_decrease_or_dust(self):
        self.s.save_custody(1, "0x" + "a" * 40, "enc")
        t = _T()
        poll_deposits(self.s, t, _Thr(), balance_fn=lambda a: 10.0)
        self.assertEqual(poll_deposits(self.s, t, _Thr(), balance_fn=lambda a: 10.2), 0)  # dust
        self.assertEqual(poll_deposits(self.s, t, _Thr(), balance_fn=lambda a: 5.0), 0)   # decrease
        self.assertEqual(t.msgs, [])

    def test_skips_balance_errors(self):
        self.s.save_custody(1, "0x" + "a" * 40, "enc")

        def boom(a):
            raise RuntimeError("rpc")

        self.assertEqual(poll_deposits(self.s, _T(), _Thr(), balance_fn=boom), 0)


if __name__ == "__main__":
    unittest.main()
