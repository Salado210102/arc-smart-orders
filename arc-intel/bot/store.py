"""Subscription store for the alert bot (chat_id -> tokens/wallets/kinds)."""
from __future__ import annotations

import secrets
import sqlite3
import time


class SubscriptionStore:
    MAX_TOKENS = 30

    def __init__(self, path: str = "bot_subs.db"):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS subscribers ("
            "chat_id TEXT PRIMARY KEY, tokens TEXT, wallets TEXT, kinds TEXT, "
            "since_block INTEGER DEFAULT 0)")
        try:
            self.conn.execute("ALTER TABLE subscribers ADD COLUMN since_block INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        # one-time migration: drop the legacy wildcard '*' (users subscribe explicitly)
        try:
            rows = self.conn.execute(
                "SELECT chat_id, tokens FROM subscribers WHERE tokens LIKE '%*%'").fetchall()
            for chat, toks in rows:
                newt = ",".join(t for t in (toks or "").split(",") if t and t != "*")
                self.conn.execute("UPDATE subscribers SET tokens=? WHERE chat_id=?", (newt, chat))
            self.conn.commit()
        except sqlite3.OperationalError:
            pass
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS delivered ("
            "chat_id TEXT, token TEXT, kind TEXT, block INTEGER, "
            "PRIMARY KEY (chat_id, token, kind, block))")
        self.conn.execute("CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT)")
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS aqueue (token TEXT, kind TEXT, block INTEGER, "
            "severity TEXT, message TEXT, context TEXT, "
            "PRIMARY KEY (token, kind, block))")
        self.conn.execute("CREATE TABLE IF NOT EXISTS allowlist (chat_id TEXT PRIMARY KEY)")
        self.conn.execute("CREATE TABLE IF NOT EXISTS requests (chat_id TEXT PRIMARY KEY, ts INTEGER)")
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS cooldowns (token TEXT, kind TEXT, ts INTEGER, "
            "PRIMARY KEY (token, kind))")
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS approvals ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id TEXT, token TEXT, kind TEXT, side TEXT, "
            "notional REAL, alert_block INTEGER, created_ts INTEGER, cancel_until INTEGER, "
            "expires_ts INTEGER, requires_2fa INTEGER, code TEXT, status TEXT, history TEXT, "
            "UNIQUE(chat_id, token, kind, alert_block))")
        try:
            self.conn.execute("ALTER TABLE approvals ADD COLUMN alert_block INTEGER")
        except sqlite3.OperationalError:
            pass
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS paper_alerts ("
            "kind TEXT, token TEXT, alert_block INTEGER, detected_ts INTEGER, "
            "PRIMARY KEY (kind, token, alert_block))")
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS paper_outcomes ("
            "kind TEXT, token TEXT, alert_block INTEGER, delay_seconds INTEGER, computed_ts INTEGER, "
            "horizons_json TEXT, PRIMARY KEY (kind, token, alert_block, delay_seconds))")
        # real fills (idempotent) + tracked positions (average cost)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS fills ("
            "fill_id TEXT PRIMARY KEY, user TEXT, token TEXT, side TEXT, qty REAL, "
            "usdc REAL, block INTEGER, ts INTEGER)")
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS positions ("
            "user TEXT, token TEXT, qty REAL, cost REAL, realized REAL, last_block INTEGER, "
            "PRIMARY KEY (user, token))")
        # pre-signed protective orders (arm -> fires on trigger)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS preorders ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, chat TEXT, user TEXT, token TEXT, pct REAL, "
            "floor_pct REAL, min_out REAL, deadline INTEGER, order_nonce INTEGER, status TEXT, "
            "created_ts INTEGER, signature TEXT, sign_token TEXT, sig_payload TEXT, "
            "kind TEXT DEFAULT 'sell')")
        # holdings (tokens bought through the bot wallet) + per-token exit plan (SL/TP %)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS holdings ("
            "chat TEXT, token TEXT, added_ts INTEGER, PRIMARY KEY (chat, token))")
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS exit_plans ("
            "chat TEXT, token TEXT, sl_pct REAL, tp_pct REAL, trailing_pct REAL, updated_ts INTEGER, "
            "PRIMARY KEY (chat, token))")
        try:
            self.conn.execute("ALTER TABLE exit_plans ADD COLUMN trailing_pct REAL")
        except sqlite3.OperationalError:
            pass
        # custodial quick wallet (Modo Maestro/Banana): bot-held key per user (encrypted)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS custody ("
            "chat TEXT PRIMARY KEY, address TEXT, enc_secret TEXT, created_ts INTEGER, status TEXT)")
        # session keys (Opción 3): scoped hot keys the user authorizes once
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS sessions ("
            "chat TEXT, session_key TEXT, enc_secret TEXT, executor TEXT, pool_id TEXT, "
            "token_in TEXT, max_per_order TEXT, max_total TEXT, min_out_floor TEXT, expiry INTEGER, "
            "status TEXT, created_ts INTEGER, PRIMARY KEY (chat, session_key))")
        # persisted alerts (for the Mini App Alerts tab with charts)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS alerts ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, token TEXT, kind TEXT, severity TEXT, "
            "block INTEGER, ts INTEGER, wallet TEXT, amount_usdc REAL, message TEXT, context TEXT, "
            "UNIQUE(token, kind, block))")
        # wallet tracking: read-only address link + which subs were auto-generated from it
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS wallet_links ("
            "chat_id TEXT PRIMARY KEY, address TEXT, created_ts INTEGER)")
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS auto_subs ("
            "chat_id TEXT, token TEXT, PRIMARY KEY (chat_id, token))")
        # referrals: per-user code -> owner, who was referred by whom, and accrued commissions
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS referral_codes ("
            "code TEXT PRIMARY KEY, owner_chat TEXT UNIQUE, created_ts INTEGER)")
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS referral_bindings ("
            "chat TEXT PRIMARY KEY, owner_chat TEXT, code TEXT, bound_ts INTEGER)")
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS referral_credits ("
            "fill_id TEXT PRIMARY KEY, owner_chat TEXT, buyer_chat TEXT, token TEXT, "
            "fee_usdc REAL, commission_usdc REAL, created_ts INTEGER, status TEXT DEFAULT 'accrued')")
        # contest: per-round settlement (who won, how much) + published marker
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS contest_rounds ("
            "round_id INTEGER PRIMARY KEY, published_ts INTEGER)")
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS contest_winners ("
            "round_id INTEGER, category TEXT, user TEXT, volume REAL, prize REAL, "
            "PRIMARY KEY (round_id, category))")
        # copy-trading: tracked leader wallets (many per follower) + global filters
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS copy_wallets ("
            "follower_chat TEXT, leader TEXT, flat_usdc REAL, enabled INTEGER DEFAULT 1, "
            "last_block INTEGER DEFAULT 0, created_ts INTEGER, "
            "PRIMARY KEY (follower_chat, leader))")
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS copy_settings ("
            "follower_chat TEXT PRIMARY KEY, min_buy_usdc REAL DEFAULT 0, max_open INTEGER DEFAULT 0, "
            "sizing TEXT DEFAULT 'flat', flat_usdc REAL DEFAULT 25, mirror_sells INTEGER DEFAULT 1, "
            "tp_pct REAL DEFAULT 0, sl_pct REAL DEFAULT 0, trailing_pct REAL DEFAULT 0, "
            "dump_guard INTEGER DEFAULT 1, updated_ts INTEGER)")
        for _col in ("signature TEXT", "sign_token TEXT", "sig_payload TEXT",
                     "kind TEXT DEFAULT 'sell'", "tx_hash TEXT", "attempts INTEGER DEFAULT 0"):
            try:
                self.conn.execute(f"ALTER TABLE preorders ADD COLUMN {_col}")
            except sqlite3.OperationalError:
                pass
        self.conn.commit()

    def subscribe(self, chat_id, tokens=(), wallets=(), kinds=()) -> None:
        self.conn.execute(
            "INSERT INTO subscribers(chat_id,tokens,wallets,kinds) VALUES(?,?,?,?) "
            "ON CONFLICT(chat_id) DO UPDATE SET tokens=excluded.tokens, wallets=excluded.wallets, "
            "kinds=excluded.kinds",
            (str(chat_id), ",".join(tokens), ",".join(wallets), ",".join(kinds)))
        self.conn.commit()

    def list(self) -> list[dict]:
        cur = self.conn.execute("SELECT chat_id,tokens,wallets,kinds,since_block FROM subscribers")
        out = []
        for chat_id, tokens, wallets, kinds, since in cur.fetchall():
            out.append({"chat_id": chat_id,
                        "tokens": (set((tokens or "").split(",")) - {""}) - {"*"},
                        "wallets": set((wallets or "").split(",")) - {""},
                        "kinds": set((kinds or "").split(",")) - {""},
                        "since_block": int(since or 0)})
        return out

    def get(self, chat_id) -> dict | None:
        cur = self.conn.execute(
            "SELECT chat_id,tokens,wallets,kinds,since_block FROM subscribers WHERE chat_id=?",
            (str(chat_id),))
        row = cur.fetchone()
        if not row:
            return None
        chat_id, tokens, wallets, kinds, since = row
        return {"chat_id": chat_id, "tokens": (set((tokens or "").split(",")) - {""}) - {"*"},
                "wallets": set((wallets or "").split(",")) - {""},
                "kinds": set((kinds or "").split(",")) - {""},
                "since_block": int(since or 0)}

    def ensure_subscriber(self, chat_id, since_block: int = 0) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO subscribers(chat_id,tokens,wallets,kinds,since_block) "
            "VALUES(?,?,?,?,?)", (str(chat_id), "", "", "", int(since_block)))
        self.conn.commit()

    def add_token(self, chat_id, token: str, now_block: int = 0,
                  allow_over_cap: bool = False) -> tuple[bool, str]:
        row = self.get(chat_id)
        if row is None:
            self.ensure_subscriber(chat_id, since_block=now_block)
            row = self.get(chat_id)
        tokens = set(row["tokens"])
        token = token.lower()
        if token in tokens:
            return True, "already"
        if not allow_over_cap and len(tokens) >= self.MAX_TOKENS:
            return False, f"limit_{self.MAX_TOKENS}"
        tokens.add(token)
        since = row["since_block"] or now_block
        self.conn.execute("UPDATE subscribers SET tokens=?, since_block=? WHERE chat_id=?",
                          (",".join(sorted(tokens)), int(since), str(chat_id)))
        self.conn.commit()
        return True, "added"

    def remove_token(self, chat_id, token: str) -> tuple[bool, str]:
        row = self.get(chat_id)
        if row is None:
            return False, "not_subscribed"
        tokens = set(row["tokens"])
        token = token.lower()
        if token not in tokens:
            return False, "not_found"
        tokens.discard(token)
        self.conn.execute("UPDATE subscribers SET tokens=? WHERE chat_id=?",
                          (",".join(sorted(tokens)), str(chat_id)))
        self.conn.commit()
        return True, "removed"

    def set_wallet(self, chat_id, wallet: str) -> None:
        if self.get(chat_id) is None:
            self.ensure_subscriber(chat_id)
        self.conn.execute("UPDATE subscribers SET wallets=? WHERE chat_id=?",
                          (wallet.lower(), str(chat_id)))
        self.conn.commit()

    def get_wallet(self, chat_id) -> str:
        row = self.get(chat_id)
        if not row or not row["wallets"]:
            return ""
        return sorted(row["wallets"])[0]

    def set_kinds(self, chat_id, kinds) -> None:
        row = self.get(chat_id)
        if row is None:
            self.ensure_subscriber(chat_id)
        self.conn.execute("UPDATE subscribers SET kinds=? WHERE chat_id=?",
                          (",".join(sorted(kinds)), str(chat_id)))
        self.conn.commit()

    def purge_queue(self, before_block: int) -> int:
        cur = self.conn.execute("DELETE FROM aqueue WHERE block < ?", (int(before_block),))
        self.conn.commit()
        return cur.rowcount

    # --- closed-beta allowlist ---
    def add_allow(self, chat_id) -> None:
        self.conn.execute("INSERT OR IGNORE INTO allowlist(chat_id) VALUES(?)", (str(chat_id),))
        self.conn.commit()

    def remove_allow(self, chat_id) -> bool:
        cur = self.conn.execute("DELETE FROM allowlist WHERE chat_id=?", (str(chat_id),))
        self.conn.commit()
        return cur.rowcount > 0

    def is_allowed(self, chat_id) -> bool:
        cur = self.conn.execute("SELECT 1 FROM allowlist WHERE chat_id=?", (str(chat_id),))
        return cur.fetchone() is not None

    def list_allow(self) -> list:
        return [r[0] for r in self.conn.execute("SELECT chat_id FROM allowlist ORDER BY chat_id")]

    def add_request(self, chat_id, ts: int) -> None:
        self.conn.execute("INSERT OR IGNORE INTO requests(chat_id,ts) VALUES(?,?)",
                          (str(chat_id), int(ts)))
        self.conn.commit()

    def list_requests(self) -> list:
        return [{"chat_id": r[0], "ts": r[1]} for r in
                self.conn.execute("SELECT chat_id,ts FROM requests ORDER BY ts")]

    # --- approvals (persistent) ---
    def create_approval(self, chat_id, token, kind, side, notional, alert_block, created_ts,
                        cancel_until, expires_ts, requires_2fa, code):
        import json as _json
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO approvals(chat_id,token,kind,side,notional,alert_block,"
            "created_ts,cancel_until,expires_ts,requires_2fa,code,status,history) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (str(chat_id), token, kind, side, float(notional), int(alert_block), int(created_ts),
             int(cancel_until), int(expires_ts), 1 if requires_2fa else 0, code, "pending",
             _json.dumps([["created", int(created_ts)]])))
        self.conn.commit()
        return int(cur.lastrowid) if cur.lastrowid else self._approval_id(chat_id, token, kind, alert_block)

    def _approval_id(self, chat_id, token, kind, alert_block):
        cur = self.conn.execute(
            "SELECT id FROM approvals WHERE chat_id=? AND token=? AND kind=? AND alert_block=?",
            (str(chat_id), token, kind, int(alert_block)))
        r = cur.fetchone()
        return int(r[0]) if r else 0

    def get_approval(self, approval_id) -> dict | None:
        import json as _json
        cur = self.conn.execute(
            "SELECT id,chat_id,token,kind,side,notional,alert_block,created_ts,cancel_until,"
            "expires_ts,requires_2fa,code,status,history FROM approvals WHERE id=?", (int(approval_id),))
        r = cur.fetchone()
        if not r:
            return None
        return {"id": r[0], "chat_id": r[1], "token": r[2], "kind": r[3], "side": r[4],
                "notional": r[5], "alert_block": r[6], "created_ts": r[7], "cancel_until": r[8],
                "expires_ts": r[9], "requires_2fa": bool(r[10]), "code": r[11], "status": r[12],
                "history": _json.loads(r[13] or "[]")}

    def list_open_approvals(self, chat_id, now: int) -> list:
        cur = self.conn.execute(
            "SELECT id FROM approvals WHERE chat_id=? AND status='pending' AND expires_ts>=? "
            "ORDER BY id", (str(chat_id), int(now)))
        return [self.get_approval(r[0]) for r in cur.fetchall()]

    def list_approvals(self, chat_id, limit: int = 10) -> list:
        cur = self.conn.execute(
            "SELECT id FROM approvals WHERE chat_id=? ORDER BY id DESC LIMIT ?",
            (str(chat_id), int(limit)))
        return [self.get_approval(r[0]) for r in cur.fetchall()]

    def approval_exists(self, chat_id, token, kind, alert_block) -> bool:
        cur = self.conn.execute(
            "SELECT 1 FROM approvals WHERE chat_id=? AND token=? AND kind=? AND alert_block=? LIMIT 1",
            (str(chat_id), token, kind, int(alert_block)))
        return cur.fetchone() is not None

    def update_approval(self, approval_id, status: str, ts: int, note: str) -> None:
        import json as _json
        row = self.get_approval(approval_id)
        hist = row["history"] if row else []
        hist.append([note, int(ts)])
        self.conn.execute("UPDATE approvals SET status=?, history=? WHERE id=?",
                          (status, _json.dumps(hist), int(approval_id)))
        self.conn.commit()

    # --- paper (live) alerts + outcomes ---
    def add_paper_alert(self, kind, token, alert_block, detected_ts) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO paper_alerts(kind,token,alert_block,detected_ts) VALUES(?,?,?,?)",
            (kind, token, int(alert_block or 0), int(detected_ts)))
        self.conn.commit()

    def list_pending_paper_alerts(self, ready_before_block, delay_seconds) -> list:
        cur = self.conn.execute(
            "SELECT kind,token,alert_block FROM paper_alerts pa WHERE alert_block <= ? "
            "AND NOT EXISTS (SELECT 1 FROM paper_outcomes po WHERE po.kind=pa.kind "
            "AND po.token=pa.token AND po.alert_block=pa.alert_block AND po.delay_seconds=?)",
            (int(ready_before_block), int(delay_seconds)))
        return [(r[0], r[1], int(r[2])) for r in cur.fetchall()]

    def save_paper_outcome(self, kind, token, alert_block, delay_seconds, computed_ts,
                           horizons_json) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO paper_outcomes(kind,token,alert_block,delay_seconds,computed_ts,"
            "horizons_json) VALUES(?,?,?,?,?,?)",
            (kind, token, int(alert_block), int(delay_seconds), int(computed_ts), horizons_json))
        self.conn.commit()

    def list_paper_outcomes(self, delay_seconds) -> list:
        import json as _json
        cur = self.conn.execute(
            "SELECT kind,token,alert_block,horizons_json FROM paper_outcomes WHERE delay_seconds=?",
            (int(delay_seconds),))
        return [{"kind": r[0], "token": r[1], "alert_block": r[2],
                 "horizons": _json.loads(r[3] or "{}")} for r in cur.fetchall()]

    # --- per-token cooldowns (e.g. volume_collapse spam control) ---
    def cooldown_ok(self, token, kind, now_ts: int, window_s: int) -> bool:
        cur = self.conn.execute("SELECT ts FROM cooldowns WHERE token=? AND kind=?",
                                (token, kind))
        row = cur.fetchone()
        if row and (int(now_ts) - int(row[0])) < int(window_s):
            return False
        self.conn.execute(
            "INSERT INTO cooldowns(token,kind,ts) VALUES(?,?,?) "
            "ON CONFLICT(token,kind) DO UPDATE SET ts=excluded.ts",
            (token, kind, int(now_ts)))
        self.conn.commit()
        return True

    # --- holdings + exit plans (SL/TP %) ---
    def add_holding(self, chat, token) -> None:
        self.conn.execute("INSERT OR IGNORE INTO holdings(chat,token,added_ts) VALUES(?,?,?)",
                          (str(chat), str(token).lower(), int(time.time())))
        self.conn.commit()

    def remove_holding(self, chat, token) -> None:
        self.conn.execute("DELETE FROM holdings WHERE chat=? AND token=?",
                          (str(chat), str(token).lower()))
        self.conn.commit()

    def list_holdings(self, chat) -> list:
        return [r[0] for r in self.conn.execute(
            "SELECT token FROM holdings WHERE chat=? ORDER BY added_ts DESC", (str(chat),)).fetchall()]

    def set_exit_plan(self, chat, token, sl_pct, tp_pct, trailing_pct=0) -> None:
        self.conn.execute(
            "INSERT INTO exit_plans(chat,token,sl_pct,tp_pct,trailing_pct,updated_ts) VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(chat,token) DO UPDATE SET sl_pct=excluded.sl_pct, tp_pct=excluded.tp_pct, "
            "trailing_pct=excluded.trailing_pct, updated_ts=excluded.updated_ts",
            (str(chat), str(token).lower(), float(sl_pct or 0), float(tp_pct or 0),
             float(trailing_pct or 0), int(time.time())))
        self.conn.commit()

    def get_exit_plan(self, chat, token) -> dict | None:
        r = self.conn.execute(
            "SELECT sl_pct,tp_pct,trailing_pct FROM exit_plans WHERE chat=? AND token=?",
            (str(chat), str(token).lower())).fetchone()
        return ({"sl_pct": float(r[0] or 0), "tp_pct": float(r[1] or 0),
                 "trailing_pct": float(r[2] or 0)} if r else None)

    def list_exit_plans(self, chat) -> dict:
        return {t: {"sl_pct": float(sl or 0), "tp_pct": float(tp or 0), "trailing_pct": float(tr or 0)}
                for t, sl, tp, tr in
                self.conn.execute("SELECT token,sl_pct,tp_pct,trailing_pct FROM exit_plans WHERE chat=?",
                                  (str(chat),)).fetchall()}

    # --- custodial quick wallet ---
    def save_custody(self, chat, address, enc_secret, status="active") -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO custody(chat,address,enc_secret,created_ts,status) VALUES(?,?,?,?,?)",
            (str(chat), str(address).lower(), enc_secret, int(time.time()), status))
        self.conn.commit()

    def get_custody(self, chat) -> dict | None:
        r = self.conn.execute("SELECT chat,address,enc_secret,created_ts,status FROM custody WHERE chat=?",
                              (str(chat),)).fetchone()
        if not r:
            return None
        return {"chat": r[0], "address": r[1], "enc_secret": r[2], "created_ts": int(r[3] or 0),
                "status": r[4]}

    def delete_custody(self, chat) -> None:
        self.conn.execute("DELETE FROM custody WHERE chat=?", (str(chat),))
        self.conn.commit()

    def list_custody_addresses(self) -> list:
        return [(r[0], r[1]) for r in self.conn.execute(
            "SELECT chat, address FROM custody WHERE status='active'").fetchall()]

    # --- session keys (Opción 3) ---
    def save_session(self, chat, session_key, enc_secret, executor, pool_id, token_in,
                     max_per_order, max_total, min_out_floor, expiry, status="active") -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO sessions(chat,session_key,enc_secret,executor,pool_id,token_in,"
            "max_per_order,max_total,min_out_floor,expiry,status,created_ts) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (str(chat), str(session_key).lower(), enc_secret, str(executor).lower(),
             str(pool_id).lower(), str(token_in).lower(), str(int(max_per_order)),
             str(int(max_total)), str(int(min_out_floor)), int(expiry), status, int(time.time())))
        self.conn.commit()

    def get_session(self, chat, pool_id, token_in, status="active") -> dict | None:
        r = self.conn.execute(
            "SELECT chat,session_key,enc_secret,executor,pool_id,token_in,max_per_order,max_total,"
            "min_out_floor,expiry,status FROM sessions "
            "WHERE chat=? AND pool_id=? AND token_in=? AND status=? ORDER BY created_ts DESC LIMIT 1",
            (str(chat), str(pool_id).lower(), str(token_in).lower(), status)).fetchone()
        return self._sess_row(r) if r else None

    def list_sessions(self, chat) -> list:
        return [self._sess_row(r) for r in self.conn.execute(
            "SELECT chat,session_key,enc_secret,executor,pool_id,token_in,max_per_order,max_total,"
            "min_out_floor,expiry,status FROM sessions WHERE chat=? ORDER BY created_ts DESC",
            (str(chat),)).fetchall()]

    def _sess_row(self, r) -> dict:
        return {"chat": r[0], "session_key": r[1], "enc_secret": r[2], "executor": r[3],
                "pool_id": r[4], "token_in": r[5], "max_per_order": int(r[6] or 0),
                "max_total": int(r[7] or 0), "min_out_floor": int(r[8] or 0), "expiry": int(r[9] or 0),
                "status": r[10]}

    def revoke_session(self, chat, session_key) -> bool:
        cur = self.conn.execute("UPDATE sessions SET status='revoked' WHERE chat=? AND session_key=?",
                                (str(chat), str(session_key).lower()))
        self.conn.commit()
        return cur.rowcount > 0

    # --- persisted alerts (idempotent by token+kind+block) ---
    def add_alert(self, alert, ts: int = 0) -> None:
        import json as _json
        d = alert if isinstance(alert, dict) else getattr(alert, "__dict__", {})
        self.conn.execute(
            "INSERT OR IGNORE INTO alerts(token,kind,severity,block,ts,wallet,amount_usdc,"
            "message,context) VALUES(?,?,?,?,?,?,?,?,?)",
            ((d.get("token") or "").lower(), d.get("kind"), d.get("severity"),
             int(d.get("block") or 0), int(ts or 0), (d.get("wallet") or ""), d.get("amount_usdc"),
             d.get("message") or "", _json.dumps(d.get("context") or {})))
        self.conn.commit()

    def recent_alerts(self, tokens=None, kinds=None, limit: int = 50) -> list:
        import json as _json
        q = ("SELECT token,kind,severity,block,ts,wallet,amount_usdc,message,context "
             "FROM alerts")
        conds, params = [], []
        if tokens:
            conds.append("token IN (" + ",".join("?" * len(tokens)) + ")")
            params += [str(t).lower() for t in tokens]
        if kinds:
            conds.append("kind IN (" + ",".join("?" * len(kinds)) + ")")
            params += list(kinds)
        if conds:
            q += " WHERE " + " AND ".join(conds)
        q += " ORDER BY block DESC LIMIT ?"
        params.append(int(limit))
        return [{"token": r[0], "kind": r[1], "severity": r[2], "block": int(r[3]),
                 "ts": int(r[4] or 0), "wallet": r[5], "amount_usdc": r[6], "message": r[7],
                 "context": _json.loads(r[8] or "{}")} for r in self.conn.execute(q, params).fetchall()]

    # --- real fills + positions (idempotent, average cost) ---
    def record_fill(self, fill_id, user, token, side, qty, usdc, block=0, ts=0) -> bool:
        """Record a CONFIRMED fill once (idempotent by fill_id) and update the position.
        Returns True if it was new, False if it was a duplicate (no double count)."""
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO fills(fill_id,user,token,side,qty,usdc,block,ts) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (str(fill_id), str(user).lower(), str(token).lower(), side, float(qty),
             float(usdc), int(block), int(ts)))
        if cur.rowcount == 0:
            self.conn.commit()
            return False
        from execution.positions import Position, apply_fill
        p = self.get_position(user, token)
        pos = Position(token=str(token).lower(), qty=p["qty"], cost=p["cost"],
                       realized=p["realized"], last_block=p["last_block"])
        apply_fill(pos, side, float(qty), float(usdc), int(block))
        self.conn.execute(
            "INSERT INTO positions(user,token,qty,cost,realized,last_block) VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(user,token) DO UPDATE SET qty=excluded.qty, cost=excluded.cost, "
            "realized=excluded.realized, last_block=excluded.last_block",
            (str(user).lower(), str(token).lower(), pos.qty, pos.cost, pos.realized, pos.last_block))
        self.conn.commit()
        # Watch the tokens the user holds: follow on an open position, unfollow when it closes.
        try:
            if pos.qty > 0:
                self.add_auto_sub(user, token, now_block=int(block))
            else:
                self.remove_auto_sub(user, token)
        except Exception:
            pass
        # Referral: credit the buyer's referrer a lifetime % of this fill's fee (idempotent).
        try:
            self.accrue_referral(fill_id, user, token, usdc, ts=int(ts or 0))
        except Exception:
            pass
        return True

    def get_position(self, user, token) -> dict:
        cur = self.conn.execute(
            "SELECT qty,cost,realized,last_block FROM positions WHERE user=? AND token=?",
            (str(user).lower(), str(token).lower()))
        r = cur.fetchone()
        if not r:
            return {"token": str(token).lower(), "qty": 0.0, "cost": 0.0, "realized": 0.0,
                    "avg_cost": 0.0, "last_block": 0}
        qty, cost, realized, lb = r
        return {"token": str(token).lower(), "qty": float(qty or 0), "cost": float(cost or 0),
                "realized": float(realized or 0),
                "avg_cost": (float(cost) / float(qty)) if qty else 0.0, "last_block": int(lb or 0)}

    def list_positions(self, user) -> list:
        cur = self.conn.execute(
            "SELECT token,qty,cost,realized,last_block FROM positions WHERE user=? AND qty>0 "
            "ORDER BY last_block DESC", (str(user).lower(),))
        return [{"token": r[0], "qty": float(r[1]), "cost": float(r[2]), "realized": float(r[3]),
                 "avg_cost": (float(r[2]) / float(r[1])) if r[1] else 0.0, "last_block": int(r[4])}
                for r in cur.fetchall()]

    # --- contest / volume (real fills only; [PAPER] never counts) ---
    def volume_by_user_since(self, ts: int) -> dict:
        rows = self.conn.execute(
            "SELECT user, COALESCE(SUM(usdc),0) FROM fills "
            "WHERE ts>=? AND fill_id NOT LIKE 'paper%' GROUP BY user", (int(ts),)).fetchall()
        return {r[0]: float(r[1] or 0.0) for r in rows}

    def referred_volume_by_user_since(self, ts: int) -> dict:
        rows = self.conn.execute(
            "SELECT rb.owner_chat, COALESCE(SUM(f.usdc),0) FROM fills f "
            "JOIN referral_bindings rb ON rb.chat=f.user "
            "WHERE f.ts>=? AND f.fill_id NOT LIKE 'paper%' GROUP BY rb.owner_chat",
            (int(ts),)).fetchall()
        return {r[0]: float(r[1] or 0.0) for r in rows}

    def volume_by_user_between(self, start, end) -> dict:
        rows = self.conn.execute(
            "SELECT user, COALESCE(SUM(usdc),0) FROM fills WHERE ts>=? AND ts<? "
            "AND fill_id NOT LIKE 'paper%' GROUP BY user", (int(start), int(end))).fetchall()
        return {r[0]: float(r[1] or 0.0) for r in rows}

    def referred_volume_between(self, start, end) -> dict:
        rows = self.conn.execute(
            "SELECT rb.owner_chat, COALESCE(SUM(f.usdc),0) FROM fills f "
            "JOIN referral_bindings rb ON rb.chat=f.user WHERE f.ts>=? AND f.ts<? "
            "AND f.fill_id NOT LIKE 'paper%' GROUP BY rb.owner_chat",
            (int(start), int(end))).fetchall()
        return {r[0]: float(r[1] or 0.0) for r in rows}

    def contest_round_published(self, round_id) -> bool:
        return self.conn.execute("SELECT 1 FROM contest_rounds WHERE round_id=?",
                                 (int(round_id),)).fetchone() is not None

    def mark_contest_round(self, round_id, ts=0) -> None:
        self.conn.execute("INSERT OR REPLACE INTO contest_rounds(round_id,published_ts) VALUES(?,?)",
                          (int(round_id), int(ts or time.time())))
        self.conn.commit()

    def record_contest_winner(self, round_id, category, user, volume, prize) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO contest_winners(round_id,category,user,volume,prize) "
            "VALUES(?,?,?,?,?)",
            (int(round_id), str(category), str(user), float(volume), float(prize)))
        self.conn.commit()

    def list_contest_winners(self, round_id) -> list:
        rows = self.conn.execute(
            "SELECT category,user,volume,prize FROM contest_winners WHERE round_id=?",
            (int(round_id),)).fetchall()
        return [{"category": r[0], "user": r[1], "volume": float(r[2]), "prize": float(r[3])}
                for r in rows]

    # --- pre-signed protective orders ---
    def create_preorder(self, chat, user, token, pct, floor_pct, min_out, deadline,
                        order_nonce, status="armed", created_ts=None, kind="sell") -> int:
        sign_token = secrets.token_urlsafe(16)
        cur = self.conn.execute(
            "INSERT INTO preorders(chat,user,token,pct,floor_pct,min_out,deadline,order_nonce,"
            "status,created_ts,sign_token,kind) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (str(chat), str(user).lower(), str(token).lower(), float(pct), float(floor_pct),
             float(min_out), int(deadline), int(order_nonce), status,
             int(created_ts if created_ts is not None else time.time()), sign_token, str(kind)))
        self.conn.commit()
        return int(cur.lastrowid)

    def _po_full(self, r) -> dict:
        d = self._po_row(r[:11])
        d.update({"signature": r[11], "sign_token": r[12], "sig_payload": r[13]})
        if len(r) > 14:
            d["kind"] = r[14]
        return d

    def get_preorder(self, pid) -> dict | None:
        r = self.conn.execute(
            "SELECT id,chat,user,token,pct,floor_pct,min_out,deadline,order_nonce,status,created_ts,"
            "signature,sign_token,sig_payload,kind FROM preorders WHERE id=?", (int(pid),)).fetchone()
        return self._po_full(r) if r else None

    def get_preorder_by_sign_token(self, sign_token) -> dict | None:
        r = self.conn.execute(
            "SELECT id,chat,user,token,pct,floor_pct,min_out,deadline,order_nonce,status,created_ts,"
            "signature,sign_token,sig_payload,kind FROM preorders WHERE sign_token=?",
            (str(sign_token),)).fetchone()
        return self._po_full(r) if r else None

    def save_sig_payload(self, pid, payload_json: str) -> None:
        self.conn.execute("UPDATE preorders SET sig_payload=? WHERE id=?", (payload_json, int(pid)))
        self.conn.commit()

    def attach_signature(self, pid, signature: str) -> None:
        self.conn.execute("UPDATE preorders SET signature=?, status='signed' WHERE id=?",
                          (signature, int(pid)))
        self.conn.commit()

    def _po_row(self, r) -> dict:
        return {"id": r[0], "chat": r[1], "user": r[2], "token": r[3], "pct": r[4],
                "floor_pct": r[5], "min_out": r[6], "deadline": r[7], "order_nonce": r[8],
                "status": r[9], "created_ts": r[10]}

    def preorders_for_token(self, token, active_only=True) -> list:
        q = ("SELECT id,chat,user,token,pct,floor_pct,min_out,deadline,order_nonce,status,created_ts "
             "FROM preorders WHERE token=?")
        if active_only:
            q += " AND status='armed' AND coalesce(kind,'sell')='sell'"
        return [self._po_row(r) for r in self.conn.execute(q, (str(token).lower(),)).fetchall()]

    def list_preorders(self, chat, active_only=True) -> list:
        q = ("SELECT id,chat,user,token,pct,floor_pct,min_out,deadline,order_nonce,status,created_ts "
             "FROM preorders WHERE chat=?")
        if active_only:
            q += " AND status='armed'"
        q += " ORDER BY id DESC"
        return [self._po_row(r) for r in self.conn.execute(q, (str(chat),)).fetchall()]

    def set_preorder_status(self, pid, status) -> None:
        self.conn.execute("UPDATE preorders SET status=? WHERE id=?", (status, int(pid)))
        self.conn.commit()

    def list_orders(self, kind=None, status=None, limit: int = 200) -> list:
        q = ("SELECT id,chat,user,token,pct,floor_pct,min_out,deadline,order_nonce,status,created_ts "
             "FROM preorders")
        conds, params = [], []
        if kind:
            conds.append("coalesce(kind,'sell')=?")
            params.append(str(kind))
        if status:
            conds.append("status=?")
            params.append(str(status))
        if conds:
            q += " WHERE " + " AND ".join(conds)
        q += " ORDER BY id DESC LIMIT ?"
        params.append(int(limit))
        return [self._po_row(r) for r in self.conn.execute(q, params).fetchall()]

    def orders_due(self, kind, now: int, limit: int = 50) -> list:
        """Signed orders of `kind`, not executed and not expired (ready for the keeper)."""
        rows = self.conn.execute(
            "SELECT id,chat,user,token,pct,floor_pct,min_out,deadline,order_nonce,status,created_ts,"
            "signature,sign_token,sig_payload,kind FROM preorders "
            "WHERE coalesce(kind,'sell')=? AND status='signed' AND deadline > ? ORDER BY id LIMIT ?",
            (str(kind), int(now), int(limit))).fetchall()
        return [self._po_full(r) for r in rows]

    def armed_orders(self, kind, now: int, limit: int = 50) -> list:
        """Armed orders of `kind` (with sig_payload) not yet executed and not expired."""
        rows = self.conn.execute(
            "SELECT id,chat,user,token,pct,floor_pct,min_out,deadline,order_nonce,status,created_ts,"
            "signature,sign_token,sig_payload,kind FROM preorders "
            "WHERE coalesce(kind,'sell')=? AND status='armed' AND deadline > ? ORDER BY id LIMIT ?",
            (str(kind), int(now), int(limit))).fetchall()
        return [self._po_full(r) for r in rows]

    def claim_order(self, pid) -> bool:
        """Atomically move 'signed' -> 'submitting' so two keepers can't submit the same order."""
        cur = self.conn.execute(
            "UPDATE preorders SET status='submitting' WHERE id=? AND status='signed'", (int(pid),))
        self.conn.commit()
        return cur.rowcount > 0

    def mark_executed(self, pid, tx_hash: str = "") -> None:
        self.conn.execute("UPDATE preorders SET status='executed', tx_hash=? WHERE id=?",
                          (str(tx_hash), int(pid)))
        self.conn.commit()

    def bump_attempt(self, pid) -> None:
        self.conn.execute("UPDATE preorders SET attempts=coalesce(attempts,0)+1 WHERE id=?",
                          (int(pid),))
        self.conn.commit()

    def cancel_preorder(self, pid, user) -> bool:
        """Cancel by owner: `user` may be the telegram chat (chat column) or the wallet."""
        u = str(user).lower()
        cur = self.conn.execute(
            "UPDATE preorders SET status='cancelled' WHERE id=? AND (chat=? OR user=?) "
            "AND status IN ('armed','signed','submitting')",
            (int(pid), u, u))
        self.conn.commit()
        return cur.rowcount > 0

    # --- wallet tracking (read-only public address) ---
    def link_wallet(self, chat_id, address: str) -> None:
        self.conn.execute(
            "INSERT INTO wallet_links(chat_id,address,created_ts) VALUES(?,?,?) "
            "ON CONFLICT(chat_id) DO UPDATE SET address=excluded.address, created_ts=excluded.created_ts",
            (str(chat_id), str(address).lower(), int(time.time())))
        self.conn.commit()

    def get_linked_wallet(self, chat_id) -> str:
        r = self.conn.execute("SELECT address FROM wallet_links WHERE chat_id=?",
                              (str(chat_id),)).fetchone()
        return r[0] if r else ""

    def list_linked_wallets(self) -> list:
        return [(r[0], r[1]) for r in self.conn.execute(
            "SELECT chat_id, address FROM wallet_links").fetchall()]

    def _auto_subs(self, chat_id) -> list:
        return [r[0] for r in self.conn.execute(
            "SELECT token FROM auto_subs WHERE chat_id=?", (str(chat_id),)).fetchall()]

    def is_auto_sub(self, chat_id, token) -> bool:
        cur = self.conn.execute("SELECT 1 FROM auto_subs WHERE chat_id=? AND token=?",
                                (str(chat_id), str(token).lower()))
        return cur.fetchone() is not None

    def add_auto_sub(self, chat_id, token, now_block: int = 0) -> bool:
        """Auto-subscribe (future alerts only). Only NEW subs are marked as auto; an existing
        (manual) subscription is left untouched."""
        token = str(token).lower()
        # A held token must always be watched -> auto-subs may exceed the manual cap.
        ok, reason = self.add_token(chat_id, token, now_block=now_block, allow_over_cap=True)
        if reason == "added":
            self.conn.execute("INSERT OR IGNORE INTO auto_subs(chat_id,token) VALUES(?,?)",
                              (str(chat_id), token))
            self.conn.commit()
            return True
        return False

    def remove_auto_sub(self, chat_id, token) -> bool:
        """Remove a subscription ONLY if it was auto-generated (manual stays)."""
        token = str(token).lower()
        if not self.is_auto_sub(chat_id, token):
            return False
        self.remove_token(chat_id, token)
        self.conn.execute("DELETE FROM auto_subs WHERE chat_id=? AND token=?", (str(chat_id), token))
        self.conn.commit()
        return True

    def promote_to_manual(self, chat_id, token) -> None:
        """A manual /subscribe on an auto token makes it manual (won't be auto-removed)."""
        self.conn.execute("DELETE FROM auto_subs WHERE chat_id=? AND token=?",
                          (str(chat_id), str(token).lower()))
        self.conn.commit()

    def unlink_wallet(self, chat_id) -> int:
        """Delete the link + all its auto-generated subs (manual subs stay). Returns count removed."""
        removed = 0
        for tok in self._auto_subs(chat_id):
            self.remove_token(chat_id, tok)
            removed += 1
        self.conn.execute("DELETE FROM auto_subs WHERE chat_id=?", (str(chat_id),))
        self.conn.execute("DELETE FROM wallet_links WHERE chat_id=?", (str(chat_id),))
        self.conn.execute("UPDATE subscribers SET wallets='' WHERE chat_id=?", (str(chat_id),))
        self.conn.commit()
        return removed

    # --- referrals (code -> owner, bindings, accrued commissions) ---
    def ensure_referral_code(self, chat, code) -> str:
        """Create the owner's code once (idempotent); returns the owner's stable code."""
        row = self.conn.execute("SELECT code FROM referral_codes WHERE owner_chat=?",
                                (str(chat),)).fetchone()
        if row:
            return row[0]
        from monetization import referrals as _refs
        fallback = _refs.make_code(f"{chat}:{secrets.token_hex(4)}")
        for cand in (str(code).upper(), fallback):
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO referral_codes(code,owner_chat,created_ts) VALUES(?,?,?)",
                (cand, str(chat), int(time.time())))
            self.conn.commit()
            if cur.rowcount:
                return cand
        row = self.conn.execute("SELECT code FROM referral_codes WHERE owner_chat=?",
                                (str(chat),)).fetchone()
        return row[0] if row else fallback

    def get_referral_code(self, chat) -> str:
        row = self.conn.execute("SELECT code FROM referral_codes WHERE owner_chat=?",
                                (str(chat),)).fetchone()
        return row[0] if row else ""

    def referral_owner(self, code) -> str:
        row = self.conn.execute("SELECT owner_chat FROM referral_codes WHERE code=?",
                                (str(code).upper(),)).fetchone()
        return row[0] if row else ""

    def bind_referral(self, chat, owner_chat, code) -> bool:
        """Bind `chat` to `owner_chat` (first binding wins; no self-referral). Returns new."""
        if str(chat) == str(owner_chat):
            return False
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO referral_bindings(chat,owner_chat,code,bound_ts) VALUES(?,?,?,?)",
            (str(chat), str(owner_chat), str(code).upper(), int(time.time())))
        self.conn.commit()
        return cur.rowcount > 0

    def get_referrer(self, chat) -> str:
        row = self.conn.execute("SELECT owner_chat FROM referral_bindings WHERE chat=?",
                                (str(chat),)).fetchone()
        return row[0] if row else ""

    def add_referral_credit(self, fill_id, owner_chat, buyer_chat, token, fee_usdc, commission_usdc,
                            ts=0) -> bool:
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO referral_credits(fill_id,owner_chat,buyer_chat,token,fee_usdc,"
            "commission_usdc,created_ts,status) VALUES(?,?,?,?,?,?,?,'accrued')",
            (str(fill_id), str(owner_chat), str(buyer_chat), str(token).lower(), float(fee_usdc),
             float(commission_usdc), int(ts or time.time())))
        self.conn.commit()
        return cur.rowcount > 0

    def accrue_referral(self, fill_id, buyer_chat, token, notional_usdc, ts=0,
                        fee_bps=100, pct_bps=3000) -> float:
        """Credit the buyer's referrer with a lifetime % of this fill's fee (idempotent by
        fill_id). Simulated [PAPER] fills never pay. Returns the commission (0 if none)."""
        if str(fill_id).startswith("paper"):
            return 0.0
        owner = self.get_referrer(buyer_chat)
        if not owner:
            return 0.0
        from monetization.referrals import fee_from_notional, commission_usdc
        fee = fee_from_notional(float(notional_usdc or 0), fee_bps)
        if fee <= 0:
            return 0.0
        comm = commission_usdc(fee, pct_bps)
        self.add_referral_credit(fill_id, owner, buyer_chat, token, fee, comm, ts=ts)
        return comm

    def list_referred(self, owner_chat) -> list:
        return [r[0] for r in self.conn.execute(
            "SELECT chat FROM referral_bindings WHERE owner_chat=? ORDER BY bound_ts DESC",
            (str(owner_chat),)).fetchall()]

    def referral_summary(self, owner_chat) -> dict:
        n = self.conn.execute("SELECT COUNT(*) FROM referral_bindings WHERE owner_chat=?",
                              (str(owner_chat),)).fetchone()[0]
        total, fills = self.conn.execute(
            "SELECT COALESCE(SUM(commission_usdc),0), COUNT(*) FROM referral_credits "
            "WHERE owner_chat=?", (str(owner_chat),)).fetchone()
        paid = self.conn.execute(
            "SELECT COALESCE(SUM(commission_usdc),0) FROM referral_credits WHERE owner_chat=? "
            "AND status='paid'", (str(owner_chat),)).fetchone()[0]
        total, paid = float(total or 0.0), float(paid or 0.0)
        return {"referred": int(n), "fills": int(fills or 0), "accrued": total,
                "paid": paid, "pending": total - paid}

    def referral_breakdown(self, owner_chat) -> list:
        """Per-referred-user totals (fills, fees, commission), highest commission first."""
        rows = self.conn.execute(
            "SELECT buyer_chat, COUNT(*), COALESCE(SUM(fee_usdc),0), "
            "COALESCE(SUM(commission_usdc),0), MAX(created_ts) FROM referral_credits "
            "WHERE owner_chat=? GROUP BY buyer_chat ORDER BY SUM(commission_usdc) DESC",
            (str(owner_chat),)).fetchall()
        return [{"buyer": r[0], "fills": int(r[1]), "fee_usdc": float(r[2]),
                 "commission_usdc": float(r[3]), "last_ts": int(r[4] or 0)} for r in rows]

    def list_referral_credits(self, owner_chat, limit: int = 50) -> list:
        return [{"buyer": r[0], "token": r[1], "fee_usdc": float(r[2]),
                 "commission_usdc": float(r[3]), "ts": int(r[4]), "status": r[5]}
                for r in self.conn.execute(
                    "SELECT buyer_chat,token,fee_usdc,commission_usdc,created_ts,status "
                    "FROM referral_credits WHERE owner_chat=? ORDER BY created_ts DESC LIMIT ?",
                    (str(owner_chat), int(limit))).fetchall()]

    # --- copy trading: tracked leader wallets ---
    def add_copy_wallet(self, follower, leader, flat_usdc=None, now_block=0) -> None:
        self.conn.execute(
            "INSERT INTO copy_wallets(follower_chat,leader,flat_usdc,enabled,last_block,created_ts) "
            "VALUES(?,?,?,1,?,?) ON CONFLICT(follower_chat,leader) DO UPDATE SET "
            "flat_usdc=excluded.flat_usdc, enabled=1",
            (str(follower), str(leader).lower(),
             (None if flat_usdc is None else float(flat_usdc)), int(now_block or 0),
             int(time.time())))
        self.conn.commit()

    _COW_COLS = "follower_chat,leader,flat_usdc,enabled,last_block,created_ts"

    def _copy_wallet_row(self, r) -> dict | None:
        if not r:
            return None
        return {"follower_chat": r[0], "leader": r[1],
                "flat_usdc": (None if r[2] is None else float(r[2])),
                "enabled": bool(r[3]), "last_block": int(r[4] or 0), "created_ts": int(r[5] or 0)}

    def get_copy_wallet(self, follower, leader) -> dict | None:
        return self._copy_wallet_row(self.conn.execute(
            "SELECT " + self._COW_COLS + " FROM copy_wallets WHERE follower_chat=? AND leader=?",
            (str(follower), str(leader).lower())).fetchone())

    def list_copy_wallets(self, follower) -> list:
        return [self._copy_wallet_row(r) for r in self.conn.execute(
            "SELECT " + self._COW_COLS + " FROM copy_wallets WHERE follower_chat=? "
            "ORDER BY created_ts", (str(follower),)).fetchall()]

    def list_all_copy_wallets(self, enabled_only=True) -> list:
        q = "SELECT " + self._COW_COLS + " FROM copy_wallets"
        if enabled_only:
            q += " WHERE enabled=1"
        return [self._copy_wallet_row(r) for r in self.conn.execute(q).fetchall()]

    def remove_copy_wallet(self, follower, leader) -> bool:
        cur = self.conn.execute("DELETE FROM copy_wallets WHERE follower_chat=? AND leader=?",
                                (str(follower), str(leader).lower()))
        self.conn.commit()
        return cur.rowcount > 0

    def set_copy_wallet_enabled(self, follower, leader, enabled: bool) -> bool:
        cur = self.conn.execute("UPDATE copy_wallets SET enabled=? WHERE follower_chat=? AND leader=?",
                                (1 if enabled else 0, str(follower), str(leader).lower()))
        self.conn.commit()
        return cur.rowcount > 0

    def set_copy_wallet_last_block(self, follower, leader, block: int) -> None:
        self.conn.execute("UPDATE copy_wallets SET last_block=? WHERE follower_chat=? AND leader=?",
                          (int(block), str(follower), str(leader).lower()))
        self.conn.commit()

    # --- copy trading: global filters (one row per follower) ---
    _CS_COLS = ("follower_chat,min_buy_usdc,max_open,sizing,flat_usdc,mirror_sells,tp_pct,sl_pct,"
                "trailing_pct,dump_guard,updated_ts")

    def get_copy_settings(self, follower) -> dict:
        r = self.conn.execute("SELECT " + self._CS_COLS + " FROM copy_settings WHERE follower_chat=?",
                              (str(follower),)).fetchone()
        if not r:
            return {"follower_chat": str(follower), "min_buy_usdc": 0.0, "max_open": 0,
                    "sizing": "flat", "flat_usdc": 25.0, "mirror_sells": True, "tp_pct": 0.0,
                    "sl_pct": 0.0, "trailing_pct": 0.0, "dump_guard": True, "updated_ts": 0}
        return {"follower_chat": r[0], "min_buy_usdc": float(r[1] or 0), "max_open": int(r[2] or 0),
                "sizing": r[3] or "flat",
                "flat_usdc": float(r[4] if r[4] is not None else 25.0),
                "mirror_sells": bool(r[5]), "tp_pct": float(r[6] or 0), "sl_pct": float(r[7] or 0),
                "trailing_pct": float(r[8] or 0), "dump_guard": bool(r[9]), "updated_ts": int(r[10] or 0)}

    def set_copy_settings(self, follower, **kw) -> None:
        cur = self.get_copy_settings(follower)

        def _pick(key, default):
            return kw[key] if key in kw and kw[key] is not None else cur.get(key, default)

        f = {"min_buy_usdc": float(_pick("min_buy_usdc", 0.0)),
             "max_open": int(_pick("max_open", 0)),
             "sizing": str(_pick("sizing", "flat")),
             "flat_usdc": float(_pick("flat_usdc", 25.0)),
             "mirror_sells": 1 if _pick("mirror_sells", True) else 0,
             "tp_pct": float(_pick("tp_pct", 0.0)),
             "sl_pct": float(_pick("sl_pct", 0.0)),
             "trailing_pct": float(_pick("trailing_pct", 0.0)),
             "dump_guard": 1 if _pick("dump_guard", True) else 0}
        self.conn.execute(
            "INSERT INTO copy_settings(follower_chat,min_buy_usdc,max_open,sizing,flat_usdc,"
            "mirror_sells,tp_pct,sl_pct,trailing_pct,dump_guard,updated_ts) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(follower_chat) DO UPDATE SET "
            "min_buy_usdc=excluded.min_buy_usdc, max_open=excluded.max_open, sizing=excluded.sizing, "
            "flat_usdc=excluded.flat_usdc, mirror_sells=excluded.mirror_sells, tp_pct=excluded.tp_pct, "
            "sl_pct=excluded.sl_pct, trailing_pct=excluded.trailing_pct, "
            "dump_guard=excluded.dump_guard, updated_ts=excluded.updated_ts",
            (str(follower), f["min_buy_usdc"], f["max_open"], f["sizing"], f["flat_usdc"],
             f["mirror_sells"], f["tp_pct"], f["sl_pct"], f["trailing_pct"], f["dump_guard"],
             int(time.time())))
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # --- persistent dedup (delivered alerts) ---
    def is_delivered(self, chat_id, token, kind, block) -> bool:
        cur = self.conn.execute(
            "SELECT 1 FROM delivered WHERE chat_id=? AND token=? AND kind=? AND block=? LIMIT 1",
            (str(chat_id), token, kind, int(block or 0)))
        return cur.fetchone() is not None

    def mark_delivered(self, chat_id, token, kind, block) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO delivered(chat_id,token,kind,block) VALUES(?,?,?,?)",
            (str(chat_id), token, kind, int(block or 0)))
        self.conn.commit()

    def get_state(self, key: str, default=None):
        cur = self.conn.execute("SELECT value FROM state WHERE key=?", (key,))
        row = cur.fetchone()
        return row[0] if row else default

    def set_state(self, key: str, value) -> None:
        self.conn.execute(
            "INSERT INTO state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)))
        self.conn.commit()

    # --- alert queue (no alert is ever discarded by the per-cycle cap) ---
    def enqueue_alert(self, a: dict) -> None:
        import json as _json
        self.conn.execute(
            "INSERT OR IGNORE INTO aqueue(token,kind,block,severity,message,context) VALUES(?,?,?,?,?,?)",
            (a.get("token"), a.get("kind"), int(a.get("block") or 0), a.get("severity"),
             a.get("message"), _json.dumps(a.get("context") or {})))
        self.conn.commit()

    def enqueue_alert_many(self, alerts: list) -> None:
        import json as _json
        rows = [(a.get("token"), a.get("kind"), int(a.get("block") or 0), a.get("severity"),
                 a.get("message"), _json.dumps(a.get("context") or {})) for a in alerts]
        if rows:
            self.conn.executemany(
                "INSERT OR IGNORE INTO aqueue(token,kind,block,severity,message,context) "
                "VALUES(?,?,?,?,?,?)", rows)
            self.conn.commit()

    def queue_size(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM aqueue").fetchone()[0])

    def dequeue(self, limit: int = 30) -> list:
        import json as _json
        cur = self.conn.execute(
            "SELECT token,kind,block,severity,message,context FROM aqueue "
            "ORDER BY (kind IN ('dev_sell','compound')) DESC, block, rowid LIMIT ?", (int(limit),))
        out = []
        for token, kind, block, severity, message, context in cur.fetchall():
            out.append({"token": token, "kind": kind, "block": block, "severity": severity,
                        "message": message, "context": _json.loads(context or "{}")})
        return out

    def remove_from_queue(self, token, kind, block) -> None:
        self.conn.execute("DELETE FROM aqueue WHERE token=? AND kind=? AND block=?",
                          (token, kind, int(block or 0)))
        self.conn.commit()
