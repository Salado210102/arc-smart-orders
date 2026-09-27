import unittest

from bot.store import SubscriptionStore
from bot.telegram import (matches, dispatch, AlertLoop, safe_call, apply_collapse_cooldown,
                          is_transient_poll_error)
from indexer.alerts import Alert


class FakeTransport:
    def __init__(self):
        self.sent = []

    def send(self, chat_id, text):
        self.sent.append((chat_id, text))


class TelegramTests(unittest.TestCase):
    def setUp(self):
        self.store = SubscriptionStore(":memory:")

    def tearDown(self):
        self.store.close()

    def test_subscribe_and_list(self):
        self.store.subscribe(chat_id=1, tokens=("0xt",), kinds=("dev_sell",))
        subs = self.store.list()
        self.assertEqual(len(subs), 1)
        self.assertIn("0xt", subs[0]["tokens"])
        self.assertIn("dev_sell", subs[0]["kinds"])

    def test_matches_token_and_kind(self):
        sub = {"tokens": {"0xt"}, "kinds": {"dev_sell"}}
        self.assertTrue(matches(sub, {"token": "0xt", "kind": "dev_sell"}))
        self.assertFalse(matches(sub, {"token": "0xt", "kind": "thin_market"}))
        self.assertFalse(matches(sub, {"token": "0xother", "kind": "dev_sell"}))

    def test_wildcard_all(self):
        sub = {"tokens": {"*"}, "kinds": set()}
        self.assertTrue(matches(sub, {"token": "anything", "kind": "dev_sell"}))

    def test_dispatch_and_dedupe(self):
        self.store.subscribe(chat_id=1, tokens=("0xt",), kinds=("dev_sell",))
        alerts = [{"token": "0xt", "kind": "dev_sell", "severity": "high", "block": 10,
                   "message": "hello"}]
        t = FakeTransport()
        n = dispatch(alerts, self.store, t)
        self.assertEqual(n, 1)
        self.assertEqual(t.sent[0][0], "1")
        self.assertIn("hello", t.sent[0][1])
        # persistent dedup: second dispatch sends nothing (even with a new transport)
        self.assertEqual(dispatch(alerts, self.store, FakeTransport()), 0)

    def test_state_cursor_persists(self):
        self.store.set_state("alert_cursor", "123")
        self.assertEqual(self.store.get_state("alert_cursor"), "123")

    def test_per_chat_cap(self):
        self.store.subscribe(chat_id=1, tokens=("0xt",), kinds=("dev_sell",))
        self.store.subscribe(chat_id=2, tokens=("0xt",), kinds=("dev_sell",))
        alerts = [{"token": "0xt", "kind": "dev_sell", "block": i, "severity": "high",
                   "message": "m"} for i in range(5)]
        n = dispatch(alerts, self.store, FakeTransport(), per_chat_cap=2)
        self.assertEqual(n, 4)  # 2 per chat x 2 chats

    def test_since_block_skips_old_alerts(self):
        self.store.subscribe(chat_id=1, tokens=("0xt",), kinds=("dev_sell",))
        self.store.conn.execute("UPDATE subscribers SET since_block=100 WHERE chat_id='1'")
        self.store.conn.commit()
        alerts = [{"token": "0xt", "kind": "dev_sell", "block": 50, "severity": "high", "message": "old"},
                  {"token": "0xt", "kind": "dev_sell", "block": 150, "severity": "high", "message": "new"}]
        t = FakeTransport()
        n = dispatch(alerts, self.store, t)
        self.assertEqual(n, 1)
        self.assertIn("new", t.sent[0][1])

    def test_dispatch_uses_rich_html_for_html_transport(self):
        self.store.subscribe(chat_id=1, tokens=("0xt",), kinds=("dev_sell",))

        class HtmlTransport:
            send_html = True

            def __init__(self):
                self.calls = []

            def send(self, chat_id, text, parse_mode=None):
                self.calls.append((chat_id, text, parse_mode))

        t = HtmlTransport()
        alerts = [{"token": "0xt", "kind": "dev_sell", "severity": "high", "block": 1,
                   "message": "creator sold 100%", "context": {"symbol": "BTS"}}]
        dispatch(alerts, self.store, t)
        self.assertEqual(t.calls[0][2], "HTML")
        self.assertIn("<b>", t.calls[0][1])

    def test_paper_store_and_live_report(self):
        from indexer.paper_eval import live_report
        self.store.add_paper_alert("dev_sell", "0xt", 100, 1000)
        self.assertEqual(len(self.store.list_pending_paper_alerts(1000000, 45)), 1)
        self.store.save_paper_outcome("dev_sell", "0xt", 100, 45, 1001,
                                      '{"1h":{"benefit_delayed":0.1,"benefit_instant":0.2}}')
        self.assertEqual(len(self.store.list_pending_paper_alerts(1000000, 45)), 0)
        rep = live_report(self.store, 45)
        self.assertEqual(rep["dev_sell"]["n_alerts"], 1)

    def test_transient_poll_error_classification(self):
        import socket
        import urllib.error
        self.assertTrue(is_transient_poll_error(TimeoutError()))
        self.assertTrue(is_transient_poll_error(socket.timeout()))
        self.assertTrue(is_transient_poll_error(urllib.error.URLError("x")))
        self.assertFalse(is_transient_poll_error(ValueError("a real bug")))

    def test_collapse_cooldown(self):
        a1 = Alert(token="0xt", kind="volume_collapse", severity="high", block=1)
        a2 = Alert(token="0xt", kind="volume_collapse", severity="high", block=2)
        dev = Alert(token="0xt", kind="dev_sell", severity="high", block=3)

        kept = apply_collapse_cooldown([a1, a2], self.store, 1000, 3600)
        self.assertEqual(len(kept), 1)  # second suppressed
        # after the window, allowed again
        kept2 = apply_collapse_cooldown([a2], self.store, 1000 + 3601, 3600)
        self.assertEqual(len(kept2), 1)
        # dev_sell is not affected
        kept3 = apply_collapse_cooldown([dev, dev], self.store, 1000, 3600)
        self.assertEqual(len(kept3), 2)

    def test_safe_call_keeps_loop_alive(self):
        result, err = safe_call(lambda: 5)
        self.assertEqual(result, 5)
        self.assertIsNone(err)

        def boom():
            raise RuntimeError("rpc hiccup")

        result, err = safe_call(boom)
        self.assertIsNone(result)
        self.assertEqual(err, "RuntimeError")

    def test_queue_no_discard(self):
        self.store.subscribe(chat_id=1, tokens=("0xt",), kinds=("dev_sell",))
        for i in range(5):
            self.store.enqueue_alert({"token": f"0x{i}", "kind": "dev_sell", "block": i,
                                      "severity": "high", "message": "m"})
        self.assertEqual(self.store.queue_size(), 5)
        # enqueue is idempotent by (token,kind,block)
        self.store.enqueue_alert({"token": "0x0", "kind": "dev_sell", "block": 0,
                                  "severity": "high", "message": "m"})
        self.assertEqual(self.store.queue_size(), 5)
        batch = self.store.dequeue(2)
        self.assertEqual(len(batch), 2)
        dispatch(batch, self.store, FakeTransport())
        for a in batch:
            self.store.remove_from_queue(a["token"], a["kind"], a["block"])
        self.assertEqual(self.store.queue_size(), 3)  # excess preserved, not discarded

    def test_dispatch_never_pushes_thin_market(self):
        self.store.subscribe(chat_id=1, tokens=("0xt",), kinds=())
        alerts = [{"token": "0xt", "kind": "thin_market", "severity": "low", "block": 1,
                   "message": "thin"}]
        self.assertEqual(dispatch(alerts, self.store, FakeTransport()), 0)

    def test_alert_loop_logs_per_cycle(self):
        self.store.subscribe(chat_id=1, tokens=("0xt",), kinds=("dev_sell",))
        logs = []
        alerts = [{"token": "0xt", "kind": "dev_sell", "severity": "high", "block": 5,
                   "message": "x"}]
        loop = AlertLoop(self.store, FakeTransport(), lambda: alerts, logger=logs.append)
        self.assertEqual(loop.run_once(), 1)
        self.assertEqual(logs[0]["dispatched"], 1)
        self.assertEqual(logs[0]["alerts"], 1)
        # dedupe on second cycle
        self.assertEqual(loop.run_once(), 0)
        self.assertEqual(logs[1]["dispatched"], 0)


if __name__ == "__main__":
    unittest.main()
