"""Copy-trading engine (multi-wallet): mirror the trades of every tracked leader wallet with the
follower's bot wallet (custodial "Modo Maestro").

Global filters (`copy_settings`) apply to all wallets: min buy, max open positions, sizing
(flat/proportional), mirror sells. Protection defaults (TP/SL/trailing/dump guard) are attached to
every copied fill.

DRY-RUN: `ARC_INTEL_COPY_DRY_RUN=1` (or dry_run=True) logs the intended mirror without executing.
Dormant without a custody wallet + `ARC_INTEL_SESSION_ENC_KEY`.
"""
from __future__ import annotations

import os
import time

from .copy import CopySettings, decide

STABLE_DEFAULT = "0x3600000000000000000000000000000000000000"


def default_executor(store, storage, *, logger=None):
    """Real executor using the custodial quick wallet. Callable(chat, wallet, trade, decision, settings)."""
    from execution import custody as C
    from execution.eip712 import new_nonce
    from execution.quotes import buy_quote, sell_quote
    from execution.sessions import decrypt_secret
    from bot import tokenmeta
    from bot.miniapp_data import load_pool, latest_price

    enc = os.environ.get("ARC_INTEL_SESSION_ENC_KEY")
    stable = os.environ.get("ARC_INTEL_STABLE", STABLE_DEFAULT)

    def _exec(chat, wallet, trade, decision, settings):
        c = store.get_custody(chat)
        if not c or not enc:
            return None
        tok = str(trade.get("token") or "").lower()
        pool = load_pool(storage, tok)
        if not pool:
            return None
        try:
            pk = decrypt_secret(c["enc_secret"], enc)
        except Exception:
            return None
        dec = tokenmeta.rpc_decimals(tok)
        slip = 3.0
        if decision["action"] == "buy":
            price = latest_price(storage, tok) or 0
            if price <= 0:
                return None
            amount_in = int(round(float(decision["usdc"]) * 1e6))
            q = buy_quote(amount_in_base=amount_in, token_price=price, token_decimals=dec,
                          slippage_pct=slip)
            C.ensure_permit2_approval(pk, stable)
            txh = C.swap(pk, pool=pool, token_in=stable, amount_in=amount_in,
                         min_out=q["min_out_base"], recipient=c["address"],
                         order_nonce=new_nonce(), deadline=int(time.time()) + 600)
            store.add_holding(chat, tok)
            store.record_fill(f"{(txh or '')}:copybuy", chat, tok, "buy",
                              float(q.get("expected_out") or 0), float(decision["usdc"]),
                              ts=int(time.time()))
            try:  # protection defaults attached to this copied fill
                if settings.tp_pct or settings.sl_pct or settings.trailing_pct:
                    store.set_exit_plan(chat, tok, settings.sl_pct, settings.tp_pct,
                                        settings.trailing_pct)
                if settings.dump_guard:
                    store.set_state(f"autoprotect:{chat}", "1")
            except Exception:
                pass
            return {"tx": txh, "qty": q.get("expected_out"), "usdc": decision["usdc"]}
        if decision["action"] == "sell":
            bal = C.erc20_balance(tok, c["address"])
            if bal <= 0:
                return None
            qty = int(bal) / (10 ** dec)
            price = latest_price(storage, tok) or 0
            q = sell_quote(qty=qty, price=price, token_decimals=dec, floor_pct=slip)
            C.ensure_permit2_approval(pk, tok)
            txh = C.swap(pk, pool=pool, token_in=tok, amount_in=q["amount_in_base"],
                         min_out=q["min_out_base"], recipient=c["address"],
                         order_nonce=new_nonce(), deadline=int(time.time()) + 600)
            store.record_fill(f"{(txh or '')}:copysell", chat, tok, "sell", qty, qty * price,
                              ts=int(time.time()))
            return {"tx": txh, "qty": qty}
        return None

    return _exec


def run_copy_engine(store, storage, *, head: int = 0, dry_run=None, logger=None, executor=None,
                    on_exec=None, limit: int = 20) -> dict:
    """One pass: for every tracked wallet, mirror the leader's trades newer than `last_block`."""
    logger = logger or (lambda d: None)
    if dry_run is None:
        dry_run = os.environ.get("ARC_INTEL_COPY_DRY_RUN") == "1"
    wallets = store.list_all_copy_wallets(enabled_only=True)
    summary = {"wallets": len(wallets), "trades": 0, "executed": 0, "skipped": 0, "errors": 0}
    if not wallets:
        return summary
    exec_fn = executor or default_executor(store, storage, logger=logger)
    settings_cache, open_cache = {}, {}
    for w in wallets:
        follower, leader = w["follower_chat"], w["leader"]
        if follower not in settings_cache:
            settings_cache[follower] = CopySettings.from_row(store.get_copy_settings(follower))
            open_cache[follower] = len(store.list_positions(follower))
        eff = settings_cache[follower].with_flat(w.get("flat_usdc"))
        last = int(w.get("last_block") or 0)
        if last <= 0:
            last = int(head or 0)   # first run: jump to head, copy nothing historical
            store.set_copy_wallet_last_block(follower, leader, last)
            if last <= 0:
                continue
        try:
            trades = storage.recent_wallet_legs(leader, last, limit=limit)
        except Exception as e:
            summary["errors"] += 1
            logger({"copy_error": {"leader": leader, "err": "fetch:" + str(e)[:100]}})
            continue
        advanced = last
        for t in trades:
            blk = int((t or {}).get("block") or 0)
            if blk <= last:
                continue
            summary["trades"] += 1
            tok = str(t.get("token") or "").lower()
            try:
                pos = store.get_position(follower, tok)
                d = decide(t, eff, pos["qty"], open_cache[follower], holding=pos["qty"] > 0)
            except Exception as e:
                summary["errors"] += 1
                logger({"copy_error": {"token": tok, "err": "decide:" + str(e)[:100]}})
                break
            if d["action"] == "skip":
                summary["skipped"] += 1
                advanced = max(advanced, blk)
                continue
            if dry_run:
                summary["executed"] += 1
                advanced = max(advanced, blk)
                logger({"copy_dry": {"leader": leader, "token": tok, "decision": d}})
                continue
            try:
                res = exec_fn(follower, w, t, d, eff)
            except Exception as e:
                summary["errors"] += 1
                logger({"copy_error": {"leader": leader, "token": tok, "err": str(e)[:120]}})
                break  # do not advance past a failed trade -> retry next cycle
            if res:
                summary["executed"] += 1
                advanced = max(advanced, blk)
                if d["action"] == "buy":
                    open_cache[follower] = len(store.list_positions(follower))
                logger({"copy_exec": {"leader": leader, "token": tok, "action": d["action"],
                                      "tx": (res or {}).get("tx", "")}})
                if on_exec:
                    try:
                        on_exec(follower, w, t, d, res)
                    except Exception:
                        pass
            else:
                summary["skipped"] += 1
                advanced = max(advanced, blk)
        if advanced != last:
            store.set_copy_wallet_last_block(follower, leader, advanced)
    return summary
