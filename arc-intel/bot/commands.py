"""Telegram commands (polling) — multiuser onboarding. No execution.

Commands: /start, /help, /subscribe <token>, /unsubscribe <token>, /check <token>,
/settings <kinds>, /list. All inputs validated; errors are friendly and never crash
the process (handled by caller).
"""
from __future__ import annotations

import html as _html
import json
import os
import re
import time
import urllib.request

from . import i18n

ADDR_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
ALLOWED_KINDS = {"dev_sell", "volume_collapse", "compound"}
CLOSED_BETA = ("This bot is in closed beta. Send /start to request access and the operator "
               "will enable it if there is room.")
DISCLAIMER = ("Not financial advice. Alerts are informational and derived from on-chain data; "
              "they are not guarantees and can be wrong. Always do your own research.")
ONBOARDING = ("ARC AI — on-chain risk alerts for Arc.\n"
              "I watch Arc tokens and warn you about dev-sells, volume collapses and "
              "compound risk (so you can decide for yourself).\n\n"
              "Get started:\n"
              "/subscribe <token>   — follow a token (future alerts only)\n"
              "/subscribe_recent [n] [hours] — follow the n most active recent tokens\n"
              "/check <token>       — quick market/activity check\n"
              "/list                — your subscriptions\n"
              "/pending             — your [PAPER] proposals\n"
              "/approve <id> [code]   /cancel <id>\n"
              "/stats               — signal value (with both faces)\n"
              "/settings dev_sell,volume_collapse,compound\n\n"
              + DISCLAIMER)
HELP = ONBOARDING

# Links (overridable via env; defaults point at the public repo/docs).
DOCS_URL = os.environ.get("ARC_INTEL_DOCS_URL",
                          "https://github.com/Salado210102/arc-smart-orders/tree/main/docs")
REPO_URL = os.environ.get("ARC_INTEL_REPO_URL",
                          "https://github.com/Salado210102/arc-smart-orders")

# Persistent reply keyboard. Labels are normalized to commands in `_normalize`.
MENU_ROWS = [
    ["\U0001F4CB My alerts", "\U0001F50E Check token"],
    ["\U0001F4CA Stats", "\u23F3 Pending"],
    ["\U0001F4BC Positions", "\u2699\uFE0F Settings"],
    ["\U0001F4C4 Disclaimer", "\u2753 Help"],
]
LABEL_TO_CMD = {
    "\U0001F4CB my alerts": "/list",
    "\U0001F50E check token": "/check",
    "\U0001F4CA stats": "/stats",
    "\u23F3 pending": "/pending",
    "\U0001F4BC positions": "/positions",
    "\u2699\uFE0F settings": "/settings",
    "\U0001F4C4 disclaimer": "/disclaimer",
    "\u2753 help": "/help",
}
LINKS = [{"text": "\U0001F4DA Docs", "url": DOCS_URL},
         {"text": "\U0001F4BB Repo", "url": REPO_URL}]


def _valid_addr(token: str) -> bool:
    return bool(ADDR_RE.match(token or ""))


def _normalize(text: str) -> str:
    """Map reply-keyboard labels and pasted token addresses to real commands."""
    raw = (text or "").strip()
    low = raw.lower()
    if low in LABEL_TO_CMD:
        return LABEL_TO_CMD[low]
    if _valid_addr(raw):
        return "/check " + raw
    parts = raw.split()
    if len(parts) >= 2 and parts[0].lower() in ("check", "ca") and _valid_addr(parts[1]):
        return "/check " + parts[1]
    return raw


def _lang(store, chat_id) -> str:
    return i18n.normalize_lang(store.get_state(f"lang:{chat_id}", i18n.DEFAULT))


def command_reply_rich(text: str, chat_id, store, token_exists, check_fn, now_block: int,
                       recent_fn=None, paper_price_fn=None, symbol_fn=None):
    """Like `command_reply`, but returns a dict {text, inline} for menu commands.

    Kept separate so `command_reply` stays a pure str (existing tests/consumers unchanged)."""
    norm = _normalize(text)
    lang = _lang(store, chat_id)
    cmd = (norm.split() or [""])[0].lower().split("@")[0]
    if cmd == "/language":
        return {"text": i18n.t("language_choose", lang), "inline": i18n.language_buttons()}
    reply = command_reply(norm, chat_id, store, token_exists, check_fn, now_block,
                          recent_fn=recent_fn, paper_price_fn=paper_price_fn, symbol_fn=symbol_fn)
    if cmd in ("/start", "/help", "/menu"):
        return {"text": reply, "inline": i18n.menu_buttons(lang), "parse_mode": "HTML"}
    if cmd in ("/list", "/stats", "/wallet", "/connect"):
        return {"text": reply, "parse_mode": "HTML"}
    return reply


