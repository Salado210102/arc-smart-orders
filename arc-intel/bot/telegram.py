"""Phase 6 — Telegram alert delivery (notification only; NO execution).

Consumes Telegram-ready Alert objects from the risk engine and dispatches them to
subscribed chats, filtered by token/wallet and alert kind. Two transports:
  - ConsoleTransport: dry-run (prints), for testing without a bot token.
  - TelegramTransport: real delivery via python-telegram-bot (needs BOT token).

Run:
    python -m bot.telegram --demo
    python -m bot.telegram --from-db --dsn <dsn>
"""
from __future__ import annotations

import argparse
import json
import os
import threading
import time

from . import tokenmeta
from .sender import SenderPool
from .messages import format_alert, format_alert_rich
from .store import SubscriptionStore
from .throttle import Throttle

PUSH_EXCLUDED_KINDS = {"thin_market", "volume_collapse"}  # not pushed (collapse feeds 'compound')

_IMG_CACHE: dict[str, str] = {}


def _argus_image_for(storage, token: str) -> str:
    """Argus on-chain token image (ipfs://... -> gateway URL), cached. '' if none."""
    t = (token or "").lower()
    if t in _IMG_CACHE:
        return _IMG_CACHE[t]
    url = ""
    try:
        conn = storage.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT data FROM launchpad_events WHERE event_name='TokenCreated' "
                            "AND token=%s LIMIT 1", (t,))
                r = cur.fetchone()
        finally:
            storage.pool.putconn(conn)
        if r and r[0]:
            url = tokenmeta.argus_image(r[0])
    except Exception:
        url = ""
    _IMG_CACHE[t] = url
    return url


def load_token() -> str | None:
    """Read the bot token from env or a local .env (never hardcode it).

    Tolerant: accepts 'TELEGRAM_BOT_TOKEN=...' or a bare token line (digits:alnum).
    """
    tok = os.environ.get("TELEGRAM_BOT_TOKEN")
    if tok:
        return tok.strip()
    for path in (".env", "/root/arc-intel/.env"):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    s = line.strip()
                    if not s:
                        continue
                    if s.startswith("TELEGRAM_BOT_TOKEN="):
                        return s.split("=", 1)[1].strip()
                    if ":" in s and " " not in s and len(s) >= 20:
                        return s
        except OSError:
            continue
    return None


def set_bot_commands(token: str, timeout: int = 10) -> bool:
    """Register the bot's command list (the square 'menu' button in Telegram). Best-effort."""
    import urllib.request

    def post(method, payload):
        url = f"https://api.telegram.org/bot{token}/{method}"
        req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        return urllib.request.urlopen(req, timeout=timeout).read()

    en = [
        {"command": "start", "description": "Start / menu"},
        {"command": "list", "description": "My alerts"},
        {"command": "check", "description": "Check a token"},
        {"command": "stats", "description": "Signal stats"},
        {"command": "pending", "description": "Pending proposals"},
        {"command": "positions", "description": "Paper positions"},
        {"command": "wallet", "description": "Connect wallet"},
        {"command": "link_wallet", "description": "Link wallet (auto-track)"},
        {"command": "unlink_wallet", "description": "Unlink wallet"},
        {"command": "settings", "description": "Alert settings"},
        {"command": "language", "description": "Language"},
        {"command": "disclaimer", "description": "Disclaimer"},
        {"command": "help", "description": "Help"},
    ]
    es = [
        {"command": "start", "description": "Iniciar / menú"},
        {"command": "list", "description": "Mis alertas"},
        {"command": "check", "description": "Consultar token"},
        {"command": "stats", "description": "Estadísticas"},
        {"command": "pending", "description": "Pendientes"},
        {"command": "positions", "description": "Posiciones"},
        {"command": "wallet", "description": "Conectar cartera"},
        {"command": "link_wallet", "description": "Vincular cartera (auto)"},
        {"command": "unlink_wallet", "description": "Desvincular cartera"},
        {"command": "settings", "description": "Ajustes"},
        {"command": "language", "description": "Idioma"},
        {"command": "disclaimer", "description": "Aviso legal"},
        {"command": "help", "description": "Ayuda"},
    ]
    zh = [
        {"command": "start", "description": "\u5f00\u59cb / \u83dc\u5355"},
        {"command": "list", "description": "\u6211\u7684\u63d0\u9192"},
        {"command": "check", "description": "\u67e5\u8be2\u4ee3\u5e01"},
        {"command": "stats", "description": "\u7edf\u8ba1"},
        {"command": "pending", "description": "\u5f85\u5904\u7406"},
        {"command": "positions", "description": "\u6301\u4ed3"},
        {"command": "wallet", "description": "\u8fde\u63a5\u94b1\u5305"},
        {"command": "link_wallet", "description": "\u5173\u8054\u94b1\u5305\uff08\u81ea\u52a8\uff09"},
        {"command": "unlink_wallet", "description": "\u53d6\u6d88\u5173\u8054\u94b1\u5305"},
        {"command": "settings", "description": "\u8bbe\u7f6e"},
        {"command": "language", "description": "\u8bed\u8a00"},
        {"command": "disclaimer", "description": "\u514d\u8d23\u58f0\u660e"},
        {"command": "help", "description": "\u5e2e\u52a9"},
    ]
    try:
        post("setMyCommands", {"commands": en})
        post("setMyCommands", {"commands": es, "language_code": "es"})
        post("setMyCommands", {"commands": zh, "language_code": "zh"})
        post("setChatMenuButton", {"menu_button": {"type": "commands"}})
        return True
    except Exception:
        return False


