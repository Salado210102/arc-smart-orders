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


if __name__ == "__main__":
    unittest.main()
