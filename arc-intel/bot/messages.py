"""Phase 6 — Telegram UX message formatting (pure). No bot token, no network.

Turns Phase 2 scores and Phase 3 alerts into human messages that explain the WHY, not just
notify (e.g. "73% win rate in 18 trades, early entry, last exits up"). Delivery (grammY /
python-telegram-bot) is wired later; this is the testable core.
"""
from __future__ import annotations

import html as _html

SEVERITY_EMOJI = {"high": "[HIGH]", "medium": "[MED]", "low": "[LOW]"}
EXPLORER = "https://explorer.arc.io/address/"
_RICH_EMOJI = {"high": "🔴", "medium": "🟠", "low": "🟡"}
_RICH_LABEL = {"dev_sell": "DEV-SELL", "volume_collapse": "VOLUME COLLAPSE",
               "compound": "COMPOSITE RISK", "liquidity_removal": "LIQUIDITY REMOVAL",
               "thin_market": "THIN MARKET", "volume_spike": "VOLUME UP + PRICE UP",
               "price_surge": "PRICE SURGE", "whale_buy": "WHALE BUY", "large_sell": "LARGE SELL"}
DISCOVERY_KINDS = {"volume_spike", "price_surge", "whale_buy"}


def _esc(s) -> str:
    return _html.escape(str(s if s is not None else ""))


def format_alert_rich(alert: dict) -> str:
    """Attractive, robust HTML alert: severity color, token symbol + explorer link.

    Keeps the disclaimer; severity colors the RISK (not a 'profit' signal).
    """
    tok = alert.get("token") or ""
    sym = (alert.get("context") or {}).get("symbol") or ""
    sev = alert.get("severity")
    kind = alert.get("kind")
    label = _RICH_LABEL.get(kind, (kind or "").upper())
    emoji = "\U0001F7E2" if kind in DISCOVERY_KINDS else _RICH_EMOJI.get(sev, "⚪")
    head = f"{emoji} <b>ARC AI · {_esc(label)}</b>"
    if sym:
        title = f"<b>${_esc(sym)}</b> · <code>{_esc(tok)}</code>"
    else:
        title = f"<code>{_esc(tok)}</code>"
    why = _esc(alert.get("message", ""))
    link = f'🔗 <a href="{EXPLORER}{_esc(tok)}">view on explorer</a>'
    return "\n".join([head, title, f"❓ {why}", link,
                      "<i>Not financial advice. Informational only.</i>"])


def format_wallet_context(score: dict) -> str:
    return (f"{score.get('win_rate', 0) * 100:.0f}% win rate in {score.get('trades', 0)} trades | "
            f"avg {score.get('avg_mult', 0):.2f}x | entry pct {score.get('entry_pct', 0):.2f} | "
            f"confidence {score.get('confidence', 'n/a')}")


def format_alert(alert: dict, score: dict | None = None) -> str:
    head = f"{SEVERITY_EMOJI.get(alert.get('severity'), '')} {alert.get('token')}"
    if alert.get("reasons"):
        body = "; ".join(r.get("rule", "") for r in alert["reasons"])
    else:
        body = alert.get("message", "")
    lines = [head, f"why: {body}"]
    if score:
        lines.append(f"wallet: {format_wallet_context(score)}")
    return "\n".join(lines)


def format_token_signal(token: str, score: dict | None, risk_flags: list[str] | None = None) -> str:
    flags = risk_flags or []
    parts = [f"token {token}"]
    if score:
        parts.append(format_wallet_context(score))
    if flags:
        parts.append("risk: " + ", ".join(flags))
    return " | ".join(parts)
