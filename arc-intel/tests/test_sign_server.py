import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from bot.store import SubscriptionStore
import bot.sign_server as ss

TOK = "0x" + "a" * 40


class SignServerTests(unittest.TestCase):
    def setUp(self):
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

    def test_unknown_token_404(self):
        try:
            urllib.request.urlopen(self._url("/order?t=nope"))
            self.fail("expected error")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 404)


if __name__ == "__main__":
    unittest.main()
