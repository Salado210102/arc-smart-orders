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

    def _session_authorize(self, uid, data):
        """Generate a scoped session key + return the one-time setup txs for the wallet."""
        import time
        from execution import sessions as S
        from execution.eip712 import PERMIT2
        from .miniapp_data import load_pool
        addr = (data.get("token") or "").lower()
        if not ADDR_RE.match(addr):
            return 400, {"error": "bad_address"}
        executor = os.environ.get("ARC_INTEL_EXECUTOR")
        if not executor:
            return 503, {"error": "no_executor"}
        enc = os.environ.get("ARC_INTEL_SESSION_ENC_KEY")
        if not enc:
            return 503, {"error": "no_enc_key"}
        st = _storage()
        if st is None:
            return 503, {"error": "no_storage"}
        pool = load_pool(st, addr)
        if not pool:
            return 404, {"error": "no_pool"}
        stable = os.environ.get("ARC_INTEL_STABLE", "0x3600000000000000000000000000000000000000")
        try:
            max_per_order = int(float(data.get("max_per_order") or 50) * 1e6)
            max_total = int(float(data.get("max_total") or 200) * 1e6)
            min_out_floor = int(data.get("min_out_floor") or 0)
            ttl = int(data.get("ttl") or 24 * 3600)
        except (TypeError, ValueError):
            return 400, {"error": "bad_amount"}
        expiry = int(time.time()) + ttl
        pid = S.pool_id(pool)
        #  Two sessions: buy (spend the stable) and sell (spend the token) -> one setup, both ways.
        buy = S.new_session_key()
        sell = S.new_session_key()
        sell_cap = 10 ** 30  # effectively "any amount" for the sell side
        store = SubscriptionStore(DB)
        try:
            store.save_session(uid, buy["address"], S.encrypt_secret(buy["private_key"], enc),
                               executor, pid, stable, max_per_order, max_total, min_out_floor,
                               expiry, status="active")
            store.save_session(uid, sell["address"], S.encrypt_secret(sell["private_key"], enc),
                               executor, pid, addr, sell_cap, sell_cap, 0, expiry, status="active")
        finally:
            store.close()
        txs = [
            {"to": stable, "data": S.calldata_approve(PERMIT2, max_total), "desc": "1/6 Approve USDC"},
            {"to": PERMIT2, "data": S.calldata_permit2_approve(stable, executor, max_total, expiry),
             "desc": "2/6 Permit2 USDC"},
            {"to": executor, "data": S.calldata_authorize_session(buy["address"], pid, stable,
                                                                  max_per_order, max_total, min_out_floor, expiry),
             "desc": "3/6 Sesión compra"},
            {"to": addr, "data": S.calldata_approve(PERMIT2, sell_cap), "desc": "4/6 Approve token"},
            {"to": PERMIT2, "data": S.calldata_permit2_approve(addr, executor, sell_cap, expiry),
             "desc": "5/6 Permit2 token"},
            {"to": executor, "data": S.calldata_authorize_session(sell["address"], pid, addr,
                                                                  sell_cap, sell_cap, 0, expiry),
             "desc": "6/6 Sesión venta"},
        ]
        return 200, {"session_key": buy["address"], "sell_session_key": sell["address"],
                     "pool_id": pid, "token_in": stable, "expiry": expiry,
                     "max_per_order": max_per_order, "max_total": max_total,
                     "min_out_floor": min_out_floor, "txs": txs, "tx_count": len(txs)}

    def _sell(self, uid, data):
        """1-tap sell via the user's sell session (no per-order signature)."""
        import time
        from . import tokenmeta
        from .miniapp_data import load_pool, latest_price
        from execution import sessions as S
        from execution.quotes import sell_quote
        from execution.preorders import zero_for_one_for
        from execution.eip712 import new_nonce
        addr = (data.get("token") or "").lower()
        if not ADDR_RE.match(addr):
            return 400, {"error": "bad_address"}
        try:
            pct = float(data.get("pct") or 0)
            floor = float(data.get("floor_pct") or 0)
        except (TypeError, ValueError):
            return 400, {"error": "bad_amount"}
        if not (0 < pct <= 100):
            return 400, {"error": "bad_pct"}
        executor = os.environ.get("ARC_INTEL_EXECUTOR")
        if not executor:
            return 503, {"error": "no_executor"}
        st = _storage()
        if st is None:
            return 503, {"error": "no_storage"}
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
            sess = store.get_session(uid, S.pool_id(pool), addr) if recipient else None
        finally:
            store.close()
        if not recipient:
            return 409, {"error": "link_wallet"}
        if sess is None:
            return 409, {"error": "activate"}
        if self._allowed(S.pool_id(pool), pool.get("hooks")) is False:
            return 409, {"error": "pool_not_allowed", "pool_id": S.pool_id(pool), "executor": executor}
        if pos["qty"] <= 0:
            return 409, {"error": "no_position"}
        qty = pos["qty"] * pct / 100.0
        try:
            quote = sell_quote(qty=qty, price=price, token_decimals=tokenmeta.rpc_decimals(addr),
                               floor_pct=floor)
        except ValueError as e:
            return 400, {"error": str(e)}
        import time as _t
        deadline = int(_t.time()) + int(os.environ.get("ARC_INTEL_ORDER_TTL", "1800"))
        intent = {"mode": "session", "pool_id": S.pool_id(pool), "token_in": addr,
                  "key": {"currency0": pool["currency0"], "currency1": pool["currency1"],
                          "fee": pool["fee"], "tick_spacing": pool["tick_spacing"],
                          "hooks": pool["hooks"]},
                  "zero_for_one": zero_for_one_for(addr, pool["currency0"]),
                  "amount_in": quote["amount_in_base"], "min_out": quote["min_out_base"],
                  "recipient": recipient}
        store = SubscriptionStore(DB)
        try:
            pid = store.create_preorder(uid, recipient, addr, pct, floor, quote["min_out_base"],
                                        deadline, new_nonce(), status="armed", kind="session")
            store.save_sig_payload(pid, json.dumps(intent))
        finally:
            store.close()
        self._kick_session_keeper()
        return 200, {"persisted": True, "executing": True, "id": pid, "qty": qty,
                     "quote": quote, "session_key": sess["session_key"]}

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

        # Session (1-tap) path: if the user authorized a session for this pool, execute with the
        # session key — no per-order user signature.
        if persist:
            try:
                from execution import sessions as S
                from execution.quotes import stable_side
                z4o, _ = stable_side(pool, stable)
                pid_pool = S.pool_id(pool)
            except Exception:
                pid_pool = None
            if pid_pool:
                s2 = SubscriptionStore(DB)
                try:
                    sess = s2.get_session(uid, pid_pool, stable)
                finally:
                    s2.close()
                if sess:
                    if self._allowed(pid_pool, pool.get("hooks")) is False:
                        return 409, {"error": "pool_not_allowed", "pool_id": pid_pool,
                                     "executor": executor}
                    intent = {"mode": "session", "pool_id": pid_pool, "token_in": stable,
                              "key": {"currency0": pool["currency0"], "currency1": pool["currency1"],
                                      "fee": pool["fee"], "tick_spacing": pool["tick_spacing"],
                                      "hooks": pool["hooks"]},
                              "zero_for_one": z4o, "amount_in": amount_in_base,
                              "min_out": quote["min_out_base"], "recipient": recipient}
                    s3 = SubscriptionStore(DB)
                    try:
                        pid = s3.create_preorder(uid, recipient, addr, 0.0, slippage,
                                                 quote["min_out_base"], deadline, order_nonce,
                                                 status="armed", kind="session")
                        s3.save_sig_payload(pid, json.dumps(intent))
                    finally:
                        s3.close()
                    self._kick_session_keeper()
                    resp.update({"preview": False, "persisted": True, "id": pid, "executing": True,
                                 "session_key": sess["session_key"]})
                    return 200, resp

        if persist:
            # No session for this pool yet -> the user activates 1-tap trading first (no sign page).
            resp.update({"need_session": True, "hint": "activate_session", "token": addr})
            return 200, resp
        permit_nonce = new_nonce()
        resp["payload"] = build_buy_payload(
            chain_id=chain_id, executor=executor, pool=pool, stable=stable,
            amount_in_base=amount_in_base, min_out_base=quote["min_out_base"],
            recipient=recipient, order_nonce=order_nonce, permit_nonce=permit_nonce,
            deadline=deadline)
        return 200, resp

    def _allowed(self, pid, hook=None):
        """True/False/None: allowAllPools OR allowedPools[pid] OR allowedHooks[hook]."""
        from indexer.token_risk import selector, _jsonrpc
        executor = os.environ.get("ARC_INTEL_EXECUTOR")
        rpc = os.environ.get("ARC_RPC", "https://rpc.testnet.arc.io")

        def eth(sig, arg=""):
            res = _jsonrpc(rpc, "eth_call", [{"to": executor, "data": selector(sig) + arg}, "latest"])
            try:
                return bool(res and int(res, 16))
            except (TypeError, ValueError):
                return None
        allp = eth("allowAllPools()")
        if allp:
            return True
        if eth("allowedPools(bytes32)", (pid or "0x")[2:]):
            return True
        if hook and eth("allowedHooks(address)", (hook or "").lower().replace("0x", "").rjust(64, "0")):
            return True
        return None if allp is None else False

    def _custody_of(self, uid):
        store = SubscriptionStore(DB)
        try:
            return store.get_custody(uid)
        finally:
            store.close()

    def _custody_create(self, uid, data):
        from execution import custody as C
        from execution.sessions import encrypt_secret
        enc = os.environ.get("ARC_INTEL_SESSION_ENC_KEY")
        if not enc:
            return 503, {"error": "no_enc_key"}
        pk = (data.get("private_key") or "").strip()
        try:
            if pk:
                addr = C.address_of(pk)
            else:
                w = C.new_wallet()
                pk, addr = w["private_key"], w["address"]
        except Exception:
            return 400, {"error": "bad_key"}
        store = SubscriptionStore(DB)
        try:
            store.save_custody(uid, addr, encrypt_secret(pk, enc))
        finally:
            store.close()
        return 200, {"address": addr}

    def _custody_view(self, uid):
        from execution import custody as C
        c = self._custody_of(uid)
        if not c:
            return 200, {"exists": False}
        addr = c["address"]
        stable = os.environ.get("ARC_INTEL_STABLE", "0x3600000000000000000000000000000000000000")
        return 200, {"exists": True, "address": addr,
                     "usdc": C.erc20_balance(stable, addr) / 1e6,
                     "native": C.native_balance(addr) / 1e18}

    def _custody_withdraw(self, uid, data):
        from execution import custody as C
        from execution.sessions import decrypt_secret
        enc = os.environ.get("ARC_INTEL_SESSION_ENC_KEY")
        c = self._custody_of(uid)
        if not c:
            return 409, {"error": "no_custody"}
        to = (data.get("to") or "").lower()
        if not ADDR_RE.match(to):
            return 400, {"error": "bad_address"}
        token = (data.get("token") or os.environ.get("ARC_INTEL_STABLE",
                   "0x3600000000000000000000000000000000000000")).lower()
        if not ADDR_RE.match(token):
            return 400, {"error": "bad_token"}
        try:
            amount = int(str(data.get("amount_raw") or "0"))
        except (TypeError, ValueError):
            return 400, {"error": "bad_amount"}
        try:
            pk = decrypt_secret(c["enc_secret"], enc)
            txh = C.withdraw(pk, token, to, amount)
        except Exception as e:
            return 502, {"error": "withdraw_failed", "detail": str(e)[:120]}
        return 200, {"ok": True, "tx": txh}

    def _custody_buy(self, uid, data):
        import time
        from execution import custody as C
        from execution import sessions as S
        from execution.quotes import buy_quote
        from execution.eip712 import new_nonce
        from execution.sessions import decrypt_secret
        from . import tokenmeta
        from .miniapp_data import load_pool, load_token_card
        enc = os.environ.get("ARC_INTEL_SESSION_ENC_KEY")
        tok = (data.get("token") or "").lower()
        if not ADDR_RE.match(tok):
            return 400, {"error": "bad_address"}
        c = self._custody_of(uid)
        if not c:
            return 409, {"error": "no_custody"}
        st = _storage()
        if st is None:
            return 503, {"error": "no_storage"}
        pool = load_pool(st, tok)
        if not pool:
            return 404, {"error": "no_pool"}
        if self._allowed(S.pool_id(pool), pool.get("hooks")) is False:
            return 409, {"error": "pool_not_allowed", "pool_id": S.pool_id(pool)}
        stable = os.environ.get("ARC_INTEL_STABLE", "0x3600000000000000000000000000000000000000")
        card = load_token_card(st, tok)
        amount_in = int(round(float(data.get("amount_usdc") or 0) * 1e6))
        try:
            quote = buy_quote(amount_in_base=amount_in, token_price=card["price"],
                              token_decimals=tokenmeta.rpc_decimals(tok),
                              slippage_pct=float(data.get("slippage") or 3))
        except ValueError as e:
            return 400, {"error": str(e)}
        try:
            pk = decrypt_secret(c["enc_secret"], enc)
            C.ensure_permit2_approval(pk, stable)
            txh = C.swap(pk, pool=pool, token_in=stable, amount_in=amount_in,
                         min_out=quote["min_out_base"], recipient=c["address"],
                         order_nonce=new_nonce(), deadline=int(time.time()) + 600)
        except Exception as e:
            return 502, {"error": "swap_failed", "detail": str(e)[:160]}
        store2 = SubscriptionStore(DB)
        try:
            store2.add_holding(uid, tok)
            try:
                store2.record_fill(f"{(txh or '')}:buy", uid, tok, "buy",
                                   float(quote.get("expected_out") or 0),
                                   float(data.get("amount_usdc") or 0))
            except Exception:
                pass
        finally:
            store2.close()
        return 200, {"executing": True, "tx": txh, "quote": quote}

    def _portfolio(self, uid):
        """Custody holdings with qty (on-chain), price and the SL/TP plan."""
        from execution import custody as C
        from . import tokenmeta
        from .miniapp_data import latest_price
        c = self._custody_of(uid)
        if not c:
            return 200, {"positions": []}
        store = SubscriptionStore(DB)
        try:
            holds = store.list_holdings(uid)
            plans = store.list_exit_plans(uid)
            pos_map = {t: store.get_position(uid, t) for t in holds}
        finally:
            store.close()
        st = _storage()
        out = []
        for t in holds:
            raw = C.erc20_balance(t, c["address"])
            if raw <= 0:
                continue
            dec = tokenmeta.rpc_decimals(t)
            qty = raw / (10 ** dec)
            plan = plans.get(t) or {"sl_pct": 0, "tp_pct": 0, "trailing_pct": 0}
            try:
                dex = tokenmeta.dex_info(t)
            except Exception:
                dex = {}
            price = float(dex.get("price_usd") or 0) or (latest_price(st, t) if st is not None else 0.0)
            avg = float(pos_map.get(t, {}).get("avg_cost") or 0.0)
            unrealized = (price - avg) * qty if avg > 0 else 0.0
            pct = (price / avg - 1.0) if (avg > 0 and price > 0) else 0.0
            out.append({"token": t, "qty": qty, "price": price, "value": qty * price,
                        "avg_cost": avg, "unrealized": unrealized, "unrealized_pct": pct,
                        "symbol": dex.get("symbol", ""), "dex": dex,
                        "sl_pct": plan["sl_pct"], "tp_pct": plan["tp_pct"],
                        "trailing_pct": plan.get("trailing_pct", 0)})
        return 200, {"positions": out, "address": c["address"]}

    def _custody_sell(self, uid, data):
        import time
        from execution import custody as C
        from execution import sessions as S
        from execution.quotes import sell_quote
        from execution.eip712 import new_nonce
        from execution.sessions import decrypt_secret
        from . import tokenmeta
        from .miniapp_data import load_pool, latest_price
        enc = os.environ.get("ARC_INTEL_SESSION_ENC_KEY")
        tok = (data.get("token") or "").lower()
        if not ADDR_RE.match(tok):
            return 400, {"error": "bad_address"}
        c = self._custody_of(uid)
        if not c:
            return 409, {"error": "no_custody"}
        try:
            pct = float(data.get("pct") or 0)
        except (TypeError, ValueError):
            return 400, {"error": "bad_amount"}
        if not (0 < pct <= 100):
            return 400, {"error": "bad_pct"}
        st = _storage()
        if st is None:
            return 503, {"error": "no_storage"}
        pool = load_pool(st, tok)
        if not pool:
            return 404, {"error": "no_pool"}
        if self._allowed(S.pool_id(pool), pool.get("hooks")) is False:
            return 409, {"error": "pool_not_allowed", "pool_id": S.pool_id(pool)}
        bal = C.erc20_balance(tok, c["address"])
        if bal <= 0:
            return 409, {"error": "no_position"}
        amount_in = int(bal * pct / 100.0)
        price = latest_price(st, tok)
        if price <= 0:
            return 409, {"error": "no_price"}
        dec = tokenmeta.rpc_decimals(tok)
        try:
            quote = sell_quote(qty=amount_in / (10 ** dec), price=price, token_decimals=dec,
                               floor_pct=float(data.get("floor_pct") or 0))
        except ValueError as e:
            return 400, {"error": str(e)}
        try:
            pk = decrypt_secret(c["enc_secret"], enc)
            C.ensure_permit2_approval(pk, tok)
            txh = C.swap(pk, pool=pool, token_in=tok, amount_in=amount_in,
                         min_out=quote["min_out_base"], recipient=c["address"],
                         order_nonce=new_nonce(), deadline=int(time.time()) + 600)
        except Exception as e:
            return 502, {"error": "swap_failed", "detail": str(e)[:160]}
        store2 = SubscriptionStore(DB)
        try:
            qty_tok = amount_in / (10 ** dec)
            store2.record_fill(f"{(txh or '')}:sell", uid, tok, "sell", qty_tok, qty_tok * price)
        except Exception:
            pass
        finally:
            store2.close()
        return 200, {"executing": True, "tx": txh, "quote": quote}

    def _kick_session_keeper(self):
        """Fire-and-forget: execute armed session buys with the user's session key."""
        def _run():
            try:
                from execution.session_keeper import run_session_keeper
                s = SubscriptionStore(DB)
                try:
                    run_session_keeper(s)
                finally:
                    s.close()
            except Exception:
                pass
        threading.Thread(target=_run, daemon=True).start()

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
                # Only alerts for tokens the user holds in the bot wallet (cartera).
                toks = store.list_holdings(uid)
                al = store.recent_alerts(tokens=toks, limit=50) if toks else []
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
        if u.path == "/custody":
            uid = self._auth_user()
            if uid is None:
                return self._send(401, {"error": "unauthorized"})
            code, resp = self._custody_view(uid)
            return self._send(code, resp)
        if u.path == "/portfolio":
            uid = self._auth_user()
            if uid is None:
                return self._send(401, {"error": "unauthorized"})
            code, resp = self._portfolio(uid)
            return self._send(code, resp)
        if u.path == "/sessions":
            uid = self._auth_user()
            if uid is None:
                return self._send(401, {"error": "unauthorized"})
            store = SubscriptionStore(DB)
            try:
                out = [{"session_key": s["session_key"], "pool_id": s["pool_id"],
                        "token_in": s["token_in"], "expiry": s["expiry"], "status": s["status"]}
                       for s in store.list_sessions(uid)]
            finally:
                store.close()
            return self._send(200, {"sessions": out})
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
        if u.path == "/sell_order":
            uid = self._auth_user()
            if uid is None:
                return self._send(401, {"error": "unauthorized"})
            n = int(self.headers.get("Content-Length") or 0)
            try:
                data = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._send(400, {"error": "bad_json"})
            code, resp = self._sell(uid, data)
            return self._send(code, resp)
        if u.path == "/exit_plan":
            uid = self._auth_user()
            if uid is None:
                return self._send(401, {"error": "unauthorized"})
            n = int(self.headers.get("Content-Length") or 0)
            try:
                data = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._send(400, {"error": "bad_json"})
            tok = (data.get("token") or "").lower()
            if not ADDR_RE.match(tok):
                return self._send(400, {"error": "bad_address"})
            try:
                sl = float(data.get("sl_pct") or 0)
                tp = float(data.get("tp_pct") or 0)
                tr = float(data.get("trailing_pct") or 0)
            except (TypeError, ValueError):
                return self._send(400, {"error": "bad_amount"})
            if not (0 <= sl <= 99) or not (0 <= tp <= 10000) or not (0 <= tr <= 99):
                return self._send(400, {"error": "bad_pct"})
            store = SubscriptionStore(DB)
            try:
                store.set_exit_plan(uid, tok, sl, tp, tr)
            finally:
                store.close()
            return self._send(200, {"ok": True, "sl_pct": sl, "tp_pct": tp, "trailing_pct": tr})
        if u.path in ("/custody/create", "/custody/withdraw", "/custody/buy", "/custody/sell"):
            uid = self._auth_user()
            if uid is None:
                return self._send(401, {"error": "unauthorized"})
            n = int(self.headers.get("Content-Length") or 0)
            try:
                data = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._send(400, {"error": "bad_json"})
            if u.path == "/custody/create":
                code, resp = self._custody_create(uid, data)
            elif u.path == "/custody/withdraw":
                code, resp = self._custody_withdraw(uid, data)
            elif u.path == "/custody/buy":
                code, resp = self._custody_buy(uid, data)
            else:
                code, resp = self._custody_sell(uid, data)
            return self._send(code, resp)
        if u.path == "/session/authorize":
            uid = self._auth_user()
            if uid is None:
                return self._send(401, {"error": "unauthorized"})
            n = int(self.headers.get("Content-Length") or 0)
            try:
                data = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._send(400, {"error": "bad_json"})
            code, resp = self._session_authorize(uid, data)
            return self._send(code, resp)
        if u.path == "/session/revoke":
            uid = self._auth_user()
            if uid is None:
                return self._send(401, {"error": "unauthorized"})
            n = int(self.headers.get("Content-Length") or 0)
            try:
                data = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._send(400, {"error": "bad_json"})
            sk = data.get("session_key") or ""
            store = SubscriptionStore(DB)
            try:
                ok = store.revoke_session(uid, sk) if sk else False
            finally:
                store.close()
            from execution.sessions import calldata_revoke_session
            executor = os.environ.get("ARC_INTEL_EXECUTOR", "")
            return self._send(200 if ok else 404,
                              {"ok": ok, "tx": {"to": executor, "data": calldata_revoke_session(sk)}})
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
