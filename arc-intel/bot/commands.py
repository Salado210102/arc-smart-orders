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
import threading
import time
import urllib.request

from . import i18n
from .sender import DirectSender

ADDR_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
ALLOWED_KINDS = {"dev_sell", "compound", "volume_spike"}
ALL_KINDS = ["dev_sell", "compound", "volume_spike"]
KIND_LABELS = {"dev_sell": "Dev-sell", "compound": "Compound risk",
               "volume_spike": "Volume spike"}


def _enabled_kinds(store, chat) -> set:
    """Empty stored set = all enabled (default); {'none'} = all muted."""
    row = store.get(chat)
    cur = set(row["kinds"]) if row else set()
    if not cur:
        return set(ALL_KINDS)
    if cur == {"none"}:
        return set()
    return cur


def settings_screen(store, chat, lang) -> dict:
    enabled = _enabled_kinds(store, chat)
    rows = []
    for k in ALL_KINDS:
        mark = "\u2705" if k in enabled else "\u2B1C"
        rows.append([{"text": f"{mark} {KIND_LABELS[k]}", "data": f"setkind:{k}"}])
    return {"text": i18n.t("settings_text", lang), "inline": rows, "parse_mode": "HTML"}


def _toggle_kind(store, chat, kind) -> None:
    if kind not in ALLOWED_KINDS:
        return
    enabled = _enabled_kinds(store, chat)
    if kind in enabled:
        enabled.discard(kind)
    else:
        enabled.add(kind)
    if len(enabled) == len(ALL_KINDS):
        store.set_kinds(chat, set())      # default (empty = all)
    elif not enabled:
        store.set_kinds(chat, {"none"})   # muted
    else:
        store.set_kinds(chat, enabled)
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
              "/settings dev_sell,compound,volume_spike\n\n"
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


def _route(text: str, chat_id, store) -> str:
    """If the chat is in 'connect wallet' mode and a bare address arrives, treat it as the
    wallet to connect (so the user just pastes + sends, no /connect needed)."""
    raw = (text or "").strip()
    if _valid_addr(raw) and str(store.get_state(f"awaiting_wallet:{chat_id}", "0")) == "1":
        store.set_state(f"awaiting_wallet:{chat_id}", "0")
        return "/link_wallet " + raw
    return _normalize(raw)


def command_reply_rich(text: str, chat_id, store, token_exists, check_fn, now_block: int,
                       recent_fn=None, paper_price_fn=None, symbol_fn=None):
    """Like `command_reply`, but returns a dict {text, inline} for menu commands.

    Kept separate so `command_reply` stays a pure str (existing tests/consumers unchanged)."""
    norm = _route(text, chat_id, store)
    lang = _lang(store, chat_id)
    cmd = (norm.split() or [""])[0].lower().split("@")[0]
    if cmd == "/language":
        return {"text": i18n.t("language_choose", lang), "inline": i18n.language_buttons()}
    if cmd == "/settings" and len(norm.split()) == 1:
        return settings_screen(store, chat_id, lang)
    if cmd == "/wallet":
        return wallet_screen(store, chat_id, lang)
    reply = command_reply(norm, chat_id, store, token_exists, check_fn, now_block,
                          recent_fn=recent_fn, paper_price_fn=paper_price_fn, symbol_fn=symbol_fn)
    if cmd == "/help":
        btns = i18n.menu_buttons(lang)
        btns.append([{"text": i18n.t("btn_docs", lang), "url": i18n.DOCS_URL}])
        return {"text": reply, "inline": btns, "parse_mode": "HTML"}
    if cmd in ("/start", "/menu"):
        return {"text": reply, "inline": i18n.menu_buttons(lang), "parse_mode": "HTML"}
    if cmd == "/check":
        parts2 = norm.split()
        if len(parts2) > 1 and _valid_addr(parts2[1]):
            card = _token_card(store, chat_id, parts2[1], reply, lang, paper_price_fn)
            card["parse_mode"] = "HTML"
            return card
        return {"text": reply, "parse_mode": "HTML"}
    if cmd in ("/list", "/stats", "/wallet", "/connect", "/link_wallet", "/unlink_wallet"):
        return {"text": reply, "parse_mode": "HTML"}
    return reply