def is_authorized(store, chat_id) -> bool:
    admin = store.get_state("admin_chat")
    if admin and str(chat_id) == str(admin):
        return True
    return store.is_allowed(chat_id)


def _is_admin(store, chat_id) -> bool:
    admin = store.get_state("admin_chat")
    return bool(admin and str(chat_id) == str(admin))


def command_reply(text: str, chat_id, store, token_exists, check_fn, now_block: int,
                  recent_fn=None, paper_price_fn=None, symbol_fn=None) -> str:
    text = _normalize(text)
    parts = (text or "").strip().split()
    if not parts:
        return HELP
    cmd = parts[0].lower().split("@")[0]
    arg = parts[1].lower() if len(parts) > 1 else ""
    lang = _lang(store, chat_id)
    if cmd in ("/start", "/help", "/menu"):
        store.ensure_subscriber(chat_id, since_block=now_block)
        return i18n.welcome_text(lang)
    if cmd == "/language":
        return i18n.t("language_choose", lang)
    if cmd == "/disclaimer":
        return i18n.t("disclaimer", lang)
    if cmd == "/wallet":
        w = store.get_wallet(chat_id)
        head = i18n.t("wallet_connected", lang).format(addr=w) if w else i18n.t("wallet_none", lang)
        return head + "\n\n" + i18n.t("wallet_text", lang)
    if cmd == "/connect":
        if not _valid_addr(arg):
            return i18n.t("connect_prompt", lang)
        store.set_wallet(chat_id, arg)
        return i18n.t("connect_ok", lang).format(addr=arg)
    if cmd == "/allow":
        if not _is_admin(store, chat_id):
            return "Not authorized."
        if not arg or not arg.lstrip("-").isdigit():
            return "Usage: /allow <chat_id>"
        store.add_allow(arg)
        return f"Allowed {arg}."
    if cmd == "/requests":
        if not _is_admin(store, chat_id):
            return "Not authorized."
        reqs = store.list_requests()
        return "Requests:\n" + "\n".join(r["chat_id"] for r in reqs) if reqs else "No pending requests."
    if cmd == "/stats":
        from indexer.paper_eval import live_report
        rep = live_report(store, 45)
        lines = ["\U0001F4CA <b>Signal value</b> \u00B7 <i>[PAPER, simulated]</i>", ""]
        for kind in ("dev_sell", "compound", "volume_collapse"):
            d = rep.get(kind)
            h = (d or {}).get("horizons", {}).get("1h", {})
            n = int(h.get("n_real") or 0) if h else 0
            if n < 10:
                lines.append(f"\u2022 <b>{kind}</b> \u2014 not enough data yet (n={n})")
                continue
            ci = h.get("median_ci95_pct") or [0, 0]
            miss = h.get("max_missed_upside_x")
            if miss and miss > 1:
                tail = (f"tail: token pumped after the alert, missed up to ~{miss:.1f}x upside "
                        f"(opportunity cost, not a capital loss)")
            else:
                tail = "tail: none large in this sample"
            lines.append(f"\u2022 <b>{kind}</b> \u00B7 n={n}")
            lines.append(f"   helps ~{h['median_delayed_pct']}% vs holding (95% CI {ci[0]}\u2013{ci[1]})")
            lines.append(f"   positive in {h['pct_positive_delayed']}% of cases")
            lines.append(f"   {tail}")
            lines.append("")
        lines.append("<i>Both faces shown: typical benefit AND tail risk. Not financial advice.</i>")
        return "\n".join(lines)
    if cmd == "/pending":
        from .approvals import pending as ap_pending
        rows = ap_pending(store, chat_id, int(time.time()))
        if not rows:
            return "[PAPER] No pending approvals."
        lines = ["[PAPER] Pending approvals:"]
        for a in rows:
            lines.append(f"#{a['id']} {a['kind']} {a['token']} notional {a['notional']} "
                         f"cancel_until {a['cancel_until']} 2fa={'yes' if a['requires_2fa'] else 'no'}")
        return "\n".join(lines)
    if cmd == "/positions":
        rows = store.list_approvals(chat_id, 8)
        if not rows:
            return ("[PAPER] No positions yet. Approve a proposal (see /pending) to open a "
                    "simulated position.")
        lines = ["[PAPER] Positions (simulated, NOT financial advice):"]
        for a in rows:
            lines.append(f"#{a['id']} {str(a['status']).upper()} {a['kind']} {a['token']} "
                         f"side {a['side']} notional {a['notional']}")
        lines.append("Paper only: no real funds move.")
        return "\n".join(lines)
    if cmd in ("/approve", "/confirm"):
        from .approvals import approve as ap_approve, paper_result
        if not arg or not arg.isdigit():
            return "Usage: /approve <id> [code]"
        aid = int(arg)
        code = parts[2] if len(parts) > 2 else None
        a = store.get_approval(aid)
        ok, reason = ap_approve(store, chat_id, aid, int(time.time()), code=code)
        if not ok:
            if reason == "2fa_required":
                a2 = store.get_approval(aid)
                return (f"[PAPER] 2FA required for #{aid}. Simulated code: {a2['code']}. "
                        f"Use /confirm {aid} <code>.")
            return f"[PAPER] Cannot approve #{aid}: {reason}."
        if a:
            store.add_paper_alert(a["kind"], a["token"], a["alert_block"], int(time.time()))
        msg = f"[PAPER] Approved #{aid} ({a['kind']} {a['token']})."
        if a:
            msg += "\n" + paper_result(paper_price_fn, a["token"], a["alert_block"])
        return msg
    if cmd == "/cancel":
        from .approvals import cancel as ap_cancel
        if not arg or not arg.isdigit():
            return "Usage: /cancel <id>"
        ok, reason = ap_cancel(store, chat_id, int(arg), int(time.time()))
        return (f"[PAPER] Cancelled #{arg}." if ok else f"[PAPER] Cannot cancel #{arg}: {reason}.")
    if cmd == "/list":
        row = store.get(chat_id)
        if not row or not row["tokens"]:
            return i18n.t("no_subs", lang)
        toks = sorted(row["tokens"])
        kinds = ", ".join(sorted(row["kinds"])) or "all"
        lines = [f"\U0001F4CB <b>{i18n.t('subs_header', lang)}</b> \u00B7 {len(toks)}"]
        for i, tok in enumerate(toks, 1):
            sym = ""
            if symbol_fn:
                try:
                    sym = symbol_fn(tok) or ""
                except Exception:
                    sym = ""
            if sym:
                lines.append(f"{i}. <b>{_html.escape(sym)}</b> \u00B7 <code>{tok}</code>")
            else:
                lines.append(f"{i}. <code>{tok}</code>")
        lines.append("")
        lines.append(f"\u2699\uFE0F <b>{kinds}</b>")
        return "\n".join(lines)
    if cmd == "/subscribe":
        if not arg:
            return "Usage: /subscribe <token>"
        if not _valid_addr(arg):
            return "Invalid address. Expect 0x + 40 hex chars."
        if not token_exists(arg):
            return "Token not found in the indexed set."
        ok, reason = store.add_token(chat_id, arg, now_block=now_block)
        if not ok:
            return f"Cannot subscribe: {reason} (max {store.MAX_TOKENS} tokens per user)."
        if reason == "already":
            return f"Already subscribed to {arg}."
        return f"Subscribed to {arg}. You'll get future alerts only."
    if cmd == "/unsubscribe":
        if not _valid_addr(arg):
            return "Usage: /unsubscribe <token> (0x + 40 hex)"
        ok, reason = store.remove_token(chat_id, arg)
        if not ok:
            return f"Not subscribed: {arg}." if reason == "not_found" else "No subscriptions."
        return f"Unsubscribed from {arg}."
    if cmd == "/subscribe_recent":
        n = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 10
        hours = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 24
        n = max(1, min(n, store.MAX_TOKENS))
        window_blocks = hours * 6923  # ~blocks/hour at 0.52s
        tokens = recent_fn(n, window_blocks) if recent_fn else []
        if not tokens:
            return "No recent active tokens found."
        added, already, skipped = [], 0, 0
        for t in tokens:
            ok, reason = store.add_token(chat_id, t, now_block=now_block)
            if ok and reason == "added":
                added.append(t)
            elif ok and reason == "already":
                already += 1
            elif not ok and str(reason).startswith("limit"):
                skipped += 1
        parts_msg = [f"Subscribed to {len(added)} new recent token(s) (last {hours}h)"]
        if already:
            parts_msg.append(f"{already} already followed")
        if skipped:
            parts_msg.append(f"{skipped} skipped (max {store.MAX_TOKENS}/user)")
        msg = ", ".join(parts_msg)
        return msg + (":\n" + "\n".join(added) if added else ".")
    if cmd == "/check":
        if not _valid_addr(arg):
            return i18n.t("paste_prompt", lang)
        try:
            return check_fn(arg)
        except Exception:
            return "Could not check that token right now."
    if cmd == "/settings":
        if not arg:
            return "Usage: /settings dev_sell,volume_collapse,compound"
        kinds = {k.strip() for k in arg.split(",") if k.strip()}
        if not kinds or not kinds <= ALLOWED_KINDS:
            return "Allowed kinds: dev_sell, volume_collapse, compound"
        store.set_kinds(chat_id, kinds)
        return "Kinds set: " + ",".join(sorted(kinds))
    return "Unknown command. /help"


