"""Minimal signing endpoint for protective pre-orders (Mini App / WalletConnect).

GET  /order?t=<sign_token>  -> the EIP-712 payload the wallet must sign (one-time token per order)
POST /sign  {t, signature}  -> stores the signature and marks the pre-order 'signed'

Stdlib only. Runs next to the bot; expose it behind HTTPS (reverse proxy) for the Mini App.
"""
from __future__ import annotations

import json
import os
import re
import threading
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

    def _buy(self, uid, addr, amount_usdc, slippage, persist):
        """Buy quote (and, if persist, a stored buy order) -> (http_code, body)."""
        if not ADDR_RE.match(addr or ""):
            return 400, {"error": "bad_address"}
        try:
            amount_usdc = float(amount_usdc)
            slippage = float(slippage)
        except (TypeError, ValueError):
            return 400, {"error": "bad_amount"}
        if amount_usdc <= 0 or slippage < 0:
            return 400, {"error": "bad_amount"}
        executor = os.environ.get("ARC_INTEL_EXECUTOR")
        if not executor:
            return 503, {"error": "no_executor"}
        st = _storage()
        if st is None:
            return 503, {"error": "no_storage"}
        from . import tokenmeta
        from .miniapp_data import load_pool, load_token_card
        from execution.quotes import buy_quote, build_buy_payload
        from execution.eip712 import new_nonce
        stable = os.environ.get("ARC_INTEL_STABLE", "0x3600000000000000000000000000000000000000")
        pool = load_pool(st, addr)
        if not pool:
            return 404, {"error": "no_pool"}
        card = load_token_card(st, addr)
        amount_in_base = int(round(amount_usdc * (10 ** 6)))
        try:
            quote = buy_quote(amount_in_base=amount_in_base, token_price=card["price"],
                              token_decimals=tokenmeta.rpc_decimals(addr), slippage_pct=slippage)
        except ValueError as e:
            return 400, {"error": str(e)}
        store = SubscriptionStore(DB)
        try:
            recipient = store.get_linked_wallet(uid)
        finally:
            store.close()
        resp = {"preview": not persist, "persisted": persist, "token": card, "pool": pool,
                "quote": quote, "slippage_pct": slippage, "recipient": recipient or None,
                "payload": None}
        if not recipient:
            resp["hint"] = "link_wallet"
            return 200, resp
        import time as _t
        chain_id = int(os.environ.get("ARC_INTEL_CHAIN_ID", "5042"))
        deadline = int(_t.time()) + int(os.environ.get("ARC_INTEL_ORDER_TTL", "1800"))
        order_nonce = new_nonce()
        permit_nonce = new_nonce()
        resp["payload"] = build_buy_payload(
            chain_id=chain_id, executor=executor, pool=pool, stable=stable,
            amount_in_base=amount_in_base, min_out_base=quote["min_out_base"],
            recipient=recipient, order_nonce=order_nonce, permit_nonce=permit_nonce,
            deadline=deadline)
        if persist:
            store = SubscriptionStore(DB)
            try:
                pid = store.create_preorder(uid, recipient, addr, 0.0, slippage,
                                            quote["min_out_base"], deadline, order_nonce,
                                            status="armed", kind="buy")
                store.save_sig_payload(pid, json.dumps(resp["payload"]))
                po = store.get_preorder(pid)
            finally:
                store.close()
            resp.update({"id": pid, "sign_token": po["sign_token"],
                         "sign_url": f"/?t={po['sign_token']}"})
        return 200, resp

    def _kick_keeper(self):
        """Fire-and-forget: submit any signed buy order now (only if a relayer is configured)."""
        def _run():
            try:
                from execution.keeper import run_keeper
                s = SubscriptionStore(DB)
                try:
                    run_keeper(s)
                finally:
                    s.close()
            except Exception:
                pass
        threading.Thread(target=_run, daemon=True).start()

    def _plan(self, uid, addr, pct, floor_pct):
        """Create a protective/limit SELL pre-order (EIP-712 payload) for a % of the position."""
        if not ADDR_RE.match(addr or ""):
            return 400, {"error": "bad_address"}
        try:
            pct = float(pct)
            floor = float(floor_pct)
        except (TypeError, ValueError):
            return 400, {"error": "bad_amount"}
        if not (0 < pct <= 100) or floor < 0 or floor > 99:
            return 400, {"error": "bad_amount"}
        executor = os.environ.get("ARC_INTEL_EXECUTOR")
        if not executor:
            return 503, {"error": "no_executor"}
        st = _storage()
        if st is None:
            return 503, {"error": "no_storage"}
        from . import tokenmeta
        from .miniapp_data import load_pool, latest_price
        from execution.quotes import sell_quote, build_sell_payload
        from execution.eip712 import new_nonce
        stable = os.environ.get("ARC_INTEL_STABLE", "0x3600000000000000000000000000000000000000")
        pool = load_pool(st, addr)
        if not pool:
            return 404, {"error": "no_pool"}
        price = latest_price(st, addr)
        if price <= 0:
            return 409, {"error": "no_price"}
        store = SubscriptionStore(DB)
        try:
            recipient = store.get_linked_wallet(uid)
            pos = store.get_position(uid, addr)
        finally:
            store.close()
        if not recipient:
            return 409, {"error": "link_wallet"}
        if pos["qty"] <= 0:
            return 409, {"error": "no_position"}
        qty = pos["qty"] * pct / 100.0
        quote = sell_quote(qty=qty, price=price, token_decimals=tokenmeta.rpc_decimals(addr),
                           floor_pct=floor)
        import time as _t
        chain_id = int(os.environ.get("ARC_INTEL_CHAIN_ID", "5042"))
        deadline = int(_t.time()) + 30 * 24 * 3600
        order_nonce = new_nonce()
        permit_nonce = new_nonce()
        payload = build_sell_payload(
            chain_id=chain_id, executor=executor, pool=pool, stable=stable, token=addr,
            amount_in_base=quote["amount_in_base"], min_out_base=quote["min_out_base"],
            recipient=recipient, order_nonce=order_nonce, permit_nonce=permit_nonce,
            deadline=deadline)
        store = SubscriptionStore(DB)
        try:
            pid = store.create_preorder(uid, recipient, addr, pct, floor, quote["min_out_base"],
                                        deadline, order_nonce, status="armed", kind="sell")
            store.save_sig_payload(pid, json.dumps(payload))
            po = store.get_preorder(pid)
        finally:
            store.close()
        return 200, {"id": pid, "sign_token": po["sign_token"], "sign_url": f"/?t={po['sign_token']}",
                     "qty": qty, "quote": quote}

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
        if u.path == "/alerts":
            uid = self._auth_user()
            if uid is None:
                return self._send(401, {"error": "unauthorized"})
            store = SubscriptionStore(DB)
            try:
                row = store.get(uid)
                toks = sorted(row["tokens"]) if row else []
                kinds = sorted(row["kinds"]) if row else []
                al = store.recent_alerts(tokens=toks, kinds=kinds, limit=50) if toks else []
            finally:
                store.close()
            return self._send(200, {"alerts": al})
        if u.path == "/series":
            uid = self._auth_user()
            if uid is None:
                return self._send(401, {"error": "unauthorized"})
            tok = (parse_qs(u.query).get("token") or [""])[0]
            if not ADDR_RE.match(tok or ""):
                return self._send(400, {"error": "bad_address"})
            st = _storage()
            if st is None:
                return self._send(503, {"error": "no_storage"})
            try:
                from .miniapp_data import load_series
                return self._send(200, load_series(st, tok))
            except Exception:
                return self._send(502, {"error": "series_failed"})
        if u.path == "/buy_quote":
            uid = self._auth_user()
            if uid is None:
                return self._send(401, {"error": "unauthorized"})
            q = parse_qs(u.query)
            code, resp = self._buy(uid, (q.get("token") or [""])[0],
                                   (q.get("amount_usdc") or ["0"])[0],
                                   (q.get("slippage") or ["1"])[0], persist=False)
            return self._send(code, resp)
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
        if u.path == "/buy_order":
            uid = self._auth_user()
            if uid is None:
                return self._send(401, {"error": "unauthorized"})
            n = int(self.headers.get("Content-Length") or 0)
            try:
                data = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._send(400, {"error": "bad_json"})
            code, resp = self._buy(uid, data.get("token") or "", data.get("amount_usdc") or 0,
                                   data.get("slippage", 1), persist=True)
            return self._send(code, resp)
        if u.path == "/plan":
            uid = self._auth_user()
            if uid is None:
                return self._send(401, {"error": "unauthorized"})
            n = int(self.headers.get("Content-Length") or 0)
            try:
                data = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._send(400, {"error": "bad_json"})
            code, resp = self._plan(uid, data.get("token") or "", data.get("pct") or 0,
                                    data.get("floor_pct", 30))
            return self._send(code, resp)
        if u.path == "/cancel":
            uid = self._auth_user()
            if uid is None:
                return self._send(401, {"error": "unauthorized"})
            n = int(self.headers.get("Content-Length") or 0)
            try:
                data = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._send(400, {"error": "bad_json"})
            try:
                pid = int(data.get("id"))
            except (TypeError, ValueError):
                return self._send(400, {"error": "bad_id"})
            store = SubscriptionStore(DB)
            try:
                ok = store.cancel_preorder(pid, uid)
            finally:
                store.close()
            return self._send(200 if ok else 404, {"ok": ok})
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
            if po.get("kind") == "buy":
                self._kick_keeper()   # execute a signed buy immediately (no-op if no relayer)
            return self._send(200, {"ok": True, "id": po["id"], "kind": po.get("kind")})
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