def _paper_trade(data, chat, store, lang, price_fn) -> str:
    side, token = data.split(":", 1)
    token = token.lower()
    price = 0.0
    if price_fn:
        try:
            series = price_fn(token) or []
            price = float(series[-1][1]) if series else 0.0
        except Exception:
            price = 0.0
    if price <= 0:
        return "[PAPER] No price available for this token right now."
    notional = 10.0
    if side == "buy":
        qty = notional / price
        store.record_fill(f"paperbuy:{chat}:{token}:{int(time.time() * 1000)}",
                          chat, token, "buy", qty, notional)
        p = store.get_position(chat, token)
        return (f"\U0001F7E2 [PAPER] Bought ~{qty:.4g} tokens for ${notional:.0f} "
                f"(simulated at ${price:.8g}).\nPosition: {p['qty']:.4g} · avg ${p['avg_cost']:.8g}")
    p = store.get_position(chat, token)
    if p["qty"] <= 0:
        return "\U0001F534 [PAPER] No position to sell. Use \U0001F7E2 Buy first."
    qty = p["qty"]
    proceeds = qty * price
    store.record_fill(f"papersell:{chat}:{token}:{int(time.time() * 1000)}",
                      chat, token, "sell", qty, proceeds)
    p2 = store.get_position(chat, token)
    return (f"\U0001F534 [PAPER] Sold {qty:.4g} tokens for ${proceeds:.2f} (simulated).\n"
            f"Realized: ${p2['realized']:.2f}")


def is_authorized(store, chat_id) -> bool:
    admin = store.get_state("admin_chat")
    if admin and str(chat_id) == str(admin):
        return True
    return store.is_allowed(chat_id)


def _is_admin(store, chat_id) -> bool:
    admin = store.get_state("admin_chat")
    return bool(admin and str(chat_id) == str(admin))


def wallet_screen(store, chat, lang) -> dict:
    from . import tokenmeta as _tm
    w = store.get_wallet(chat)
    note = i18n.t("wallet_text", lang)
    rows = []
    if w:
        bal = ""
        try:
            nat = _tm.native_balance_eth(w) / 1e18
            usd = _tm.erc20_balance(w)
            bal = i18n.t("wallet_balances", lang).format(native=nat, usdc=usd)
        except Exception:
            bal = ""
        head = i18n.t("wallet_connected", lang).format(addr=w)
        text = head + (("\n" + bal) if bal else "") + "\n\n" + note
        rows.append([{"text": i18n.t("btn_change_wallet", lang), "data": "cmd:/connect"},
                     {"text": i18n.t("btn_disconnect", lang), "data": "disconnect"}])
        rows.append([{"text": i18n.t("btn_refresh", lang), "data": "wallet:refresh"}])
    else:
        text = i18n.t("wallet_none", lang) + "\n\n" + note
        rows.append([{"text": i18n.t("btn_connect", lang), "data": "cmd:/connect"}])
        rows.append([{"text": i18n.t("btn_refresh", lang), "data": "wallet:refresh"}])
    return {"text": text, "inline": rows, "parse_mode": "HTML"}


def _paper_price(price_fn, token) -> float:
    if not price_fn:
        return 0.0
    try:
        s = price_fn(token) or []
        return float(s[-1][1]) if s else 0.0
    except Exception:
        return 0.0


def _paper_buy(store, chat, token, notional, price_fn) -> str:
    token = str(token).lower()
    price = _paper_price(price_fn, token)
    if price <= 0:
        return "[PAPER] No price available for this token right now."
    qty = float(notional) / price
    store.record_fill(f"paperbuy:{chat}:{token}:{int(time.time() * 1000)}",
                      chat, token, "buy", qty, float(notional))
    p = store.get_position(chat, token)
    return (f"\U0001F7E2 [PAPER] Bought ~{qty:.4g} for ${float(notional):.2f} "
            f"(at ${price:.8g}).\nPosition: {p['qty']:.4g} \u00B7 avg ${p['avg_cost']:.8g}")


