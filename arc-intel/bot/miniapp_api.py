"""Read-only data layer for the Mini App (Part C, deliverable 1).

Turns the existing indexer/bot data into plain dicts the future UI will render. **Pure and
testable**: every function takes its dependencies (rows, price_fn, balance_fn, store) as
parameters, so tests run with fakes — no network, no PG, no signing, no UI.

Deliberately NOT here yet: HTTP endpoints and Telegram `initData` auth (see
`docs/ARC_AI_MINIAPP_SPEC.md` §7). Exposing per-user endpoints without that auth would be unsafe.
"""
from __future__ import annotations

from execution.positions import Position as TrackPosition, reconcile
from execution.strategy import Position as StrategyPosition, pnl_pct

SECONDS_PER_BLOCK = 0.52
EXPLORER = "https://explorer.arc.io/address/"


def format_price(price) -> str:
    p = float(price or 0.0)
    if p <= 0:
        return "n/a"
    if p >= 0.01:
        return f"${p:,.4f}"
    if p >= 1e-6:
        return f"${p:.8f}"
    return f"${p:.2e}"


def format_usd(v) -> str:
    v = float(v or 0.0)
    return f"${v:,.0f}" if v else "n/a"


def age_seconds(age_blocks) -> float:
    return int(age_blocks or 0) * SECONDS_PER_BLOCK


def age_text(age_blocks) -> str:
    secs = age_seconds(age_blocks)
    if secs >= 86400:
        return f"{secs / 86400:.1f} d"
    if secs >= 3600:
        return f"{secs / 3600:.1f} h"
    return f"{secs / 60:.0f} min"


def build_token_card(*, address, symbol="", name="", launchpad="", creator="",
                     created_block=None, head_block=0, swaps=0, wallets=0, vol24=0.0,
                     price=0.0, supply=0.0, thin_reason=None, creator_rep=None, risk=None,
                     safety=None, explorer_base: str = EXPLORER) -> dict:
    """Pure token card (mirrors the /check fields, as data instead of HTML)."""
    address = (address or "").lower()
    supply = float(supply or 0.0)
    price = float(price or 0.0)
    mcap = price * supply
    age = (int(head_block or 0) - int(created_block)) if created_block else 0
    return {
        "address": address,
        "symbol": symbol or "",
        "name": name or "",
        "launchpad": launchpad or "unknown",
        "creator": creator or "",
        "created_block": int(created_block) if created_block else None,
        "age_blocks": age,
        "age_text": age_text(age) if created_block else "unknown",
        "swaps": int(swaps or 0),
        "wallets": int(wallets or 0),
        "price": price,
        "price_text": format_price(price),
        "supply": supply,
        "market_cap": mcap,
        "market_cap_text": format_usd(mcap),
        "vol24": float(vol24 or 0.0),
        "vol24_text": format_usd(vol24),
        "thin_market": thin_reason,
        "status": f"thin market ({thin_reason})" if thin_reason else "has market activity",
        "creator_rep": creator_rep or {},
        "risk": risk or {},
        "safety": safety or {},
        "explorer": f"{explorer_base}{address}",
    }


def position_view(row: dict, price=0.0, onchain_qty=None) -> dict:
    """One position row -> render dict with unrealized PnL and (optional) reconciliation."""
    qty = float(row.get("qty") or 0.0)
    cost = float(row.get("cost") or 0.0)
    avg = float(row.get("avg_cost") or 0.0)
    price = float(price or 0.0)
    value = qty * price
    unrealized = value - cost
    upct = pnl_pct(StrategyPosition(entry_price=avg, size=qty), price) if (avg > 0 and price > 0) else 0.0
    recon_ok = recon_diff = None
    if onchain_qty is not None:
        tp = TrackPosition(token=row.get("token", ""), qty=qty, cost=cost,
                           realized=float(row.get("realized") or 0.0),
                           last_block=int(row.get("last_block") or 0))
        recon_ok, recon_diff = reconcile(tp, float(onchain_qty))
    return {
        "token": row.get("token", ""),
        "qty": qty,
        "avg_cost": avg,
        "cost": cost,
        "realized": float(row.get("realized") or 0.0),
        "price": price,
        "value": value,
        "unrealized": unrealized,
        "unrealized_pct": upct,
        "reconciled": recon_ok,
        "reconcile_diff": recon_diff,
        "last_block": int(row.get("last_block") or 0),
    }