def _inline_keyboard(inline) -> list:
    """Build a Telegram inline_keyboard from rows of {text,data|url|web_app} buttons."""
    rows = inline if inline and isinstance(inline[0], list) else [inline]
    kb = []
    for row in rows:
        r = []
        for b in row:
            if b.get("url"):
                r.append({"text": b["text"], "url": b["url"]})
            elif b.get("web_app"):
                r.append({"text": b["text"], "web_app": {"url": b["web_app"]}})
            else:
                r.append({"text": b["text"], "callback_data": b.get("data")})
        kb.append(r)
    return kb


class ConsoleTransport:
    send_html = False

    def send(self, chat_id, text: str, parse_mode=None, keyboard=None, inline=None,
             remove_keyboard=False, timeout: int = 30) -> None:
        print(f"----- Telegram -> chat {chat_id} -----")
        print(text)
        if keyboard:
            print(f"[keyboard] {keyboard}")
        if inline:
            print(f"[inline] {inline}")
        print("--------------------------------------")

    def send_photo(self, chat_id, photo_url, caption="", parse_mode=None, inline=None) -> None:
        print(f"----- Telegram PHOTO -> chat {chat_id} -----")
        print(photo_url)
        print(caption)
        print("-------------------------------------------")

    def edit_message(self, chat_id, message_id, text, parse_mode=None, inline=None,
                     timeout: int = 30) -> None:
        print(f"----- Telegram EDIT -> chat {chat_id} msg {message_id} -----")
        print(text)
        print("-------------------------------------------")


class TelegramTransport:
    send_html = True

    def __init__(self, token: str):
        try:
            import telegram  # noqa: F401
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("python-telegram-bot not installed") from exc
        self.token = token

    def send(self, chat_id, text: str, parse_mode=None, keyboard=None,
             inline=None, remove_keyboard=False, timeout: int = 30) -> None:  # noqa (needs network)
        # Direct HTTP call: no per-message client/event-loop setup -> much lower latency.
        import urllib.request
        payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if remove_keyboard:
            payload["reply_markup"] = {"remove_keyboard": True}
        elif keyboard:
            payload["reply_markup"] = {
                "keyboard": keyboard, "resize_keyboard": True, "is_persistent": True}
        elif inline:
            payload["reply_markup"] = {"inline_keyboard": _inline_keyboard(inline)}
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=timeout).read()

    def send_photo(self, chat_id, photo_url, caption="", parse_mode=None,
                   inline=None) -> None:  # pragma: no cover (needs network)
        import urllib.request
        payload = {"chat_id": chat_id, "photo": photo_url, "caption": caption}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if inline:
            payload["reply_markup"] = {"inline_keyboard": _inline_keyboard(inline)}
        url = f"https://api.telegram.org/bot{self.token}/sendPhoto"
        req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=30).read()

    def edit_message(self, chat_id, message_id, text, parse_mode=None,
                     inline=None, timeout: int = 30) -> None:  # noqa (needs network)
        import urllib.request
        payload = {"chat_id": chat_id, "message_id": message_id, "text": text,
                   "disable_web_page_preview": True}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if inline:
            payload["reply_markup"] = {"inline_keyboard": _inline_keyboard(inline)}
        url = f"https://api.telegram.org/bot{self.token}/editMessageText"
        req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=timeout).read()


def matches(sub: dict, alert: dict) -> bool:
    tokens = sub.get("tokens", set())
    kinds = sub.get("kinds", set())
    token_ok = ("*" in tokens) or (alert.get("token") in tokens)
    kind_ok = (not kinds) or (alert.get("kind") in kinds)
    return token_ok and kind_ok