def _paper_sell_pct(store, chat, token, pct, price_fn) -> str:
    from execution.positions import Position, sell_quantity
    token = str(token).lower()
    p = store.get_position(chat, token)
    if p["qty"] <= 0:
        return "\U0001F534 [PAPER] No position to sell."
    price = _paper_price(price_fn, token)
    if price <= 0:
        return "[PAPER] No price available right now."
    sell_qty = sell_quantity(Position(token, qty=p["qty"], cost=p["cost"]), pct)
    proceeds = sell_qty * price
    store.record_fill(f"papersell:{chat}:{token}:{int(time.time() * 1000)}",
                      chat, token, "sell", sell_qty, proceeds)
    p2 = store.get_position(chat, token)
    return (f"\U0001F534 [PAPER] Sold {int(pct * 100)}% (~{sell_qty:.4g}) for ${proceeds:.2f}.\n"
            f"Realized: ${p2['realized']:.2f} \u00B7 left {p2['qty']:.4g}")


def _arm_protect(store, chat, token, pct, floor_pct, price_fn) -> str:
    from execution.eip712 import min_out_from_floor, new_nonce
    token = str(token).lower()
    pos = store.get_position(chat, token)
    if pos["qty"] <= 0:
        return "\U0001F6E1\uFE0F [PAPER] No position to protect. Buy first."
    price = _paper_price(price_fn, token)
    if price <= 0:
        return "\U0001F6E1\uFE0F No price available right now."
    qty = pos["qty"] * pct / 100.0
    min_out = min_out_from_floor(price, qty, floor_pct)
    deadline = int(time.time()) + 30 * 24 * 3600
    nonce = new_nonce()
    pid = store.create_preorder(chat, chat, token, pct, floor_pct, min_out, deadline, nonce,
                                status="armed")
    return (f"\U0001F6E1\uFE0F [PAPER] Protection <b>#{pid}</b> ARMED \u2014 sell <b>{pct:.0f}%</b> "
            f"(~{qty:.4g}) if a dev-sell/rug trigger fires (floor ${min_out:.2f}, ~30 days).\n"
            f"<i>The real (signed, non-custodial) version arrives with the signing UX (Opción 2).</i>")


def fire_preorders(store, alerts, transport, thr, price_fn) -> int:
    """On a matching alert, fire armed pre-orders (PAPER: simulated sell + notify)."""
    fired = 0
    seen = set()
    for a in alerts:
        kind = getattr(a, "kind", None) or (a.get("kind") if isinstance(a, dict) else None)
        token = getattr(a, "token", None) or (a.get("token") if isinstance(a, dict) else None)
        if kind not in ("dev_sell", "compound") or not token:
            continue
        for po in store.preorders_for_token(token):
            if po["id"] in seen:
                continue
            seen.add(po["id"])
            if store.get_position(po["chat"], token)["qty"] <= 0:
                store.set_preorder_status(po["id"], "no_position")
                continue
            #  Real path (only when a signed order + relayer are configured); else [PAPER] fallback.
            executor = os.environ.get("ARC_INTEL_EXECUTOR")
            relayer = os.environ.get("ARC_INTEL_RELAYER_KEY")
            if po.get("signature") and executor and relayer:
                try:
                    from execution.preorders import submit_execute
                    txh = submit_execute(po, executor, os.environ.get("ARC_RPC",
                                        "https://rpc.mainnet.arc.io"), relayer)
                    store.set_preorder_status(po["id"], "executed")
                    thr.wait(po["chat"])
                    transport.send(po["chat"], f"\U0001F6E1\uFE0F PROTECTION #{po['id']} EXECUTED "
                                               f"on-chain ({kind}): {txh}")
                    fired += 1
                    continue
                except Exception:
                    pass  # fall back to [PAPER]
            _paper_sell_pct(store, po["chat"], token, po["pct"] / 100.0, price_fn)
            store.set_preorder_status(po["id"], "executed")
            try:
                thr.wait(po["chat"])
                transport.send(po["chat"], f"\U0001F6E1\uFE0F [PAPER] PROTECTION #{po['id']} FIRED "
                                           f"({kind}): sold {po['pct']:.0f}% of {token}.")
            except Exception:
                pass
            fired += 1
    return fired