def _get_updates(bot_token: str, offset: int, timeout: int = 25):
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    body = json.dumps({"offset": offset, "timeout": timeout,
                       "allowed_updates": ["message", "callback_query"]}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=timeout + 10)).get("result", [])


def _emit(transport, chat, reply) -> str:
    """Send a reply. Never raise: if the formatted (HTML) send fails, retry as plain text."""
    if isinstance(reply, dict):
        text = reply["text"]
        kw = {"keyboard": reply.get("keyboard"), "inline": reply.get("inline")}
        try:
            transport.send(chat, text, parse_mode=reply.get("parse_mode"), **kw)
        except Exception:
            try:
                transport.send(chat, text, parse_mode=None, **kw)
            except Exception:
                pass
        return text
    try:
        transport.send(chat, reply)
    except Exception:
        pass
    return reply


def _answer_callback(bot_token, callback_id) -> None:
    try:
        url = f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery"
        body = json.dumps({"callback_query_id": callback_id}).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10).read()
    except Exception:
        pass


def _handle_callback(data, chat, store, token_exists, check_fn, now_block,
                     recent_fn=None, paper_price_fn=None, symbol_fn=None):
    lang = _lang(store, chat)
    if data.startswith("lang:"):
        code = data.split(":", 1)[1]
        if code in i18n.LANGS:
            store.set_state(f"lang:{chat}", code)
            return {"text": i18n.welcome_text(code), "inline": i18n.menu_buttons(code),
                    "parse_mode": "HTML"}
        return {"text": i18n.t("language_choose", lang), "inline": i18n.language_buttons()}
    if data.startswith("soon:"):
        return i18n.t("soon_text", lang)
    if data.startswith("cmd:"):
        return command_reply_rich(data[4:], chat, store, token_exists, check_fn, now_block,
                                  recent_fn=recent_fn, paper_price_fn=paper_price_fn, symbol_fn=symbol_fn)
    return "Unknown action."


