import unittest

from bot.store import SubscriptionStore
from execution.keeper import run_keeper

TOKEN = "0x" + "a" * 40
USER = "0x" + "b" * 40


class KeeperTests(unittest.TestCase):
    def setUp(self):
        self.store = SubscriptionStore(":memory:")

    def tearDown(self):
        self.store.close()

    def _signed_buy(self, deadline=9999999999):
        pid = self.store.create_preorder(1, USER, TOKEN, 0, 2, 100, deadline, 1,
                                         status="armed", kind="buy")
        self.store.set_preorder_status(pid, "signed")
        return pid

    def test_not_configured_is_noop(self):
        self._signed_buy()
        r = run_keeper(self.store, executor="", relayer="")
        self.assertEqual(r.get("skipped"), "not_configured")
        self.assertEqual(r["submitted"], 0)

    def test_submits_due_buy(self):
        pid = self._signed_buy()
        calls = []
        r = run_keeper(self.store, executor="0xe", relayer="0xk", now=1,
                       submit=lambda po: (calls.append(po["id"]) or "0xtx"))
        self.assertEqual(r["submitted"], 1)
        self.assertEqual(calls, [pid])
        self.assertEqual(self.store.get_preorder(pid)["status"], "executed")

    def test_skips_expired(self):
        self._signed_buy(deadline=10)
        r = run_keeper(self.store, executor="0xe", relayer="0xk", now=100,
                       submit=lambda po: "0xtx")
        self.assertEqual(r["submitted"], 0)

    def test_failure_reverts_to_signed(self):
        pid = self._signed_buy()

        def boom(po):
            raise RuntimeError("revert")

        r = run_keeper(self.store, executor="0xe", relayer="0xk", now=1, submit=boom)
        self.assertEqual(r["failed"], 1)
        self.assertEqual(self.store.get_preorder(pid)["status"], "signed")  # retryable

    def test_ignores_sell_orders(self):
        pid = self.store.create_preorder(1, USER, TOKEN, 50, 30, 0, 9999999999, 2,
                                         status="signed", kind="sell")
        r = run_keeper(self.store, executor="0xe", relayer="0xk", now=1,
                       submit=lambda po: "0xtx")
        self.assertEqual(r["submitted"], 0)
        self.assertEqual(self.store.get_preorder(pid)["status"], "signed")


if __name__ == "__main__":
    unittest.main()
