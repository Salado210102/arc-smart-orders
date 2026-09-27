"""SQLite storage layer (repository). Idempotent inserts, cursor, health.

Schema is deliberately portable to Postgres later (TEXT/BIGINT, no SQLite-only types).
"""
from __future__ import annotations

import sqlite3
import time
from contextlib import closing

from .models import DevBuyRow, LaunchpadEventRow, SwapRow, TokenRow

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS tokens (
        address TEXT PRIMARY KEY,
        symbol TEXT, name TEXT, creator TEXT, launchpad TEXT,
        created_ts INTEGER, pool_id TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS swaps (
        tx_hash TEXT NOT NULL, log_index INTEGER NOT NULL,
        block_number INTEGER, ts INTEGER, token TEXT, wallet TEXT, side TEXT,
        amount_in TEXT, amount_out TEXT, price_implied TEXT, dex TEXT, pool TEXT,
        PRIMARY KEY (tx_hash, log_index)
    )""",
    """CREATE TABLE IF NOT EXISTS dev_buys (
        tx_hash TEXT NOT NULL, log_index INTEGER NOT NULL,
        token TEXT, creator_wallet TEXT, amount TEXT, ts INTEGER,
        PRIMARY KEY (tx_hash, log_index)
    )""",
    """CREATE TABLE IF NOT EXISTS launchpad_events (
        tx_hash TEXT NOT NULL, log_index INTEGER NOT NULL,
        launchpad TEXT, event_name TEXT, topic0 TEXT, token TEXT, address TEXT,
        block_number INTEGER, ts INTEGER, topics TEXT, data TEXT,
        PRIMARY KEY (tx_hash, log_index)
    )""",
    """CREATE TABLE IF NOT EXISTS wallets (
        address TEXT PRIMARY KEY, first_seen_ts INTEGER, trade_count INTEGER NOT NULL DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS health (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts INTEGER, events_last_window INTEGER, last_block INTEGER, lag_blocks INTEGER, source TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)""",
    """CREATE TABLE IF NOT EXISTS pools_v4 (
        pool_id TEXT PRIMARY KEY,
        currency0 TEXT, currency1 TEXT,
        fee INTEGER, tick_spacing INTEGER, hooks TEXT,
        sqrt_price_x96 TEXT, tick INTEGER,
        block_number INTEGER, ts INTEGER
    )""",
    """CREATE TABLE IF NOT EXISTS token_transfers (
        tx_hash TEXT NOT NULL, log_index INTEGER NOT NULL, token TEXT, from_addr TEXT, to_addr TEXT,
        value TEXT, block_number INTEGER, ts INTEGER, PRIMARY KEY (tx_hash, log_index)
    )""",
    """CREATE TABLE IF NOT EXISTS v4_events (
        kind TEXT, tx_hash TEXT NOT NULL, log_index INTEGER NOT NULL, pool_id TEXT, sender TEXT,
        amount0 TEXT, amount1 TEXT, block_number INTEGER, ts INTEGER, PRIMARY KEY (tx_hash, log_index)
    )""",
    """CREATE TABLE IF NOT EXISTS v4_liquidity (
        tx_hash TEXT NOT NULL, log_index INTEGER NOT NULL, pool_id TEXT, sender TEXT,
        tick_lower INTEGER, tick_upper INTEGER, liquidity_delta TEXT, salt TEXT,
        block_number INTEGER, ts INTEGER, PRIMARY KEY (tx_hash, log_index)
    )""",
    """CREATE TABLE IF NOT EXISTS tx_senders (
        tx_hash TEXT PRIMARY KEY, from_addr TEXT, to_addr TEXT, block_number INTEGER
    )""",
    """CREATE TABLE IF NOT EXISTS resolved_blocks (
        block_number INTEGER PRIMARY KEY
    )""",
    """CREATE TABLE IF NOT EXISTS wallet_scores (
        wallet TEXT PRIMARY KEY, score REAL, version TEXT, trades INTEGER,
        win_rate REAL, avg_mult REAL, pnl REAL, variance REAL, entry_pct REAL,
        confidence TEXT, computed_at INTEGER
    )""",
    """CREATE TABLE IF NOT EXISTS data_gaps (
        job TEXT NOT NULL, from_block INTEGER NOT NULL, to_block INTEGER NOT NULL,
        reason TEXT NOT NULL, attempts INTEGER, detected_at INTEGER,
        PRIMARY KEY (job, from_block, to_block, reason)
    )""",
    """DROP VIEW IF EXISTS dev_buys_inferred""",
    # Inferred dev buys via ERC-20 Transfer to the creator of the launched token within a
    # window (default 24h). NEVER mixed with confirmed events. Parameterized via method.
    """CREATE VIEW dev_buys_inferred AS
        SELECT tr.tx_hash AS tx_hash, tr.log_index AS log_index, tr.token AS token,
               tr.to_addr AS creator_wallet, tr.value AS amount, tr.ts AS transfer_ts,
               t.created_ts AS token_created_ts, 1 AS is_inferred,
               'inferred:transfer_to_creator_within_86400s' AS reason
        FROM token_transfers tr
        JOIN tokens t ON lower(t.address) = lower(tr.token) AND lower(t.creator) = lower(tr.to_addr)
        WHERE t.created_ts IS NOT NULL AND tr.ts IS NOT NULL
          AND tr.ts >= t.created_ts AND tr.ts <= t.created_ts + 86400""",
]


class Storage:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")

    def migrate(self) -> None:
        for stmt in SCHEMA:
            self._conn.execute(stmt)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def truncate_all(self) -> None:
        for t in ("tokens", "swaps", "dev_buys", "launchpad_events", "wallets", "pools_v4",
                  "token_transfers", "v4_events", "v4_liquidity", "tx_senders", "resolved_blocks",
                  "wallet_scores", "health", "meta", "data_gaps"):
            self._conn.execute(f"DELETE FROM {t}")
        self._conn.commit()

    def insert_gap(self, job: str, from_block: int, to_block: int, reason: str, attempts: int, ts: int) -> bool:
        cur = self._conn.execute(
            "INSERT OR IGNORE INTO data_gaps(job,from_block,to_block,reason,attempts,detected_at) "
            "VALUES(?,?,?,?,?,?)", (job, from_block, to_block, reason, attempts, ts))
        self._conn.commit()
        return cur.rowcount > 0

    def list_gaps(self, job: str):
        with closing(self._conn.execute(
            "SELECT * FROM data_gaps WHERE job=? ORDER BY from_block", (job,))) as cur:
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    # --- cursor ---
    def get_cursor(self, default: int) -> int:
        with closing(self._conn.execute("SELECT value FROM meta WHERE key='cursor_block'")) as cur:
            row = cur.fetchone()
        return int(row[0]) if row else default

    def set_cursor(self, block: int) -> None:
        self.set_meta("cursor_block", str(block))

    def get_meta(self, key: str, default=None):
        with closing(self._conn.execute("SELECT value FROM meta WHERE key=?", (key,))) as cur:
            row = cur.fetchone()
        return row[0] if row else default

    def set_meta(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self._conn.commit()

    # --- batch inserts (single commit; SQLite uses one transaction) ---
    def _batch(self, sql: str, rows: list) -> int:
        n = 0
        for params in rows:
            cur = self._conn.execute(sql, params)
            n += cur.rowcount if cur.rowcount > 0 else 0
        self._conn.commit()
        return n

    def insert_swaps(self, rows: list) -> int:
        return self._batch(
            "INSERT OR IGNORE INTO swaps(tx_hash,log_index,block_number,ts,token,wallet,side,"
            "amount_in,amount_out,price_implied,dex,pool) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            [(r.tx_hash.lower(), r.log_index, r.block_number, r.ts, r.token, r.wallet, r.side,
              r.amount_in, r.amount_out, r.price_implied, r.dex, r.pool) for r in rows],
        )

    def insert_pool_v4_rows(self, rows: list) -> int:
        return self._batch(
            "INSERT OR IGNORE INTO pools_v4(pool_id,currency0,currency1,fee,tick_spacing,hooks,"
            "sqrt_price_x96,tick,block_number,ts) VALUES(?,?,?,?,?,?,?,?,?,?)",
            [(r.pool_id.lower(), r.currency0, r.currency1, r.fee, r.tick_spacing, r.hooks,
              r.sqrt_price_x96, r.tick, r.block_number, r.ts) for r in rows],
        )

    def insert_transfers(self, rows: list) -> int:
        return self._batch(
            "INSERT OR IGNORE INTO token_transfers(tx_hash,log_index,token,from_addr,to_addr,value,"
            "block_number,ts) VALUES(?,?,?,?,?,?,?,?)",
            [(r.tx_hash.lower(), r.log_index, r.token.lower(), r.from_addr.lower(), r.to_addr.lower(),
              r.value, r.block_number, r.ts) for r in rows],
        )

    def insert_v4_events(self, rows: list) -> int:
        return self._batch(
            "INSERT OR IGNORE INTO v4_events(kind,tx_hash,log_index,pool_id,sender,amount0,amount1,"
            "block_number,ts) VALUES(?,?,?,?,?,?,?,?,?)",
            [(r.kind, r.tx_hash.lower(), r.log_index, r.pool_id, r.sender, r.amount0, r.amount1,
              r.block_number, r.ts) for r in rows],
        )

    def insert_v4_liquidity_rows(self, rows: list) -> int:
        return self._batch(
            "INSERT OR IGNORE INTO v4_liquidity(tx_hash,log_index,pool_id,sender,tick_lower,"
            "tick_upper,liquidity_delta,salt,block_number,ts) VALUES(?,?,?,?,?,?,?,?,?,?)",
            [(r.tx_hash.lower(), r.log_index, r.pool_id, r.sender, r.tick_lower, r.tick_upper,
              r.liquidity_delta, r.salt, r.block_number, r.ts) for r in rows],
        )

    # --- idempotent inserts (True == newly inserted) ---
    def insert_swap(self, r: SwapRow) -> bool:
        cur = self._conn.execute(
            "INSERT OR IGNORE INTO swaps(tx_hash,log_index,block_number,ts,token,wallet,side,"
            "amount_in,amount_out,price_implied,dex,pool) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (r.tx_hash.lower(), r.log_index, r.block_number, r.ts, r.token, r.wallet, r.side,
             r.amount_in, r.amount_out, r.price_implied, r.dex, r.pool),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def insert_token(self, r: TokenRow) -> bool:
        cur = self._conn.execute(
            "INSERT OR IGNORE INTO tokens(address,symbol,name,creator,launchpad,created_ts,pool_id) "
            "VALUES(?,?,?,?,?,?,?)",
            (r.address.lower(), r.symbol, r.name, r.creator, r.launchpad, r.created_ts, r.pool_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def insert_dev_buy(self, r: DevBuyRow) -> bool:
        cur = self._conn.execute(
            "INSERT OR IGNORE INTO dev_buys(tx_hash,log_index,token,creator_wallet,amount,ts) "
            "VALUES(?,?,?,?,?,?)",
            (r.tx_hash.lower(), r.log_index, r.token, r.creator_wallet, r.amount, r.ts),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def insert_launchpad_event(self, r: LaunchpadEventRow) -> bool:
        cur = self._conn.execute(
            "INSERT OR IGNORE INTO launchpad_events(tx_hash,log_index,launchpad,event_name,topic0,"
            "token,address,block_number,ts,topics,data) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (r.tx_hash.lower(), r.log_index, r.launchpad, r.event_name, r.topic0, r.token,
             r.address.lower(), r.block_number, r.ts, ",".join(r.topics), r.data),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def upsert_wallet(self, address: str, ts: int | None, trade_delta: int = 1) -> bool:
        cur = self._conn.execute(
            "INSERT INTO wallets(address,first_seen_ts,trade_count) VALUES(?,?,?) "
            "ON CONFLICT(address) DO UPDATE SET trade_count=wallets.trade_count+excluded.trade_count",
            (address.lower(), ts, trade_delta),
        )
        self._conn.commit()
        return cur.rowcount > 0

    # --- health / counts ---
    def record_health(self, events_last_window: int, last_block: int, lag_blocks: int, source: str) -> None:
        self._conn.execute(
            "INSERT INTO health(ts,events_last_window,last_block,lag_blocks,source) VALUES(?,?,?,?,?)",
            (int(time.time()), events_last_window, last_block, lag_blocks, source),
        )
        self._conn.commit()

    def counts(self) -> dict[str, int]:
        out = {}
        for t in ("tokens", "swaps", "dev_buys", "launchpad_events", "wallets", "pools_v4", "token_transfers", "v4_events", "v4_liquidity", "tx_senders", "resolved_blocks", "data_gaps"):
            with closing(self._conn.execute(f"SELECT COUNT(*) FROM {t}")) as cur:
                out[t] = int(cur.fetchone()[0])
        with closing(self._conn.execute("SELECT COUNT(*) FROM dev_buys_inferred")) as cur:
            out["dev_buys_inferred"] = int(cur.fetchone()[0])
        return out

    # --- tx sender resolution (tx.from for v4 swaps) ---
    def distinct_swap_tx_hashes(self) -> list[str]:
        with closing(self._conn.execute(
                "SELECT DISTINCT tx_hash FROM swaps WHERE tx_hash IS NOT NULL")) as cur:
            return [r[0] for r in cur.fetchall()]

    def resolved_tx_hashes(self) -> set[str]:
        with closing(self._conn.execute("SELECT tx_hash FROM tx_senders")) as cur:
            return {r[0] for r in cur.fetchall()}

    def insert_tx_senders(self, rows: list) -> int:
        return self._batch(
            "INSERT OR IGNORE INTO tx_senders(tx_hash,from_addr,to_addr,block_number) VALUES(?,?,?,?)",
            [(tx.lower(), (fr or "").lower() or None, (to or "").lower() or None, blk)
             for tx, fr, to, blk in rows],
        )

    def distinct_swap_blocks(self) -> list[int]:
        with closing(self._conn.execute(
                "SELECT DISTINCT block_number FROM swaps WHERE block_number IS NOT NULL "
                "ORDER BY block_number")) as cur:
            return [int(r[0]) for r in cur.fetchall()]

    def distinct_swap_blocks_range(self, lo: int, hi: int) -> list[int]:
        with closing(self._conn.execute(
                "SELECT DISTINCT s.block_number FROM swaps s "
                "WHERE s.block_number >= ? AND s.block_number <= ? "
                "AND NOT EXISTS (SELECT 1 FROM resolved_blocks r WHERE r.block_number = s.block_number) "
                "ORDER BY s.block_number", (int(lo), int(hi)))) as cur:
            return [int(r[0]) for r in cur.fetchall()]

    def resolved_blocks(self) -> set[int]:
        with closing(self._conn.execute("SELECT block_number FROM resolved_blocks")) as cur:
            return {int(r[0]) for r in cur.fetchall()}

    def mark_blocks_resolved(self, blocks: list[int]) -> int:
        return self._batch("INSERT OR IGNORE INTO resolved_blocks(block_number) VALUES(?)",
                           [(int(b),) for b in blocks])

    # --- wallet scores ---
    def save_wallet_scores(self, rows: list[dict], computed_at: int | None = None) -> int:
        import time as _t
        ts = int(computed_at if computed_at is not None else _t.time())
        return self._batch(
            "INSERT INTO wallet_scores(wallet,score,version,trades,win_rate,avg_mult,pnl,variance,"
            "entry_pct,confidence,computed_at) VALUES(?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(wallet) DO UPDATE SET score=excluded.score, version=excluded.version, "
            "trades=excluded.trades, win_rate=excluded.win_rate, avg_mult=excluded.avg_mult, "
            "pnl=excluded.pnl, variance=excluded.variance, entry_pct=excluded.entry_pct, "
            "confidence=excluded.confidence, computed_at=excluded.computed_at",
            [(str(r.get("wallet", "")).lower(), r.get("score"), r.get("version"), r.get("trades"), r.get("win_rate"),
              r.get("avg_mult"), r.get("pnl"), r.get("variance"), r.get("entry_pct"),
              r.get("confidence"), ts) for r in rows],
        )

    def load_wallet_scores(self, min_score: float = 0.0, min_trades: int = 0) -> list[dict]:
        with closing(self._conn.execute(
                "SELECT wallet,score,version,trades,win_rate,avg_mult,pnl,variance,entry_pct,confidence "
                "FROM wallet_scores WHERE score>=? AND trades>=? ORDER BY score DESC",
                (float(min_score), int(min_trades)))) as cur:
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def insert_v4_event(self, r) -> bool:
        cur = self._conn.execute(
            "INSERT OR IGNORE INTO v4_events(kind,tx_hash,log_index,pool_id,sender,amount0,amount1,"
            "block_number,ts) VALUES(?,?,?,?,?,?,?,?,?)",
            (r.kind, r.tx_hash.lower(), r.log_index, r.pool_id, r.sender, r.amount0, r.amount1,
             r.block_number, r.ts),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def insert_token_transfer(self, r) -> bool:
        cur = self._conn.execute(
            "INSERT OR IGNORE INTO token_transfers(tx_hash,log_index,token,from_addr,to_addr,value,"
            "block_number,ts) VALUES(?,?,?,?,?,?,?,?)",
            (r.tx_hash.lower(), r.log_index, r.token.lower(), r.from_addr.lower(), r.to_addr.lower(),
             r.value, r.block_number, r.ts),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def insert_pool_v4(self, r) -> bool:
        cur = self._conn.execute(
            "INSERT OR IGNORE INTO pools_v4(pool_id,currency0,currency1,fee,tick_spacing,hooks,"
            "sqrt_price_x96,tick,block_number,ts) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (r.pool_id.lower(), r.currency0, r.currency1, r.fee, r.tick_spacing, r.hooks,
             r.sqrt_price_x96, r.tick, r.block_number, r.ts),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def get_pool_v4(self, pool_id: str):
        with closing(self._conn.execute(
            "SELECT * FROM pools_v4 WHERE pool_id=?", (pool_id.lower(),)
        )) as cur:
            cols = [d[0] for d in cur.description]
            row = cur.fetchone()
            return dict(zip(cols, row)) if row else None


    def query_dev_buys_inferred(self, window_seconds: int = 86400, limit: int = 50) -> list[dict]:
        """Inferred dev buys (configurable window), always is_inferred=True.

        Rule: ERC-20 Transfer to the token's creator of the launched token, within
        `window_seconds` after token creation.
        """
        sql = (
            "SELECT tr.tx_hash, tr.log_index, tr.token, tr.to_addr AS creator_wallet, tr.value AS amount, "
            "tr.ts AS transfer_ts, t.created_ts AS token_created_ts, "
            "1 AS is_inferred, ? AS window_seconds "
            "FROM token_transfers tr "
            "JOIN tokens t ON lower(t.address) = lower(tr.token) AND lower(t.creator) = lower(tr.to_addr) "
            "WHERE t.created_ts IS NOT NULL AND tr.ts IS NOT NULL "
            "AND tr.ts >= t.created_ts AND tr.ts <= t.created_ts + ? "
            "ORDER BY tr.ts LIMIT ?"
        )
        with closing(self._conn.execute(sql, (window_seconds, window_seconds, int(limit)))) as cur:
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def sample(self, table: str, limit: int = 3) -> list[dict]:
        with closing(self._conn.execute(f"SELECT * FROM {table} LIMIT {int(limit)}")) as cur:
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