def dispatch(alerts: list, store: SubscriptionStore, transport, throttle=None,
             per_chat_cap: int = 20, logo_fn=None) -> int:
    """Send matching alerts to subscribers. Dedup is PERSISTENT (store), not in-memory.

    - Per-CHAT cap (`per_chat_cap`): each user has its own message budget per call.
    - Global Telegram rate handled by `throttle`.
    - thin_market is never pushed; only alerts with block > subscriber's since_block
      (i.e. subscribed AFTER those alerts) are delivered.
    """
    total = 0
    logo_budget = 8  # cap external logo lookups per cycle so alert delivery never stalls
    for s in store.list():
        chat = s["chat_id"]
        since = int(s.get("since_block", 0) or 0)
        sent = 0
        for a in alerts:
            if sent >= per_chat_cap:
                break
            if a.get("kind") in PUSH_EXCLUDED_KINDS:
                continue
            if int(a.get("block") or 0) <= since:
                continue
            if not matches(s, a):
                continue
            if store.is_delivered(chat, a.get("token"), a.get("kind"), a.get("block")):
                continue
            if throttle is not None:
                throttle.wait(chat)
            text = format_alert_rich(a)
            logo = ""
            if logo_fn and logo_budget > 0:
                logo_budget -= 1
                try:
                    logo = logo_fn(a.get("token")) or ""
                except Exception:
                    logo = ""
            tk = a.get("token")
            inline = None
            if tk:
                from .i18n import MINIAPP_URL
                inline = [[{"text": "\U0001F7E2 Comprar", "web_app": f"{MINIAPP_URL}?token={tk}"}]]
            if logo and hasattr(transport, "send_photo"):
                try:
                    transport.send_photo(chat, logo, caption=text, parse_mode="HTML", inline=inline)
                except Exception:
                    # a bad image URL must never drop the alert
                    if getattr(transport, "send_html", False):
                        transport.send(chat, text, parse_mode="HTML", inline=inline)
                    else:
                        transport.send(chat, format_alert(a))
            elif getattr(transport, "send_html", False):
                transport.send(chat, text, parse_mode="HTML", inline=inline)
            else:
                transport.send(chat, format_alert(a))
            store.mark_delivered(chat, a.get("token"), a.get("kind"), a.get("block"))
            sent += 1
            total += 1
    return total


class AlertLoop:
    """Minimal long-running service: each cycle fetches new alerts and dispatches them.

    Logs {'cycle', 'alerts', 'dispatched'} per cycle. Throttled for Telegram limits.
    Dedup is persistent (store), so restarts never resend.
    """

    def __init__(self, store, transport, fetch_alerts, throttle=None, logger=print):
        self.store = store
        self.transport = transport
        self.fetch_alerts = fetch_alerts
        self.throttle = throttle
        self.logger = logger
        self.cycle = 0

    def run_once(self) -> int:
        self.cycle += 1
        alerts = self.fetch_alerts()
        n = dispatch(alerts, self.store, self.transport, throttle=self.throttle)
        self.logger({"cycle": self.cycle, "alerts": len(alerts), "dispatched": n})
        return n

    def run(self, cycles: int = 0, interval: float = 5.0, sleep_fn=time.sleep) -> None:
        k = 0
        while cycles <= 0 or k < cycles:
            self.run_once()
            k += 1
            if cycles <= 0 or k < cycles:
                sleep_fn(interval)


