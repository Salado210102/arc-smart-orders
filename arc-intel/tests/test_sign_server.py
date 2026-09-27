import json
import os
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from urllib.parse import urlencode

from bot.store import SubscriptionStore
from bot.telegram_auth import sign_init_data
import bot.sign_server as ss

TOK = "0x" + "a" * 40
BOT_TOKEN = "123456:TESTTOKENabcdefghijklmnopqrstuvwxyz"


def init_data(user_id=1, auth_date=None):
    fields = {"auth_date": str(int(auth_date if auth_date is not None else time.time())),
              "user": json.dumps({"id": user_id, "first_name": "T"})}
    fields["hash"] = sign_init_data(fields, BOT_TOKEN)
    return urlencode(fields)


class SignServerTests(unittest.TestCase):
    def setUp(self):
        self._old_tok = os.environ.get("TELEGRAM_BOT_TOKEN")
        os.environ["TELEGRAM_BOT_TOKEN"] = BOT_TOKEN
        self.db = tempfile.mktemp(suffix=".db")
        ss.DB = self.db
        store = SubscriptionStore(self.db)
        self.pid = store.create_preorder(1, 1, TOK, 100, 30, 70, 9999999999, 123)
        self.po = store.get_preorder(self.pid)
        store.save_sig_payload(self.pid, json.dumps({"typedData": {"x": 1}}))
        store.close()
        self.srv = ss.ThreadingHTTPServer(("127.0.0.1", 0), ss.Handler)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        if self._old_tok is None:
            os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        else:
            os.environ["TELEGRAM_BOT_TOKEN"] = self._old_tok
        try:
            os.remove(self.db)
        except OSError:
            pass

    def _url(self, p):
        return f"http://127.0.0.1:{self.port}{p}"

    def test_get_order_and_sign(self):
        t = self.po["sign_token"]
        r = json.load(urllib.request.urlopen(self._url(f"/order?t={t}")))
        self.assertEqual(r["preorder"]["id"], self.pid)
        self.assertIsNotNone(r["payload"])

        body = json.dumps({"t": t, "signature": "0xdead"}).encode()
        req = urllib.request.Request(self._url("/sign"), data=body,
                                     headers={"Content-Type": "application/json"})
        r2 = json.load(urllib.request.urlopen(req))
        self.assertTrue(r2["ok"])

        s2 = SubscriptionStore(self.db)
        self.assertEqual(s2.get_preorder(self.pid)["status"], "signed")
        self.assertEqual(s2.get_preorder(self.pid)["signature"], "0xdead")
        s2.close()

    def test_serves_miniapp_page(self):
        html = urllib.request.urlopen(self._url("/")).read().decode()
        self.assertIn("SNIPER IA", html)

    def test_unknown_token_404(self):
        try:
            urllib.request.urlopen(self._url("/order?t=nope"))
            self.fail("expected error")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 404)

    def test_health(self):
        r = json.load(urllib.request.urlopen(self._url("/health")))
        self.assertTrue(r["ok"])

    def test_positions_requires_auth(self):
        try:
            urllib.request.urlopen(self._url("/positions"))
            self.fail("expected 401")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 401)

    def test_positions_rejects_bad_initdata(self):
        req = urllib.request.Request(self._url("/positions"),
                                     headers={"X-Telegram-Init-Data": "auth_date=1&user=%7B%7D"})
        try:
            urllib.request.urlopen(req)
            self.fail("expected 401")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 401)

    def test_wallet_with_auth(self):
        req = urllib.request.Request(self._url("/wallet"),
                                     headers={"X-Telegram-Init-Data": init_data(1)})
        r = json.load(urllib.request.urlopen(req))
        self.assertIn("linked_wallet", r)
        self.assertIn("auto_subs", r)

    def test_positions_with_auth_no_storage(self):
        os.environ.pop("ARC_INTEL_DSN", None)
        req = urllib.request.Request(self._url("/positions"),
                                     headers={"X-Telegram-Init-Data": init_data(1)})
        r = json.load(urllib.request.urlopen(req))
        self.assertEqual(r["positions"], [])
        self.assertIn("summary", r)

    def test_token_bad_address(self):
        try:
            urllib.request.urlopen(self._url("/token?address=0x123"))
            self.fail("expected 400")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)

    def test_token_no_storage(self):
        os.environ.pop("ARC_INTEL_DSN", None)
        try:
            urllib.request.urlopen(self._url("/token?address=" + "0x" + "1" * 40))
            self.fail("expected 503")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 503)

    def test_buy_quote_requires_auth(self):
        try:
            urllib.request.urlopen(self._url("/buy_quote?token=" + "0x" + "1" * 40))
            self.fail("expected 401")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 401)

    def test_buy_quote_bad_address(self):
        req = urllib.request.Request(self._url("/buy_quote?token=0x123"),
                                     headers={"X-Telegram-Init-Data": init_data(1)})
        try:
            urllib.request.urlopen(req)
            self.fail("expected 400")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)

    def test_buy_quote_no_storage(self):
        os.environ.pop("ARC_INTEL_DSN", None)
        req = urllib.request.Request(
            self._url("/buy_quote?token=" + "0x" + "1" * 40 + "&amount_usdc=10"),
            headers={"X-Telegram-Init-Data": init_data(1)})
        try:
            urllib.request.urlopen(req)
            self.fail("expected 503")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 503)

    def test_sessions_requires_auth(self):
        try:
            urllib.request.urlopen(self._url("/sessions"))
            self.fail("expected 401")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 401)

    def test_session_authorize_requires_auth(self):
        body = json.dumps({"token": "0x" + "1" * 40}).encode()
        req = urllib.request.Request(self._url("/session/authorize"), data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req)
            self.fail("expected 401")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 401)

    def test_sell_order_requires_auth(self):
        body = json.dumps({"token": "0x" + "1" * 40, "pct": 50}).encode()
        req = urllib.request.Request(self._url("/sell_order"), data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req)
            self.fail("expected 401")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 401)

    def test_session_revoke_requires_auth(self):
        body = json.dumps({"session_key": "0x" + "b" * 40}).encode()
        req = urllib.request.Request(self._url("/session/revoke"), data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req)
            self.fail("expected 401")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 401)

    def test_alerts_requires_auth(self):
        try:
            urllib.request.urlopen(self._url("/alerts"))
            self.fail("expected 401")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 401)

    def test_alerts_with_auth_empty(self):
        req = urllib.request.Request(self._url("/alerts"),
                                     headers={"X-Telegram-Init-Data": init_data(1)})
        r = json.load(urllib.request.urlopen(req))
        self.assertEqual(r["alerts"], [])

    def test_series_bad_address(self):
        req = urllib.request.Request(self._url("/series?token=0x1"),
                                     headers={"X-Telegram-Init-Data": init_data(1)})
        try:
            urllib.request.urlopen(req)
            self.fail("expected 400")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)

    def test_add_alert_dedup_and_filter(self):
        s = SubscriptionStore(self.db)
        s.add_alert({"token": TOK, "kind": "dev_sell", "severity": "high", "block": 5,
                     "message": "x"}, ts=1)
        s.add_alert({"token": TOK, "kind": "dev_sell", "severity": "high", "block": 5,
                     "message": "x"}, ts=1)   # duplicate (token,kind,block) -> ignored
        s.add_alert({"token": "0x" + "b" * 40, "kind": "large_sell", "severity": "medium",
                     "block": 6, "message": "y"}, ts=1)
        self.assertEqual(len(s.recent_alerts()), 2)
        only = s.recent_alerts(tokens=[TOK])
        self.assertEqual(len(only), 1)
        self.assertEqual(only[0]["kind"], "dev_sell")
        s.close()

    def test_plan_requires_auth(self):
        body = json.dumps({"token": "0x" + "1" * 40, "pct": 50}).encode()
        req = urllib.request.Request(self._url("/plan"), data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req)
            self.fail("expected 401")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 401)

    def test_cancel_requires_auth(self):
        body = json.dumps({"id": 1}).encode()
        req = urllib.request.Request(self._url("/cancel"), data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req)
            self.fail("expected 401")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 401)

    def test_cancel_bad_id(self):
        body = json.dumps({"id": "x"}).encode()
        req = urllib.request.Request(self._url("/cancel"), data=body,
                                     headers={"Content-Type": "application/json",
                                              "X-Telegram-Init-Data": init_data(1)})
        try:
            urllib.request.urlopen(req)
            self.fail("expected 400")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)

    def test_cancel_marks_order(self):
        s = SubscriptionStore(self.db)
        pid = s.create_preorder(1, "0x" + "a" * 40, TOK, 50, 30, 0, 9999999999, 3,
                                status="armed", kind="sell")
        s.close()
        body = json.dumps({"id": pid}).encode()
        req = urllib.request.Request(self._url("/cancel"), data=body,
                                     headers={"Content-Type": "application/json",
                                              "X-Telegram-Init-Data": init_data(1)})
        r = json.load(urllib.request.urlopen(req))
        self.assertTrue(r["ok"])
        s = SubscriptionStore(self.db)
        self.assertEqual(s.get_preorder(pid)["status"], "cancelled")
        s.close()

    def test_buy_order_requires_auth(self):
        body = json.dumps({"token": "0x" + "1" * 40, "amount_usdc": 10}).encode()
        req = urllib.request.Request(self._url("/buy_order"), data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req)
            self.fail("expected 401")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 401)

    def test_buy_order_no_storage(self):
        os.environ.pop("ARC_INTEL_DSN", None)
        os.environ["ARC_INTEL_EXECUTOR"] = "0x" + "e" * 40
        body = json.dumps({"token": "0x" + "1" * 40, "amount_usdc": 10}).encode()
        req = urllib.request.Request(self._url("/buy_order"), data=body,
                                     headers={"Content-Type": "application/json",
                                              "X-Telegram-Init-Data": init_data(1)})
        try:
            urllib.request.urlopen(req)
            self.fail("expected 503")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 503)

    def test_buy_kind_excluded_from_fire_list(self):
        s = SubscriptionStore(self.db)
        other = "0x" + "b" * 40
        sell = s.create_preorder(1, "0xuser", other, 50, 30, 0, 9, 11, kind="sell")
        buy = s.create_preorder(1, "0xuser", other, 0, 2, 100, 9, 12, kind="buy")
        ids = [p["id"] for p in s.preorders_for_token(other)]
        self.assertEqual(ids, [sell])
        self.assertEqual(s.get_preorder(buy)["kind"], "buy")
        self.assertEqual(s.get_preorder(sell)["kind"], "sell")
        s.close()


if __name__ == "__main__":
    unittest.main()
