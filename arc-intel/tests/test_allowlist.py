import unittest

from bot.store import SubscriptionStore
from bot.commands import is_authorized, command_reply, CLOSED_BETA


class AllowlistTests(unittest.TestCase):
    def setUp(self):
        self.store = SubscriptionStore(":memory:")

    def tearDown(self):
        self.store.close()

    def test_allow_deny(self):
        self.assertFalse(self.store.is_allowed("5"))
        self.store.add_allow("5")
        self.assertTrue(self.store.is_allowed("5"))
        self.assertIn("5", self.store.list_allow())
        self.assertTrue(self.store.remove_allow("5"))
        self.assertFalse(self.store.is_allowed("5"))

    def test_is_authorized_admin_or_allowed(self):
        self.store.set_state("admin_chat", "1")
        self.assertTrue(is_authorized(self.store, "1"))     # admin
        self.store.add_allow("2")
        self.assertTrue(is_authorized(self.store, "2"))     # allowed
        self.assertFalse(is_authorized(self.store, "3"))    # not allowed

    def test_allow_command_admin_only(self):
        self.store.set_state("admin_chat", "1")
        r = command_reply("/allow 9", "1", self.store, lambda t: True, lambda t: "", 0)
        self.assertIn("Allowed", r)
        self.assertTrue(self.store.is_allowed("9"))
        r2 = command_reply("/allow 10", "2", self.store, lambda t: True, lambda t: "", 0)
        self.assertIn("Not authorized", r2)

    def test_requests_recorded(self):
        self.store.add_request("7", 123)
        self.assertEqual(self.store.list_requests()[0]["chat_id"], "7")

    def test_closed_beta_message_no_internal_details(self):
        self.assertIn("closed beta", CLOSED_BETA.lower())
        self.assertNotIn("sqlite", CLOSED_BETA.lower())


if __name__ == "__main__":
    unittest.main()