def _token_card(store, chat, token, base_text, lang, price_fn) -> dict:
    """Token card + live-ish PnL + buy-size / sell-% buttons."""
    price = _paper_price(price_fn, token)
    p = store.get_position(chat, token)
    lines = [base_text]
    if p["qty"] > 0 and price > 0:
        unreal = p["qty"] * price - p["cost"]
        pct = (unreal / p["cost"] * 100) if p["cost"] else 0.0
        lines.append("")
        lines.append(f"\U0001F4BC <b>Position</b>: {p['qty']:.4g} \u00B7 avg ${p['avg_cost']:.8g}")
        lines.append(f"\U0001F4C8 <b>PnL</b>: {'+' if unreal >= 0 else ''}${unreal:.2f} "
                     f"({pct:+.1f}%) \u00B7 realized ${p['realized']:.2f}")
        btns = [[{"text": "\U0001F534 25%", "data": f"sellpct:{token}:25"},
                 {"text": "\U0001F534 50%", "data": f"sellpct:{token}:50"},
                 {"text": "\U0001F534 75%", "data": f"sellpct:{token}:75"},
                 {"text": "\U0001F534 100%", "data": f"sellpct:{token}:100"}],
                [{"text": "\U0001F7E2 Buy more", "data": f"buymenu:{token}"},
                 {"text": "\U0001F6E1\uFE0F Protect", "data": f"protect:{token}"}],
                [{"text": "\U0001F504 Refresh", "data": f"pos:{token}"}]]
    else:
        btns = [[{"text": "\U0001F7E2 Buy", "data": f"buymenu:{token}"},
                 {"text": "\U0001F6E1\uFE0F Protect", "data": f"protect:{token}"}],
                [{"text": "\U0001F504 Refresh", "data": f"pos:{token}"}]]
    return {"text": "\n".join(lines), "inline": btns}


def command_reply(text: str, chat_id, store, token_exists, check_fn, now_block: int,
                  recent_fn=None, paper_price_fn=None, symbol_fn=None) -> str:
    raw = (text or "").strip()
    amt_tok = store.get_state(f"awaiting_amount:{chat_id}", "")
    if amt_tok and re.fullmatch(r"\d+(?:\.\d+)?", raw):
        store.set_state(f"awaiting_amount:{chat_id}", "")
        return _paper_buy(store, chat_id, amt_tok, float(raw), paper_price_fn)
    text = _route(text, chat_id, store)
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
    if cmd == "/link_wallet":
        if not _valid_addr(arg):
            return i18n.t("link_bad", lang)
        store.link_wallet(chat_id, arg)
        store.set_wallet(chat_id, arg)
        store.ensure_subscriber(chat_id, since_block=now_block)
        store.set_state(f"awaiting_wallet:{chat_id}", "0")
        return i18n.t("link_ok", lang).format(addr=arg)
    if cmd == "/unlink_wallet":
        n = store.unlink_wallet(chat_id)
        return i18n.t("unlink_ok", lang).format(n=n)
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
        for kind in ("dev_sell", "compound", "volume_spike"):
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
        kinds = " \u00B7 ".join(sorted(row["kinds"])) or "all"
        lines = [f"\U0001F4CB <b>{i18n.t('subs_header', lang)}</b>  <i>({len(toks)})</i>", ""]
        for i, tok in enumerate(toks, 1):
            sym = ""
            if symbol_fn:
                try:
                    sym = symbol_fn(tok) or ""
                except Exception:
                    sym = ""
            short = tok[:6] + "\u2026" + tok[-4:]
            if sym:
                lines.append(f"{i}. <b>{_html.escape(sym)}</b>  \u00B7  <code>{short}</code>")
            else:
                lines.append(f"{i}. <code>{short}</code>")
        lines.append("")
        lines.append(f"\u2699\uFE0F {_html.escape(kinds)}")
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
            store.promote_to_manual(chat_id, arg)
            return f"Already subscribed to {arg}."
        store.promote_to_manual(chat_id, arg)
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
            return "Usage: /settings dev_sell,compound,volume_spike"
        kinds = {k.strip() for k in arg.split(",") if k.strip()}
        if not kinds or not kinds <= ALLOWED_KINDS:
            return "Allowed kinds: dev_sell, compound, volume_spike"
        store.set_kinds(chat_id, kinds)
        return "Kinds set: " + ",".join(sorted(kinds))
    return "Unknown command. /help"


def _get_updates(bot_token: str, offset: int, timeout: int = 25):
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    body = json.dumps({"offset": offset, "timeout": timeout,
                       "allowed_updates": ["message", "callback_query"]}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=timeout + 4)).get("result", [])