def check_token(storage, token: str) -> str:
    """On-demand /check <token>: rich token card (HTML)."""
    import html as _h
    from indexer.alerts import is_thin_market

    BLOCKS_24H = 166153  # ~24h at 0.52 s/block
    token = (token or "").lower()
    conn = storage.pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT symbol,name,creator,launchpad,pool_id FROM tokens "
                        "WHERE address=%s LIMIT 1", (token,))
            row = cur.fetchone()
            symbol = name = creator = launchpad = pool_id = None
            if row:
                symbol, name, creator, launchpad, pool_id = row
            cur.execute("SELECT block_number, topics FROM launchpad_events "
                        "WHERE event_name='TokenCreated' AND token=%s LIMIT 1", (token,))
            ev = cur.fetchone()
            created_block = int(ev[0]) if ev else None
            if ev and not creator and ev[1]:
                parts = ev[1].split(",")
                if len(parts) >= 3:
                    creator = "0x" + parts[2][-40:]
            cur.execute("SELECT count(*), count(DISTINCT wallet), min(block), max(block) "
                        "FROM legs WHERE token=%s", (token,))
            n, w, first_blk, last_blk = cur.fetchone()
            cur.execute("SELECT max(block) FROM legs")
            head = int(cur.fetchone()[0] or 0)
            cur.execute("SELECT coalesce(sum(stable_value),0) FROM legs "
                        "WHERE token=%s AND block >= %s", (token, head - BLOCKS_24H))
            vol24 = float(cur.fetchone()[0] or 0)
            cur.execute("SELECT price FROM legs WHERE token=%s ORDER BY block DESC LIMIT 1", (token,))
            pr = cur.fetchone()
            price = float(pr[0]) if pr and pr[0] is not None else 0.0
    finally:
        storage.pool.putconn(conn)

    n = int(n or 0)
    w = int(w or 0)
    if not symbol:
        symbol = tokenmeta.rpc_symbol(token) or ""
    supply = tokenmeta.rpc_total_supply(token)
    dec = tokenmeta.rpc_decimals(token)
    supply_h = supply / (10 ** dec) if supply else 0.0
    mcap = price * supply_h
    if price >= 0.01:
        price_txt = f"${price:,.4f}"
    elif price >= 1e-6:
        price_txt = f"${price:.8f}"
    elif price > 0:
        price_txt = f"${price:.2e}"
    else:
        price_txt = "n/a"

    def _usd(v):
        return f"${v:,.0f}" if v else "n/a"

    first = int(first_blk) if first_blk else None
    ob = created_block or first
    age = (head - ob) if ob else 0
    secs = age * 0.52
    if secs >= 86400:
        age_txt = f"{secs / 86400:.1f} d"
    elif secs >= 3600:
        age_txt = f"{secs / 3600:.1f} h"
    else:
        age_txt = f"{secs / 60:.0f} min"
    thin = is_thin_market(n, w, age, no_trade_blocks=100000) if ob else None
    status = f"\u26A0\uFE0F thin market ({thin})" if thin else "\U0001F7E2 has market activity"

    rep = {}
    if creator:
        try:
            from indexer.creator_rep import creator_report
            rep = creator_report(storage, creator)
        except Exception:
            rep = {}

    hd = f"<b>{_h.escape(symbol)}</b> \u00B7 " if symbol else ""
    lines = ["\U0001F50E <b>Token check</b>", "",
             f"{hd}<code>{_h.escape(token)}</code>"]
    if name:
        lines.append(f"\U0001F3F7\uFE0F {_h.escape(name)}")
    lines.append(f"\U0001F3ED Launchpad: <b>{_h.escape(launchpad or 'unknown')}</b>")
    if creator:
        cl = f"\U0001F464 Creator: <code>{_h.escape(creator)}</code>"
        if rep.get("created"):
            cl += f" \u00B7 created {rep['created']}"
            if rep["dumped"]:
                cl += f" \u00B7 <b>dumped {rep['dumped']} ({rep['rug_rate'] * 100:.0f}%)</b>"
                if rep.get("dumped_value"):
                    cl += f" (${rep['dumped_value']:,.0f})"
                cl += " \u26A0\uFE0F"
        lines.append(cl)
    lines.append(f"\U0001F552 Created: block {ob} (~{age_txt} ago)" if ob else "\U0001F552 Created: unknown")
    lines.append(f"\U0001F4CA Activity: <b>{n}</b> swaps \u00B7 <b>{w}</b> wallets")
    lines.append(f"\U0001F4B0 Price: <b>{price_txt}</b>")
    lines.append(f"\U0001F3E6 Market cap: <b>{_usd(mcap)}</b>")
    lines.append(f"\U0001F4C8 Vol 24h: <b>{_usd(vol24)}</b>")
    if last_blk:
        lines.append(f"\U0001F551 Last trade: block {int(last_blk)}")
    lines.append(f"\U0001F4CA Status: {status}")
    try:
        from indexer.token_risk import analyze_token
        from .miniapp_data import holders_for
        rk = analyze_token(token, holders=holders_for(storage, token))
        if rk.get("level") and rk["level"] != "unknown":
            emoji = {"high": "\U0001F534", "medium": "\U0001F7E0", "low": "\U0001F7E2"}.get(rk["level"], "\u26AA")
            flags = ", ".join(rk.get("reasons") or []) or "clean"
            hp = " \u26A0\uFE0F honeypot machinery" if rk.get("honeypot_hint") else ""
            lines.append(f"{emoji} Contract risk: <b>{rk['level']}</b> ({_h.escape(flags)}){hp} "
                         f"<i>heuristic</i>")
    except Exception:
        pass
    lines.append(f'\U0001F517 <a href="https://explorer.arc.io/address/{_h.escape(token)}">view on explorer</a>')
    return "\n".join(lines)


