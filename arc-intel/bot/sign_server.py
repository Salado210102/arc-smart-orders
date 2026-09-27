"""Minimal signing endpoint for protective pre-orders (Mini App / WalletConnect).

GET  /order?t=<sign_token>  -> the EIP-712 payload the wallet must sign (one-time token per order)
POST /sign  {t, signature}  -> stores the signature and marks the pre-order 'signed'

Stdlib only. Runs next to the bot; expose it behind HTTPS (reverse proxy) for the Mini App.
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .store import SubscriptionStore

DB = os.environ.get("ARC_INTEL_DB", "/root/arc-intel/bot_subs.db")


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):  # CORS preflight
        self._send(204, {})

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            path = os.environ.get("ARC_INTEL_MINIAPP", "/root/arc-intel/miniapp/index.html")
            try:
                with open(path, "rb") as fh:
                    body = fh.read()
            except OSError:
                return self._send(404, {"error": "miniapp_missing"})
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
            return
        if u.path != "/order":
            return self._send(404, {"error": "not_found"})
        tok = (parse_qs(u.query).get("t") or [""])[0]
        store = SubscriptionStore(DB)
        try:
            po = store.get_preorder_by_sign_token(tok)
            if not po:
                return self._send(404, {"error": "unknown_token"})
            if po["status"] not in ("armed", "signed"):
                return self._send(409, {"error": "not_armable", "status": po["status"]})
            payload = json.loads(po["sig_payload"]) if po["sig_payload"] else None
            return self._send(200, {"preorder": {"id": po["id"], "token": po["token"],
                                                 "pct": po["pct"], "status": po["status"]},
                                    "payload": payload})
        finally:
            store.close()

    def do_POST(self):
        u = urlparse(self.path)
        if u.path != "/sign":
            return self._send(404, {"error": "not_found"})
        n = int(self.headers.get("Content-Length") or 0)
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self._send(400, {"error": "bad_json"})
        tok = data.get("t") or ""
        sig = data.get("signature") or ""
        if not tok or not isinstance(sig, str) or not sig.startswith("0x"):
            return self._send(400, {"error": "missing_fields"})
        store = SubscriptionStore(DB)
        try:
            po = store.get_preorder_by_sign_token(tok)
            if not po:
                return self._send(404, {"error": "unknown_token"})
            if po["status"] == "executed":
                return self._send(409, {"error": "already_executed"})
            store.attach_signature(po["id"], sig)
            return self._send(200, {"ok": True, "id": po["id"]})
        finally:
            store.close()

    def log_message(self, *a):
        pass


def main():
    port = int(os.environ.get("ARC_INTEL_SIGN_PORT", "8790"))
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"sign server on :{port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
