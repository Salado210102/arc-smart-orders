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
from .messages import format_alert, format_alert_rich
from .store import SubscriptionStore
from .throttle import Throttle

PUSH_EXCLUDED_KINDS = {"thin_market"}  # thin_market is on-demand via /check, not pushed

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


class ConsoleTransport:
    send_html = False

    def send(self, chat_id, text: str, parse_mode=None, keyboard=None, inline=None) -> None:
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


class TelegramTransport:
    send_html = True

    def __init__(self, token: str):
        try:
            import telegram  # noqa: F401
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("python-telegram-bot not installed") from exc
        self.token = token

    def send(self, chat_id, text: str, parse_mode=None, keyboard=None,
             inline=None) -> None:  # pragma: no cover (needs network)
        # Direct HTTP call: no per-message client/event-loop setup -> much lower latency.
        import urllib.request
        payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if keyboard:
            payload["reply_markup"] = {
                "keyboard": keyboard, "resize_keyboard": True, "is_persistent": True}
        elif inline:
            rows = inline if isinstance(inline[0], list) else [inline]
            kb = []
            for row in rows:
                r = []
                for b in row:
                    if b.get("url"):
                        r.append({"text": b["text"], "url": b["url"]})
                    else:
                        r.append({"text": b["text"], "callback_data": b.get("data")})
                kb.append(r)
            payload["reply_markup"] = {"inline_keyboard": kb}
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=30).read()

    def send_photo(self, chat_id, photo_url, caption="", parse_mode=None,
                   inline=None) -> None:  # pragma: no cover (needs network)
        import urllib.request
        payload = {"chat_id": chat_id, "photo": photo_url, "caption": caption}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if inline:
            rows = inline if isinstance(inline[0], list) else [inline]
            kb = []
            for row in rows:
                r = []
                for b in row:
                    r.append({"text": b["text"], "url": b["url"]} if b.get("url")
                             else {"text": b["text"], "callback_data": b.get("data")})
                kb.append(r)
            payload["reply_markup"] = {"inline_keyboard": kb}
        url = f"https://api.telegram.org/bot{self.token}/sendPhoto"
        req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=30).read()


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
            if logo and hasattr(transport, "send_photo"):
                try:
                    transport.send_photo(chat, logo, caption=text, parse_mode="HTML")
                except Exception:
                    # a bad image URL must never drop the alert
                    if getattr(transport, "send_html", False):
                        transport.send(chat, text, parse_mode="HTML")
                    else:
                        transport.send(chat, format_alert(a))
            elif getattr(transport, "send_html", False):
                transport.send(chat, text, parse_mode="HTML")
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
    """On-demand /check <token>: thin-market status + basic activity (no push)."""
    from indexer.alerts import is_thin_market
    conn = storage.pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT min(block_number) FROM launchpad_events "
                        "WHERE event_name='TokenCreated' AND token=%s", (token,))
            cb = cur.fetchone()[0]
            cur.execute("SELECT count(*), count(DISTINCT wallet), max(block) FROM legs "
                        "WHERE token=%s", (token,))
            n, w, lb = cur.fetchone()
            cur.execute("SELECT max(block_number) FROM swaps")
            head = int(cur.fetchone()[0] or 0)
    finally:
        storage.pool.putconn(conn)
    n = int(n or 0)
    w = int(w or 0)
    age = (head - int(cb)) if cb else 0
    reason = is_thin_market(n, w, age, no_trade_blocks=100000) if cb else None
    status = f"THIN MARKET ({reason})" if reason else "has market activity"
    return (f"check {token}\n"
            f"- created: block {cb} | age: {age} blocks\n"
            f"- activity: {n} swaps, {w} distinct wallets\n"
            f"- status: {status}")


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
    """Suppress repeated volume_collapse alerts for the same token within `window_s`."""
    kept = []
    for a in alerts:
        if a.kind == "volume_collapse" and not store.cooldown_ok(
                a.token, "volume_collapse", now_ts, window_s):
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
    store = SubscriptionStore(db)
    thr = Throttle(global_per_sec=20, per_chat_per_sec=1.0)
    transport = TelegramTransport(tok)
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
        return sym_lc.get((tok or "").lower(), "")

    def worker():
        while not stop.is_set():
            try:
                poll_once(tok, cmd_store, transport, token_exists, check_fn, clock["block"],
                          recent_fn=recent_fn, paper_price_fn=price_fn, symbol_fn=symbol_fn, timeout=25)
            except Exception as exc:
                if is_transient_poll_error(exc):
                    # expected long-poll idle / transient network: retry quietly
                    time.sleep(1)
                else:
                    import traceback
                    print("command poll error:\n" + traceback.format_exc(), flush=True)
                    time.sleep(2)

    threading.Thread(target=worker, daemon=True).start()

    try:
        while cycles <= 0 or k < cycles:
            k += 1
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
            alerts = state.apply_legs(legs, creators)
            alerts = apply_collapse_cooldown(alerts, store, int(time.time()), collapse_cooldown)
            now_ts = int(time.time())
            for a in alerts:
                a.context["symbol"] = symbols.get(a.token, "")
                if a.kind in ("dev_sell", "compound", "volume_collapse"):
                    store.add_paper_alert(a.kind, a.token, a.block, now_ts)
            store.enqueue_alert_many([a.__dict__ for a in alerts])
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
            if ingest_note == "ok" or not ingest:
                logger({"cycle": k, "new_legs": len(legs), "alerts": len(alerts),
                        "queue": store.queue_size(), "dispatched": n, "cursor": cursor})
            if cycles <= 0 or k < cycles:
                time.sleep(interval)
    finally:
        stop.set()
        store.close()
        cmd_store.close()
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
