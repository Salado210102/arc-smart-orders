"""Minimal signing endpoint for protective pre-orders (Mini App / WalletConnect).

GET  /order?t=<sign_token>  -> the EIP-712 payload the wallet must sign (one-time token per order)
POST /sign  {t, signature}  -> stores the signature and marks the pre-order 'signed'

Stdlib only. Runs next to the bot; expose it behind HTTPS (reverse proxy) for the Mini App.
"""
from __future__ import annotations

import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .store import SubscriptionStore

DB = os.environ.get("ARC_INTEL_DB", "/root/arc-intel/bot_subs.db")
ALLOWED_ORIGIN = os.environ.get("ARC_INTEL_ALLOWED_ORIGIN", "https://app.basepump.dev")
ADDR_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_STORAGE = None


def _storage():
    """Lazy PG (indexer) connection; None if ARC_INTEL_DSN is not set."""
    global _STORAGE
    if _STORAGE is None:
        dsn = os.environ.get("ARC_INTEL_DSN")
        if not dsn:
            return None
        from indexer.pg_storage import PostgresStorage
        _STORAGE = PostgresStorage(dsn, minconn=1, maxconn=4)
    return _STORAGE


def _bot_token():
    try:
        from .telegram import load_token
        return load_token()
    except Exception:
        return os.environ.get("TELEGRAM_BOT_TOKEN")


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Headers", "Content-Type,X-Telegram-Init-Data")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def _auth_user(self):
        """Validate Telegram WebApp initData -> user id, or None."""
        from .telegram_auth import validate_init_data
        data = validate_init_data(self.headers.get("X-Telegram-Init-Data") or "", _bot_token() or "")
        if not data:
            return None
        u = data.get("user")
        return u.get("id") if isinstance(u, dict) else None

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
            self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
            self.send_header("Vary", "Origin")
            self.end_headers()
            self.wfile.write(body)
            return
        if u.path == "/health":
            return self._send(200, {"ok": True})
        if u.path == "/token":
            addr = (parse_qs(u.query).get("address") or [""])[0]
            if not ADDR_RE.match(addr or ""):
                return self._send(400, {"error": "bad_address"})
            st = _storage()
            if st is None:
                return self._send(503, {"error": "no_storage"})
            try:
                from .miniapp_data import load_token_card
                return self._send(200, load_token_card(st, addr))
            except Exception:
                return self._send(502, {"error": "token_failed"})
        if u.path in ("/positions", "/wallet"):
            uid = self._auth_user()
            if uid is None:
                return self._send(401, {"error": "unauthorized"})
            store = SubscriptionStore(DB)
            try:
                if u.path == "/wallet":
                    from .miniapp_api import wallet_view
                    return self._send(200, wallet_view(store, uid))
                from .miniapp_api import position_views, portfolio_summary
                st = _storage()
                holder = store.get_linked_wallet(uid)
                pf = bf = None
                if st is not None:
                    from .miniapp_data import price_fn, balance_fn_for
                    pf = price_fn(st)
                    bf = balance_fn_for(holder) if holder else None
                views = position_views(store, uid, pf, bf)
                return self._send(200, {"positions": views, "summary": portfolio_summary(views)})
            finally:
                store.close()
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
    host = os.environ.get("ARC_INTEL_SIGN_HOST", "127.0.0.1")
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"sign server on {host}:{port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