def _emit(sender, chat, reply) -> str:
    """Send a reply via the sender (pool or direct). Never raises here."""
    if isinstance(reply, dict):
        text = reply["text"]
        try:
            sender.send(chat, text, parse_mode=reply.get("parse_mode"),
                        keyboard=reply.get("keyboard"), inline=reply.get("inline"),
                        remove_keyboard=reply.get("remove_keyboard", False))
        except Exception:
            pass
        return text
    try:
        sender.send(chat, reply)
    except Exception:
        pass
    return reply


def _answer_callback(bot_token, callback_id) -> bool:
    try:
        url = f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery"
        body = json.dumps({"callback_query_id": callback_id}).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10).read()
        return True
    except Exception as exc:
        try:
            with open("/root/arc-intel/answer.log", "a", encoding="utf-8") as fh:
                fh.write(f"{int(time.time())} {type(exc).__name__} {getattr(exc, 'code', '')}\n")
        except OSError:
            pass
        return False


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
    if data.startswith("setkind:"):
        _toggle_kind(store, chat, data.split(":", 1)[1])
        screen = settings_screen(store, chat, lang)
        screen["edit"] = True
        return screen
    if data == "disconnect":
        store.set_wallet(chat, "")
        screen = wallet_screen(store, chat, lang)
        screen["edit"] = True
        return screen
    if data == "wallet:refresh":
        screen = wallet_screen(store, chat, lang)
        screen["edit"] = True
        return screen
    if data.startswith("buymenu:"):
        tok = data.split(":", 1)[1]
        btns = [[{"text": "$10", "data": f"buyamt:{tok}:10"},
                 {"text": "$20", "data": f"buyamt:{tok}:20"},
                 {"text": "$50", "data": f"buyamt:{tok}:50"},
                 {"text": "$100", "data": f"buyamt:{tok}:100"}],
                [{"text": "\u270F\uFE0F Other", "data": f"buycustom:{tok}"}],
                [{"text": "\u2B05\uFE0F Back", "data": f"pos:{tok}"}]]
        return {"text": "\U0001F7E2 <b>Buy</b> \u2014 choose amount (USD, [PAPER]):",
                "parse_mode": "HTML", "inline": btns, "edit": True}
    if data.startswith("buyamt:"):
        _, tok, amt = data.split(":")
        return _paper_buy(store, chat, tok, float(amt), paper_price_fn)
    if data.startswith("buycustom:"):
        tok = data.split(":", 1)[1]
        store.set_state(f"awaiting_amount:{chat}", tok)
        return "\u270F\uFE0F Type the amount in USD to buy (e.g. 25):"
    if data.startswith("sellpct:"):
        _, tok, pct = data.split(":")
        return _paper_sell_pct(store, chat, tok, float(pct) / 100.0, paper_price_fn)
    if data.startswith("pos:"):
        tok = data.split(":", 1)[1]
        try:
            base = check_fn(tok)
        except Exception:
            base = ""
        card = _token_card(store, chat, tok, base, lang, paper_price_fn)
        card["parse_mode"] = "HTML"
        card["edit"] = True
        return card
    if data.startswith("protect:"):
        tok = data.split(":", 1)[1]
        btns = [[{"text": "25%", "data": f"protectpct:{tok}:25"},
                 {"text": "50%", "data": f"protectpct:{tok}:50"},
                 {"text": "75%", "data": f"protectpct:{tok}:75"},
                 {"text": "100%", "data": f"protectpct:{tok}:100"}],
                [{"text": "\u2B05\uFE0F Back", "data": f"pos:{tok}"}]]
        return {"text": "\U0001F6E1\uFE0F <b>Protect</b> \u2014 how much to sell when a dev-sell fires?",
                "parse_mode": "HTML", "inline": btns, "edit": True}
    if data.startswith("protectpct:"):
        _, tok, pct = data.split(":")
        btns = [[{"text": "\u221220%", "data": f"protectfloor:{tok}:{pct}:20"},
                 {"text": "\u221230%", "data": f"protectfloor:{tok}:{pct}:30"},
                 {"text": "\u221250%", "data": f"protectfloor:{tok}:{pct}:50"},
                 {"text": "Any price", "data": f"protectfloor:{tok}:{pct}:99"}],
                [{"text": "\u2B05\uFE0F Back", "data": f"protect:{tok}"}]]
        return {"text": "\U0001F6E1\uFE0F Floor price (worst acceptable):",
                "parse_mode": "HTML", "inline": btns, "edit": True}
    if data.startswith("protectfloor:"):
        _, tok, pct, floor = data.split(":")
        return _arm_protect(store, chat, tok, float(pct), float(floor), paper_price_fn)
    if data.startswith("buy:") or data.startswith("sell:"):
        return _paper_trade(data, chat, store, lang, paper_price_fn)
    if data == "cmd:/connect":
        store.set_state(f"awaiting_wallet:{chat}", "1")
        return {"text": i18n.t("connect_paste", lang), "parse_mode": "HTML"}
    if data.startswith("cmd:"):
        return command_reply_rich(data[4:], chat, store, token_exists, check_fn, now_block,
                                  recent_fn=recent_fn, paper_price_fn=paper_price_fn, symbol_fn=symbol_fn)
    return "Unknown action."