def demo() -> None:
    store = SubscriptionStore(":memory:")
    store.subscribe(chat_id=12345, tokens=("*",),
                    kinds=("dev_sell", "compound", "volume_collapse"))
    alerts = [
        {"token": "0xbf5c7958a9003f62d7a6a0bdd5de7d5f5659ff53", "kind": "dev_sell",
         "severity": "high", "block": 21181957,
         "message": "0x3e7c3efd... (creator) sold 100% of its 0xbf5c7958... position (~$1,500) at block 21181957"},
        {"token": "0xdead", "kind": "thin_market", "severity": "low", "block": 22721550,
         "message": "0xdead: thin market - no_trades ... (should NOT be pushed)"},
    ]
    n = dispatch(alerts, store, ConsoleTransport())
    print(f"(delivered {n}; thin_market is excluded from push -> use /check)")
    store.close()


def demo_loop() -> None:
    from .throttle import Throttle
    store = SubscriptionStore(":memory:")
    store.subscribe(chat_id=1, tokens=("*",), kinds=("dev_sell",))
    calls = {"n": 0}

    def fetch():
        calls["n"] += 1
        if calls["n"] == 1:
            return [{"token": f"0xt{i}", "kind": "dev_sell", "severity": "high", "block": 100,
                     "message": f"demo dev-sell {i}"} for i in range(5)]
        return []

    throttled = []  # record throttle waits with a fake clock to avoid real sleeping
    clock = {"t": 0.0}
    thr = Throttle(global_per_sec=20, per_chat_per_sec=1.0,
                   time_fn=lambda: clock["t"], sleep_fn=lambda s: clock.__setitem__("t", clock["t"] + s))
    loop = AlertLoop(store, ConsoleTransport(), fetch, throttle=thr, logger=print)
    loop.run_once()
    loop.run_once()
    print(f"(clock advanced to {clock['t']:.2f}s by throttle; thin_market never pushed)")
    store.close()


def emit_alerts(dsn: str, limit: int = 10) -> list:
    """Compute real push alerts (dev_sell top-N + compound) and return them as dicts."""
    from indexer.alerts import (load_creator_sells, dev_sell_alerts, load_volume_buckets,
                                volume_collapse_alerts, compound_alerts)
    from indexer.pg_storage import PostgresStorage
    storage = PostgresStorage(dsn)
    rows = load_creator_sells(storage)
    dev = dev_sell_alerts(rows, 0.5, 100.0)
    series = load_volume_buckets(storage, 600)
    storage.close()
    collapse = volume_collapse_alerts(series, z_threshold=-2.0)
    comp = compound_alerts(dev, collapse, 6000)
    dev_sorted = sorted(dev, key=lambda a: (a.severity == "high", a.amount_usdc or 0), reverse=True)
    alerts = [a.__dict__ for a in (dev_sorted[:limit] + comp)]
    print({"dev_sell_total": len(dev), "compound": len(comp), "to_push": len(alerts)})
    return alerts


def _file_fetch(path: str):
    def fetch():
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, list) else []
        except (OSError, ValueError):
            return []
    return fetch


def is_transient_poll_error(exc: BaseException) -> bool:
    """True only for expected long-poll/transient network conditions (idle timeout, reset)."""
    import socket
    import urllib.error
    return isinstance(exc, (TimeoutError, socket.timeout, ConnectionError, urllib.error.URLError))


def apply_collapse_cooldown(alerts: list, store, now_ts: int, window_s: int) -> list:
    """Suppress repeated volume_collapse/volume_spike alerts for the same token in `window_s`."""
    kept = []
    for a in alerts:
        if a.kind in ("volume_collapse", "volume_spike") and not store.cooldown_ok(
                a.token, a.kind, now_ts, window_s):
            continue
        kept.append(a)
    return kept


def safe_call(fn):
    """Run fn(); return (result, None) or (None, error_name). Used to keep the loop alive
    across transient failures (e.g. RPC hiccups) without advancing state."""
    try:
        return fn(), None
    except Exception as exc:
        return None, type(exc).__name__