def _log_command(chat, cmd, reply) -> None:
    try:
        with open("/root/arc-intel/command.log", "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": int(time.time()), "chat": str(chat),
                                 "cmd": cmd, "reply": reply}) + "\n")
    except OSError:
        pass


def poll_once(bot_token, store, transport, token_exists, check_fn, now_block,
              recent_fn=None, paper_price_fn=None, symbol_fn=None, timeout: int = 25) -> int:
    offset = int(store.get_state("tg_offset", "0") or 0)
    if offset == 0:
        # skip any backlog so we don't reply to old messages
        try:
            backlog = _get_updates(bot_token, 0, 0)
            if backlog:
                offset = max(int(u.get("update_id", 0)) for u in backlog) + 1
                store.set_state("tg_offset", str(offset))
        except Exception:
            pass
    updates = _get_updates(bot_token, offset, timeout)
    n = 0
    for u in updates:
        offset = max(offset, int(u.get("update_id", 0)) + 1)

        # --- inline button press ---
        cb = u.get("callback_query")
        if cb:
            _answer_callback(bot_token, cb.get("id"))
            chat = ((cb.get("message") or {}).get("chat") or {}).get("id")
            if chat is None:
                continue
            data = cb.get("data") or ""
            if not is_authorized(store, chat):
                store.add_request(chat, int(time.time()))
                log_reply = _emit(transport, chat, CLOSED_BETA)
            else:
                try:
                    reply = _handle_callback(data, chat, store, token_exists, check_fn, now_block,
                                             recent_fn=recent_fn, paper_price_fn=paper_price_fn,
                                             symbol_fn=symbol_fn)
                except Exception as exc:
                    reply = f"Error handling action: {type(exc).__name__}"
                log_reply = _emit(transport, chat, reply)
            _log_command(chat, f"cb:{data}", log_reply)
            n += 1
            continue

        # --- text message ---
        msg = u.get("message") or {}
        text = msg.get("text")
        chat = (msg.get("chat") or {}).get("id")
        if not text or chat is None:
            continue
        if not is_authorized(store, chat):
            store.add_request(chat, int(time.time()))
            log_reply = _emit(transport, chat, CLOSED_BETA)
        else:
            try:
                reply = command_reply_rich(text, chat, store, token_exists, check_fn, now_block,
                                           recent_fn=recent_fn, paper_price_fn=paper_price_fn,
                                           symbol_fn=symbol_fn)
            except Exception as exc:
                reply = f"Error handling command: {type(exc).__name__}"
            log_reply = _emit(transport, chat, reply)
        _log_command(chat, text, log_reply)
        n += 1
    store.set_state("tg_offset", str(offset))
    return n