def position_views(store, user, price_fn=None, balance_fn=None) -> list:
    """All open positions for a user. price_fn(token)->float; balance_fn(token)->qty|None."""
    out = []
    for row in store.list_positions(user):
        price = price_fn(row["token"]) if price_fn else 0.0
        onchain = balance_fn(row["token"]) if balance_fn else None
        out.append(position_view(row, price, onchain))
    return out


def portfolio_summary(views: list) -> dict:
    cost = sum(float(v.get("cost") or 0.0) for v in views)
    value = sum(float(v.get("value") or 0.0) for v in views)
    realized = sum(float(v.get("realized") or 0.0) for v in views)
    unrealized = value - cost
    return {"positions": len(views), "cost": cost, "value": value,
            "unrealized": unrealized, "realized": realized,
            "unrealized_pct": (unrealized / cost) if cost else 0.0}


def alert_view(alert) -> dict:
    """Normalize an Alert object (or dict) to a render dict."""
    if isinstance(alert, dict):
        d = alert
    else:
        d = {k: getattr(alert, k, None) for k in
             ("token", "kind", "severity", "block", "wallet", "role", "amount_usdc",
              "pct_position", "context", "message")}
    return {"token": (d.get("token") or "").lower(),
            "kind": d.get("kind"), "severity": d.get("severity"),
            "block": int(d.get("block") or 0), "message": d.get("message") or "",
            "context": d.get("context") or {}}


def alerts_view(alerts: list) -> list:
    return [alert_view(a) for a in alerts]


def copy_view(wallets: list, settings: dict | None = None) -> dict:
    """Normalize tracked leader wallets + global filters for the Mini App."""
    s = settings or {}
    return {
        "wallets": [{"leader": (w.get("leader") or "").lower(),
                     "flat_usdc": w.get("flat_usdc"),
                     "enabled": bool(w.get("enabled"))} for w in (wallets or [])],
        "settings": {
            "min_buy_usdc": float(s.get("min_buy_usdc") or 0),
            "max_open": int(s.get("max_open") or 0),
            "sizing": s.get("sizing") or "flat",
            "flat_usdc": float(s.get("flat_usdc") if s.get("flat_usdc") is not None else 25),
            "mirror_sells": bool(s.get("mirror_sells", True)),
            "tp_pct": float(s.get("tp_pct") or 0),
            "sl_pct": float(s.get("sl_pct") or 0),
            "trailing_pct": float(s.get("trailing_pct") or 0),
            "dump_guard": bool(s.get("dump_guard", True)),
        },
    }


def tier_view(store, uid, now=None) -> dict:
    """Effective fee tier for a user: VIP (by 30d volume) > welcome (referred) > standard."""
    import time as _t
    from monetization import tiers as TI
    now = int(now if now is not None else _t.time())
    joined = int(store.get_state(f"joined:{uid}", "0") or 0)
    referred = bool(store.get_referrer(uid))
    vol = float(store.volume_by_user_since(now - 30 * 86400).get(str(uid), 0.0))
    t = TI.fee_bps_for(joined_ts=joined, now=now, referred=referred, volume_30d=vol)
    return {"tier": t["level"], "fee_bps": t["fee_bps"], "fee_pct": t["fee_bps"] / 100.0,
            "volume_30d": vol, "referred": referred}


def wallet_view(store, chat_id) -> dict:
    """Linked wallet + auto-followed tokens (from wallet tracking)."""
    addr = store.get_linked_wallet(chat_id)
    subs = store._auto_subs(chat_id)
    return {"linked_wallet": addr, "auto_subs": subs, "count": len(subs)}