def run_incremental(dsn: str, db: str, interval: float, cycles: int, start_block: int,
                    no_init: bool, limit_per_cycle: int = 200000, max_send: int = 30,
                    end_block: int = 0, ingest: bool = True, collapse_cooldown: int = 3600) -> None:
    """Single 24/7 process: each cycle ingests new blocks (resilient) then detects & dispatches."""
    from indexer.pg_storage import PostgresStorage
    from indexer.stream_alerts import (IncrementalState, load_creators, build_initial_state,
                                       fetch_new_legs, max_leg_block, save_state, load_state)
    from indexer.ingest import ingest_new
    tok = load_token()
    if not tok:
        print("no token")
        return
    set_bot_commands(tok)
    store = SubscriptionStore(db)
    thr = Throttle(global_per_sec=20, per_chat_per_sec=1.0)
    transport = TelegramTransport(tok)
    sender = SenderPool(transport, workers=3, timeout=8)  # command replies only
    storage = PostgresStorage(dsn)
    source = None
    if ingest:
        from indexer.config import load_config
        from indexer.sources import RpcEventSource
        cfg = load_config()
        source = RpcEventSource(cfg.rpc_url, cfg.launchpads)
    creators = load_creators(storage)
    from indexer.stream_alerts import load_symbols
    symbols = load_symbols(storage)
    state_path = "/root/arc-intel/state.pkl"
    state = IncrementalState()
    cursor = int(store.get_state("alert_cursor", str(start_block)) or start_block)
    liq_cursor = int(store.get_state("liq_cursor", str(cursor)) or cursor)
    loaded, lcur = load_state(state_path)
    if loaded is not None:
        state = loaded
        print(f"loaded persisted state (cursor {lcur})", flush=True)
    elif not no_init:
        n = build_initial_state(storage, state, creators, cursor,
                                on_progress=lambda k: print("init", k, flush=True))
        print("initial state legs:", n, flush=True)

    def logo_fn(token: str) -> str:
        # Prefer the Argus on-chain image; fall back to DexScreener.
        return _argus_image_for(storage, token) or tokenmeta.logo(token)

    def logger(d):
        line = json.dumps(d)
        print(line, flush=True)
        try:
            with open("/root/arc-intel/loop.log", "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            pass

    def _activity(start, end):
        try:
            with open("/root/arc-intel/loop_activity.log", "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"start": int(start * 1000), "end": int(end * 1000),
                                     "cycle": k}) + "\n")
        except OSError:
            pass

    k = 0
    from .commands import poll_once

    def token_exists(tok: str) -> bool:
        conn = storage.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM tokens WHERE lower(address)=%s LIMIT 1", (tok.lower(),))
                return cur.fetchone() is not None
        finally:
            storage.pool.putconn(conn)

    def check_fn(tok: str) -> str:
        return check_token(storage, tok)

    def price_fn(token: str):
        from indexer.stream_alerts import load_price_series
        return load_price_series(storage, token)

    def recent_fn(n: int, window_blocks: int | None = None):
        import indexer.stream_alerts as _sa
        if window_blocks is None:
            cached = store.get_state("recent_tokens")
            if cached:
                try:
                    toks = json.loads(cached)
                    if toks:
                        return toks[:n]
                except ValueError:
                    pass
            return _sa.recent_active_tokens(storage, n)
        return _sa.recent_active_tokens(storage, n, window_blocks)

    clock = {"block": cursor}
    stop = threading.Event()
    # Dedicated connection for the command thread -> no write-lock contention with the alert loop.
    cmd_store = SubscriptionStore(db)
    sym_lc = {(k or "").lower(): v for k, v in (symbols or {}).items()}

    def symbol_fn(tok: str) -> str:
        return sym_lc.get((tok or "").lower()) or tokenmeta.rpc_symbol(tok)

    def worker():
        while not stop.is_set():
            try:
                # Short polling: a stalled connection can't hold delivery for long; updates are
                # picked up within ~poll interval instead of waiting on a hung long-poll.
                n = poll_once(tok, cmd_store, transport, token_exists, check_fn, clock["block"],
                              recent_fn=recent_fn, paper_price_fn=price_fn, symbol_fn=symbol_fn,
                              sender=sender, timeout=2)
                if not n:
                    time.sleep(0.3)
            except Exception as exc:
                if is_transient_poll_error(exc):
                    time.sleep(0.5)
                else:
                    import traceback
                    print("command poll error:\n" + traceback.format_exc(), flush=True)
                    time.sleep(1)

    threading.Thread(target=worker, daemon=True).start()

    # Wallet tracking in its OWN thread (own DB connection): on-chain balance scans can be slow
    # and flaky, and must NEVER delay alert detection/delivery.
    wstore = SubscriptionStore(db)

    def wallet_worker():
        while not stop.is_set():
            try:
                from .wallet_track import scan_wallets
                scan = scan_wallets(storage, wstore, head=clock["block"])
                if scan["new_subs"] or scan["dropped_subs"]:
                    logger({"wallet_track": scan})
            except Exception:
                pass
            stop.wait(180)

    threading.Thread(target=wallet_worker, daemon=True).start()

    try:
        while cycles <= 0 or k < cycles:
            k += 1
            t_cycle0 = time.time()
            ingest_note = "ok"
            if ingest and source is not None:
                r, err = safe_call(lambda: ingest_new(storage, source))
                if err is None:
                    ingest_note = f"new_legs={r.get('new_legs')}"
                else:
                    ingest_note = f"error:{err}"
                    logger({"cycle": k, "ingest": ingest_note})
            head = max_leg_block(storage)
            if end_block:
                head = min(head, int(end_block))
            legs = fetch_new_legs(storage, cursor, head, limit_per_cycle)
            if legs:
                # Refresh creator/symbol maps for the new tokens (avoid stale maps -> missed dev-sells).
                toks = {lg["token"] for lg in legs if lg.get("token")}
                try:
                    from indexer.stream_alerts import load_creators_for, load_symbols_for
                    creators.update(load_creators_for(storage, toks))
                    symbols.update(load_symbols_for(storage, toks))
                except Exception:
                    pass
            alerts = state.apply_legs(legs, creators)
            # Liquidity removals (rug signal) since the last scan — monitored live now.
            try:
                from indexer.alerts import load_liquidity_removals, liquidity_removal_alerts
                liq = liquidity_removal_alerts(load_liquidity_removals(storage, since_block=liq_cursor))
                if liq:
                    alerts.extend(liq)
                    liq_cursor = max(liq_cursor, max(a.block for a in liq))
                    store.set_state("liq_cursor", str(liq_cursor))
            except Exception:
                pass
            alerts = apply_collapse_cooldown(alerts, store, int(time.time()), collapse_cooldown)
            now_ts = int(time.time())
            for a in alerts:
                a.context["symbol"] = symbols.get(a.token, "")
                if a.kind in ("dev_sell", "compound", "volume_collapse"):
                    store.add_paper_alert(a.kind, a.token, a.block, now_ts)
                try:
                    store.add_alert(a.__dict__, now_ts)   # persist for the Mini App Alerts tab
                except Exception:
                    pass
            store.enqueue_alert_many([a.__dict__ for a in alerts])
            try:
                from .commands import fire_preorders
                fired = fire_preorders(store, alerts, transport, thr, price_fn)
                if fired:
                    logger({"cycle": k, "preorders_fired": fired})
            except Exception:
                pass
            try:
                from execution.keeper import run_keeper

                def _on_exec(po, txh):
                    try:
                        thr.wait(po["chat"])
                        transport.send(po["chat"],
                                       f"\u2705 BUY #{po['id']} executed on-chain "
                                       f"({po['token']}): {txh}")
                    except Exception:
                        pass

                run_keeper(store, logger=logger, on_executed=_on_exec)
            except Exception:
                pass
            try:
                from execution.session_keeper import run_session_keeper
                run_session_keeper(store, logger=logger)
            except Exception:
                pass
            batch = store.dequeue(2000)
            n = dispatch(batch, store, transport, throttle=thr, logo_fn=logo_fn)
            from .approvals import propose as ap_propose
            now_ts = int(time.time())
            for a in alerts:
                if a.kind != "dev_sell":
                    continue
                for s in store.list():
                    if not matches(s, a.__dict__):
                        continue
                    if store.approval_exists(s["chat_id"], a.token, a.kind, a.block):
                        continue
                    aid = ap_propose(store, s["chat_id"], a.token, a.kind, "sell", 10.0,
                                     a.block, now_ts)
                    if aid:
                        thr.wait(s["chat_id"])
                        transport.send(s["chat_id"],
                                       f"[PAPER] Proposal #{aid}: simulated SELL {a.token} "
                                       f"(dev-sell at block {a.block}). /approve {aid} or "
                                       f"/cancel {aid} (cancel window 5 min).")
            if legs:
                cursor = max(leg["block"] for leg in legs) if len(legs) >= limit_per_cycle else head
            clock["block"] = cursor
            store.set_state("alert_cursor", str(cursor))
            store.purge_queue(cursor - 200000)
            save_state(state_path, state, cursor)
            try:
                from indexer.stream_alerts import recent_active_tokens
                store.set_state("recent_tokens", json.dumps(recent_active_tokens(storage, 30)))
            except Exception:
                pass
            try:
                from indexer.paper_eval import persist_pending
                persist_pending(storage, store, 45)
            except Exception:
                pass
            sig = {}
            for a in alerts:
                sig[a.kind] = sig.get(a.kind, 0) + 1
            logger({"cycle": k, "new_legs": len(legs), "alerts": len(alerts), "signals": sig,
                    "lag": head - cursor, "watch": len(store.list()), "queue": store.queue_size(),
                    "dispatched": n, "cursor": cursor, "ingest": ingest_note})
            _activity(t_cycle0, time.time())
            if cycles <= 0 or k < cycles:
                time.sleep(interval)
    finally:
        stop.set()
        sender.close()
        store.close()
        cmd_store.close()
        wstore.close()
        storage.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--demo-loop", action="store_true")
    ap.add_argument("--check", type=str, help="on-demand /check <token>")
    ap.add_argument("--dsn", type=str)
    ap.add_argument("--send-test", type=str, help="chat_id to send a real test message")
    ap.add_argument("--whoami", action="store_true", help="list chat ids that messaged the bot")
    ap.add_argument("--emit", type=str, help="compute real alerts and write to JSON file")
    ap.add_argument("--run-loop", nargs="?", const="", default=None,
                    help="run the loop (optional JSON file for sandbox mode)")
    ap.add_argument("--interval", type=float, default=300.0)
    ap.add_argument("--cycles", type=int, default=6)
    ap.add_argument("--db", type=str, default="/root/arc-intel/bot_subs.db")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--incremental", action="store_true",
                    help="loop processes only new legs (block > cursor) with persistent state")
    ap.add_argument("--start-block", type=int, default=0)
    ap.add_argument("--no-init", action="store_true",
                    help="skip rebuilding state from history (start clean at cursor)")
    ap.add_argument("--end-block", type=int, default=0, help="bound the processing head (tests)")
    ap.add_argument("--no-ingest", action="store_true", help="disable live ingestion inside the loop")
    ap.add_argument("--max-send", type=int, default=30,
                    help="max alerts drained from the queue per cycle (excess stays queued)")
    ap.add_argument("--collapse-cooldown", type=int, default=3600,
                    help="seconds to suppress repeated volume_collapse per token")
    args = ap.parse_args()

    if args.incremental:
        if not args.dsn:
            print("need --dsn")
            return
        run_incremental(args.dsn, args.db, args.interval, args.cycles,
                        args.start_block, args.no_init, max_send=args.max_send,
                        end_block=args.end_block, ingest=not args.no_ingest,
                        collapse_cooldown=args.collapse_cooldown)
        return

    if args.emit:
        if not args.dsn:
            print("need --dsn")
            return
        alerts = emit_alerts(args.dsn, args.limit)
        with open(args.emit, "w", encoding="utf-8") as fh:
            json.dump(alerts, fh)
        print(f"wrote {args.emit}: {len(alerts)} alerts")
        return
    if args.run_loop:
        tok = load_token()
        if not tok:
            print("no token")
            return
        store = SubscriptionStore(args.db)
        thr = Throttle(global_per_sec=20, per_chat_per_sec=1.0)
        transport = TelegramTransport(tok)

        def logger(d):
            line = json.dumps(d)
            print(line)
            try:
                with open("/root/arc-intel/loop.log", "a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
            except OSError:
                pass

        loop = AlertLoop(store, transport, _file_fetch(args.run_loop), throttle=thr, logger=logger)
        loop.run(cycles=args.cycles, interval=args.interval)
        store.close()
        return
    if args.check and args.dsn:
        from indexer.pg_storage import PostgresStorage
        storage = PostgresStorage(args.dsn)
        print(check_token(storage, args.check))
        storage.close()
        return
    if args.send_test or args.whoami:
        tok = load_token()
        if not tok:
            print("no TELEGRAM_BOT_TOKEN found (set env var or /root/arc-intel/.env)")
            return
        if args.whoami:
            import asyncio
            from telegram import Bot
            ups = asyncio.run(Bot(tok).get_updates())
            seen = sorted({(u.effective_chat.id, u.effective_chat.type)
                           for u in ups if u.effective_chat})
            print("chats:", seen or "(none yet - send /start to your bot)")
            return
        TelegramTransport(tok).send(args.send_test, "ARC AI test: bot connected.")
        print(f"sent test message to {args.send_test}")
        return
    if args.demo_loop:
        demo_loop()
    else:
        demo()


if __name__ == "__main__":
    main()