def _log_latency(kind, data, msg_date, t_recv) -> None:
    try:
        now = time.time()
        rec = {"kind": kind, "data": str(data)[:40], "recv_ms": int(t_recv * 1000),
               "sent_ms": int(now * 1000), "handle_ms": int((now - t_recv) * 1000)}
        if msg_date:
            rec["msg_date"] = int(msg_date)
            rec["pickup_ms"] = int((t_recv - msg_date) * 1000)
        with open("/root/arc-intel/cmd_latency.log", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
    except OSError:
        pass


def _log_command(chat, cmd, reply) -> None:
    try:
        with open("/root/arc-intel/command.log", "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": int(time.time()), "chat": str(chat),
                                 "cmd": cmd, "reply": reply}) + "\n")
    except OSError:
        pass


def poll_once(bot_token, store, transport, token_exists, check_fn, now_block,
              recent_fn=None, paper_price_fn=None, symbol_fn=None, sender=None,
              timeout: int = 25) -> int:
    if sender is None:
        sender = DirectSender(transport)
    try:
        with open("/root/arc-intel/poll.log", "a", encoding="utf-8") as fh:
            fh.write(str(int(time.time())) + "\n")
    except OSError:
        pass
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
        t_recv = time.time()
        offset = max(offset, int(u.get("update_id", 0)) + 1)

        # --- inline button press ---
        cb = u.get("callback_query")
        if cb:
            # Non-blocking: never let answerCallbackQuery hang the poller (it was the 10s stall).
            threading.Thread(target=_answer_callback, args=(bot_token, cb.get("id")),
                             daemon=True).start()
            cm = cb.get("message") or {}
            chat = (cm.get("chat") or {}).get("id")
            message_id = cm.get("message_id")
            if chat is None:
                continue
            data = cb.get("data") or ""
            if not is_authorized(store, chat):
                store.add_request(chat, int(time.time()))
                log_reply = _emit(sender, chat, CLOSED_BETA)
            else:
                try:
                    reply = _handle_callback(data, chat, store, token_exists, check_fn, now_block,
                                             recent_fn=recent_fn, paper_price_fn=paper_price_fn,
                                             symbol_fn=symbol_fn)
                except Exception as exc:
                    reply = f"Error handling action: {type(exc).__name__}"
                if isinstance(reply, dict) and reply.get("edit") and message_id is not None:
                    try:
                        sender.edit(chat, message_id, reply["text"],
                                    parse_mode=reply.get("parse_mode"),
                                    inline=reply.get("inline"))
                    except Exception:
                        _emit(sender, chat, reply)
                    log_reply = reply["text"]
                else:
                    log_reply = _emit(sender, chat, reply)
            _log_command(chat, f"cb:{data}", log_reply)
            _log_latency("cb", data, None, t_recv)
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
            log_reply = _emit(sender, chat, CLOSED_BETA)
        else:
            try:
                reply = command_reply_rich(text, chat, store, token_exists, check_fn, now_block,
                                           recent_fn=recent_fn, paper_price_fn=paper_price_fn,
                                           symbol_fn=symbol_fn)
            except Exception as exc:
                reply = f"Error handling command: {type(exc).__name__}"
            log_reply = _emit(sender, chat, reply)
        _log_command(chat, text, log_reply)
        _log_latency("msg", text, msg.get("date"), t_recv)
        n += 1
    store.set_state("tg_offset", str(offset))
    return n
