import unittest

from bot.store import SubscriptionStore
from bot.wallet_track import scan_wallets


class FakeCursor:
    def __init__(self, tokens):
        self.tokens = tokens

    def execute(self, sql, params=None):
        pass

    def fetchall(self):
        return [(t,) for t in self.tokens]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeConn:
    def __init__(self, tokens):
        self.tokens = tokens

    def cursor(self):
        return FakeCursor(self.tokens)


class FakePool:
    def __init__(self, tokens):
        self.tokens = tokens

    def getconn(self):
        return FakeConn(self.tokens)

    def putconn(self, c):
        pass


class FakeStorage:
    def __init__(self, tokens):
        self.pool = FakePool(tokens)


class WalletTrackTests(unittest.TestCase):
    def setUp(self):
        self.store = SubscriptionStore(":memory:")

    def tearDown(self):
        self.store.close()

    def test_scan_autosubscribes_then_unsubscribes(self):
        self.store.link_wallet(1, "0xabc")
        storage = FakeStorage(["0xtok1", "0xtok2"])
        bal = {("0xabc", "0xtok1"): 100, ("0xabc", "0xtok2"): 0}

        r = scan_wallets(storage, self.store, balance_fn=lambda a, t: bal.get((a, t), 0), head=1000)
        self.assertEqual(r["new_subs"], 1)
        self.assertTrue(self.store.is_auto_sub(1, "0xtok1"))
        self.assertIn("0xtok1", self.store.get(1)["tokens"])

        bal[("0xabc", "0xtok1")] = 0  # user sold
        r2 = scan_wallets(storage, self.store, balance_fn=lambda a, t: bal.get((a, t), 0), head=2000)
        self.assertEqual(r2["dropped_subs"], 1)
        self.assertNotIn("0xtok1", self.store.get(1)["tokens"])

    def test_manual_subscription_not_dropped(self):
        self.store.link_wallet(1, "0xabc")
        self.store.add_token(1, "0xtok1", now_block=0)  # MANUAL
        storage = FakeStorage(["0xtok1"])
        r = scan_wallets(storage, self.store, balance_fn=lambda a, t: 0, head=1000)
        self.assertEqual(r["dropped_subs"], 0)
        self.assertIn("0xtok1", self.store.get(1)["tokens"])

    def test_manual_promote_protects_from_autoremove(self):
        self.store.link_wallet(1, "0xabc")
        storage = FakeStorage(["0xtok1"])
        scan_wallets(storage, self.store, balance_fn=lambda a, t: 5, head=1000)
        self.assertTrue(self.store.is_auto_sub(1, "0xtok1"))
        self.store.promote_to_manual(1, "0xtok1")   # user /subscribe
        scan_wallets(storage, self.store, balance_fn=lambda a, t: 0, head=2000)
        self.assertIn("0xtok1", self.store.get(1)["tokens"])

    def test_failed_balance_call_changes_nothing(self):
        self.store.link_wallet(1, "0xabc")
        self.store.add_auto_sub(1, "0xtok1", now_block=0)
        storage = FakeStorage(["0xtok1"])
        r = scan_wallets(storage, self.store, balance_fn=lambda a, t: None, head=1000)  # RPC failed
        self.assertEqual(r["dropped_subs"], 0)
        self.assertIn("0xtok1", self.store.get(1)["tokens"])

    def test_unlink_removes_auto_keeps_manual(self):
        self.store.link_wallet(1, "0xabc")
        self.store.set_wallet(1, "0xabc")
        self.store.add_auto_sub(1, "0xauto", now_block=0)
        self.store.add_token(1, "0xmanual", now_block=0)
        n = self.store.unlink_wallet(1)
        self.assertEqual(n, 1)
        toks = self.store.get(1)["tokens"]
        self.assertNotIn("0xauto", toks)
        self.assertIn("0xmanual", toks)
        self.assertEqual(self.store.get_linked_wallet(1), "")
        self.assertEqual(self.store.get_wallet(1), "")


if __name__ == "__main__":
    unittest.main()
