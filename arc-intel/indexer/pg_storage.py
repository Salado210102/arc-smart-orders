"""PostgreSQL storage: connection pool + batch (execute_values) inserts.

Same logical schema as the SQLite Storage, plus a resumable checkpoint in `meta`.
Requires psycopg2-binary. Designed for concurrent writers (indexer + backfill).
"""
from __future__ import annotations

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

PG_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS tokens (
        address TEXT PRIMARY KEY, symbol TEXT, name TEXT, creator TEXT, launchpad TEXT,
        created_ts BIGINT, pool_id TEXT)""",
    """CREATE TABLE IF NOT EXISTS swaps (
        tx_hash TEXT NOT NULL, log_index INTEGER NOT NULL, block_number BIGINT, ts BIGINT,
        token TEXT, wallet TEXT, side TEXT, amount_in TEXT, amount_out TEXT, price_implied TEXT,
        dex TEXT, pool TEXT, trader TEXT, PRIMARY KEY (tx_hash, log_index))""",
    """CREATE TABLE IF NOT EXISTS dev_buys (
        tx_hash TEXT NOT NULL, log_index INTEGER NOT NULL, token TEXT, creator_wallet TEXT,
        amount TEXT, ts BIGINT, PRIMARY KEY (tx_hash, log_index))""",
    """CREATE TABLE IF NOT EXISTS launchpad_events (
        tx_hash TEXT NOT NULL, log_index INTEGER NOT NULL, launchpad TEXT, event_name TEXT,
        topic0 TEXT, token TEXT, address TEXT, block_number BIGINT, ts BIGINT, topics TEXT, data TEXT,
        PRIMARY KEY (tx_hash, log_index))""",
    """CREATE TABLE IF NOT EXISTS wallets (
        address TEXT PRIMARY KEY, first_seen_ts BIGINT, trade_count INTEGER NOT NULL DEFAULT 0)""",
    """CREATE TABLE IF NOT EXISTS pools_v4 (
        pool_id TEXT PRIMARY KEY, currency0 TEXT, currency1 TEXT, fee INTEGER, tick_spacing INTEGER,
        hooks TEXT, sqrt_price_x96 TEXT, tick BIGINT, block_number BIGINT, ts BIGINT)""",
    """CREATE TABLE IF NOT EXISTS token_transfers (
        tx_hash TEXT NOT NULL, log_index INTEGER NOT NULL, token TEXT, from_addr TEXT, to_addr TEXT,
        value TEXT, block_number BIGINT, ts BIGINT, PRIMARY KEY (tx_hash, log_index))""",
    """CREATE TABLE IF NOT EXISTS v4_events (
        kind TEXT, tx_hash TEXT NOT NULL, log_index INTEGER NOT NULL, pool_id TEXT, sender TEXT,
        amount0 TEXT, amount1 TEXT, block_number BIGINT, ts BIGINT, PRIMARY KEY (tx_hash, log_index))""",
    """CREATE TABLE IF NOT EXISTS v4_liquidity (
        tx_hash TEXT NOT NULL, log_index INTEGER NOT NULL, pool_id TEXT, sender TEXT,
        tick_lower INTEGER, tick_upper INTEGER, liquidity_delta TEXT, salt TEXT,
        block_number BIGINT, ts BIGINT, PRIMARY KEY (tx_hash, log_index))""",
    """CREATE TABLE IF NOT EXISTS tx_senders (
        tx_hash TEXT PRIMARY KEY, from_addr TEXT, to_addr TEXT, block_number BIGINT)""",
    """CREATE TABLE IF NOT EXISTS resolved_blocks (
        block_number BIGINT PRIMARY KEY)""",
    """CREATE TABLE IF NOT EXISTS wallet_scores (
        wallet TEXT PRIMARY KEY, score DOUBLE PRECISION, version TEXT, trades INTEGER,
        win_rate DOUBLE PRECISION, avg_mult DOUBLE PRECISION, pnl DOUBLE PRECISION,
        variance DOUBLE PRECISION, entry_pct DOUBLE PRECISION, confidence TEXT, computed_at BIGINT)""",
    """CREATE TABLE IF NOT EXISTS launchpad_rank (
        run_ts BIGINT NOT NULL, impl TEXT NOT NULL, hooks INTEGER, swaps BIGINT,
        volume DOUBLE PRECISION, sample_hook TEXT, PRIMARY KEY (run_ts, impl))""",
    """CREATE TABLE IF NOT EXISTS data_gaps (
        job TEXT NOT NULL, from_block BIGINT NOT NULL, to_block BIGINT NOT NULL, reason TEXT NOT NULL,
        attempts INTEGER, detected_at BIGINT, PRIMARY KEY (job, from_block, to_block, reason))""",
    """CREATE TABLE IF NOT EXISTS health (
        id SERIAL PRIMARY KEY, ts BIGINT, events_last_window INTEGER, last_block BIGINT,
        lag_blocks BIGINT, source TEXT)""",
    """CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)""",
    """DROP VIEW IF EXISTS dev_buys_inferred""",
    """CREATE VIEW dev_buys_inferred AS
        SELECT tr.tx_hash, tr.log_index, tr.token, tr.to_addr AS creator_wallet, tr.value AS amount,
               tr.ts AS transfer_ts, t.created_ts AS token_created_ts, TRUE AS is_inferred,
               'inferred:transfer_to_creator_within_86400s' AS reason
        FROM token_transfers tr
        JOIN tokens t ON lower(t.address)=lower(tr.token) AND lower(t.creator)=lower(tr.to_addr)
        WHERE t.created_ts IS NOT NULL AND tr.ts IS NOT NULL
          AND tr.ts >= t.created_ts AND tr.ts <= t.created_ts + 86400""",
]

SQL = {
    "swaps": ("INSERT INTO swaps(tx_hash,log_index,block_number,ts,token,wallet,side,amount_in,"
              "amount_out,price_implied,dex,pool) VALUES %s ON CONFLICT DO NOTHING"),
    "pools_v4": ("INSERT INTO pools_v4(pool_id,currency0,currency1,fee,tick_spacing,hooks,"
                 "sqrt_price_x96,tick,block_number,ts) VALUES %s ON CONFLICT DO NOTHING"),
    "token_transfers": ("INSERT INTO token_transfers(tx_hash,log_index,token,from_addr,to_addr,value,"
                        "block_number,ts) VALUES %s ON CONFLICT DO NOTHING"),
    "v4_events": ("INSERT INTO v4_events(kind,tx_hash,log_index,pool_id,sender,amount0,amount1,"
                  "block_number,ts) VALUES %s ON CONFLICT DO NOTHING"),
    "v4_liquidity": ("INSERT INTO v4_liquidity(tx_hash,log_index,pool_id,sender,tick_lower,"
                     "tick_upper,liquidity_delta,salt,block_number,ts) VALUES %s "
                     "ON CONFLICT DO NOTHING"),
    "tx_senders": ("INSERT INTO tx_senders(tx_hash,from_addr,to_addr,block_number) "
                   "VALUES %s ON CONFLICT DO NOTHING"),
    "resolved_blocks": ("INSERT INTO resolved_blocks(block_number) VALUES %s ON CONFLICT DO NOTHING"),
}


class PostgresStorage:
    def __init__(self, dsn: str, minconn: int = 1, maxconn: int = 8):
        self.pool = ThreadedConnectionPool(minconn, maxconn, dsn)
        self.dsn = dsn

    # --- internal ---
    def _exec(self, sql, params=None):
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params or ())
                conn.commit()
                return cur
        finally:
            self.pool.putconn(conn)

    def _batch(self, key: str, rows: list) -> int:
        if not rows:
            return 0
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                psycopg2.extras.execute_values(cur, SQL[key], rows, page_size=max(1, len(rows)))
                n = cur.rowcount
            conn.commit()
            return n
        finally:
            self.pool.putconn(conn)

    def migrate(self) -> None:
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                for stmt in PG_SCHEMA:
                    cur.execute(stmt)
                cur.execute("ALTER TABLE swaps ADD COLUMN IF NOT EXISTS trader TEXT")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_tx_senders_block ON tx_senders(block_number)")
                cur.execute("SELECT to_regclass('public.legs')")
                if cur.fetchone()[0] is not None:
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_legs_token_block ON legs(token, block)")
            conn.commit()
        finally:
            self.pool.putconn(conn)

    def materialize_traders_range(self, lo: int, hi: int) -> int:
        """Materialize trader for swaps in [lo, hi) using a range-bounded hash join."""
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SET work_mem='128MB'")
                cur.execute("UPDATE swaps s SET trader = ts.from_addr FROM tx_senders ts "
                            "WHERE s.tx_hash = ts.tx_hash AND s.trader IS NULL "
                            "AND s.block_number >= %s AND s.block_number < %s "
                            "AND ts.block_number >= %s AND ts.block_number < %s", (lo, hi, lo, hi))
                n = cur.rowcount
            conn.commit()
            return n
        finally:
            self.pool.putconn(conn)

    def materialize_traders_batched(self, lo: int, hi: int, step: int = 50000, on_progress=None) -> int:
        total = 0
        b = lo
        while b < hi:
            e = min(b + step, hi)
            total += self.materialize_traders_range(b, e)
            if on_progress:
                on_progress(b, e, total)
            b = e
        return total

    def materialize_traders(self) -> int:
        """Copy tx_senders.from_addr into swaps.trader (resolved tx.from materialization)."""
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("UPDATE swaps s SET trader = ts.from_addr FROM tx_senders ts "
                            "WHERE s.tx_hash = ts.tx_hash AND s.trader IS NULL")
                n = cur.rowcount
                cur.execute("ANALYZE swaps")
            conn.commit()
            return n
        finally:
            self.pool.putconn(conn)

    def unresolved_trader_count(self) -> int:
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM swaps WHERE trader IS NULL")
                return int(cur.fetchone()[0])
        finally:
            self.pool.putconn(conn)

    def save_launchpad_rank(self, run_ts: int, rows: list) -> int:
        if not rows:
            return 0
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                psycopg2.extras.execute_values(
                    cur,
                    "INSERT INTO launchpad_rank(run_ts,impl,hooks,swaps,volume,sample_hook) VALUES %s "
                    "ON CONFLICT DO NOTHING",
                    [(int(run_ts), r["impl"], int(r["hooks"]), int(r["swaps"]), float(r["volume"]),
                      r["sample_hook"]) for r in rows],
                    page_size=max(1, len(rows)))
                n = cur.rowcount
            conn.commit()
            return n
        finally:
            self.pool.putconn(conn)

    def swap_block_bounds(self):
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT MIN(block_number), MAX(block_number) FROM swaps")
                r = cur.fetchone()
                return (int(r[0]), int(r[1])) if r and r[0] is not None else None
        finally:
            self.pool.putconn(conn)

    def create_legs_table(self) -> None:
        self._exec("DROP TABLE IF EXISTS legs")
        self._exec("CREATE TABLE legs (wallet TEXT, token TEXT, pool TEXT, block BIGINT, "
                   "log_index INTEGER, side TEXT, token_qty DOUBLE PRECISION, "
                   "stable_value DOUBLE PRECISION, price DOUBLE PRECISION)")
        self._exec("CREATE INDEX idx_legs_wpb ON legs(wallet, pool, block)")
        self._exec("CREATE INDEX idx_legs_block ON legs(block)")
        self._exec("CREATE INDEX IF NOT EXISTS idx_legs_token_block ON legs(token, block)")

    def insert_legs(self, rows: list) -> int:
        if not rows:
            return 0
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                psycopg2.extras.execute_values(
                    cur,
                    "INSERT INTO legs(wallet,token,pool,block,log_index,side,token_qty,"
                    "stable_value,price) VALUES %s", rows, page_size=5000)
                n = cur.rowcount
            conn.commit()
            return n
        finally:
            self.pool.putconn(conn)

    def save_wallet_scores(self, rows: list[dict], computed_at: int | None = None) -> int:
        import time as _t
        ts = int(computed_at if computed_at is not None else _t.time())
        if not rows:
            return 0
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                psycopg2.extras.execute_values(
                    cur,
                    "INSERT INTO wallet_scores(wallet,score,version,trades,win_rate,avg_mult,pnl,"
                    "variance,entry_pct,confidence,computed_at) VALUES %s "
                    "ON CONFLICT(wallet) DO UPDATE SET score=EXCLUDED.score, version=EXCLUDED.version, "
                    "trades=EXCLUDED.trades, win_rate=EXCLUDED.win_rate, avg_mult=EXCLUDED.avg_mult, "
                    "pnl=EXCLUDED.pnl, variance=EXCLUDED.variance, entry_pct=EXCLUDED.entry_pct, "
                    "confidence=EXCLUDED.confidence, computed_at=EXCLUDED.computed_at",
                    [(str(r.get("wallet", "")).lower(), r.get("score"), r.get("version"), r.get("trades"),
                      r.get("win_rate"), r.get("avg_mult"), r.get("pnl"), r.get("variance"),
                      r.get("entry_pct"), r.get("confidence"), ts) for r in rows],
                    page_size=max(1, len(rows)))
                n = cur.rowcount
            conn.commit()
            return n
        finally:
            self.pool.putconn(conn)

    def load_wallet_scores(self, min_score: float = 0.0, min_trades: int = 0) -> list[dict]:
        conn = self.pool.getconn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT wallet,score,version,trades,win_rate,avg_mult,pnl,variance,"
                            "entry_pct,confidence FROM wallet_scores WHERE score>=%s AND trades>=%s "
                            "ORDER BY score DESC", (float(min_score), int(min_trades)))
                return [dict(r) for r in cur.fetchall()]
        finally:
            self.pool.putconn(conn)

    def close(self) -> None:
        self.pool.closeall()

    def truncate_all(self) -> None:
        self._exec("TRUNCATE tokens, swaps, dev_buys, launchpad_events, wallets, pools_v4, "
                   "token_transfers, v4_events, v4_liquidity, tx_senders, resolved_blocks, "
                   "wallet_scores, health, meta, data_gaps")

    def insert_gap(self, job: str, from_block: int, to_block: int, reason: str, attempts: int, ts: int) -> bool:
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO data_gaps(job,from_block,to_block,reason,attempts,detected_at) "
                            "VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                            (job, from_block, to_block, reason, attempts, ts))
                n = cur.rowcount
            conn.commit()
            return n > 0
        finally:
            self.pool.putconn(conn)

    def list_gaps(self, job: str):
        conn = self.pool.getconn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM data_gaps WHERE job=%s ORDER BY from_block", (job,))
                return [dict(r) for r in cur.fetchall()]
        finally:
            self.pool.putconn(conn)

    # --- cursor / meta ---
    def get_cursor(self, default: int) -> int:
        v = self.get_meta("cursor_block")
        return int(v) if v is not None else default

    def set_cursor(self, block: int) -> None:
        self.set_meta("cursor_block", str(block))

    def get_meta(self, key: str, default=None):
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT value FROM meta WHERE key=%s", (key,))
                row = cur.fetchone()
            return row[0] if row else default
        finally:
            self.pool.putconn(conn)

    def set_meta(self, key: str, value: str) -> None:
        self._exec("INSERT INTO meta(key,value) VALUES(%s,%s) "
                   "ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value", (key, value))

    # --- single-row (real-time path) ---
    def insert_swap(self, r) -> bool:
        return self._batch("swaps", [(r.tx_hash.lower(), r.log_index, r.block_number, r.ts, r.token,
                                      r.wallet, r.side, r.amount_in, r.amount_out, r.price_implied,
                                      r.dex, r.pool)]) > 0

    def insert_pool_v4(self, r) -> bool:
        return self._batch("pools_v4", [(r.pool_id.lower(), r.currency0, r.currency1, r.fee,
                                         r.tick_spacing, r.hooks, r.sqrt_price_x96, r.tick,
                                         r.block_number, r.ts)]) > 0

    def insert_token_transfer(self, r) -> bool:
        return self._batch("token_transfers", [(r.tx_hash.lower(), r.log_index, r.token.lower(),
                                                r.from_addr.lower(), r.to_addr.lower(), r.value,
                                                r.block_number, r.ts)]) > 0

    def insert_v4_event(self, r) -> bool:
        return self._batch("v4_events", [(r.kind, r.tx_hash.lower(), r.log_index, r.pool_id, r.sender,
                                          r.amount0, r.amount1, r.block_number, r.ts)]) > 0

    def insert_token(self, r) -> bool:
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO tokens(address,symbol,name,creator,launchpad,created_ts,pool_id) "
                            "VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                            (r.address.lower(), r.symbol, r.name, r.creator, r.launchpad, r.created_ts, r.pool_id))
                n = cur.rowcount
            conn.commit()
            return n > 0
        finally:
            self.pool.putconn(conn)

    def insert_launchpad_event(self, r) -> bool:
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO launchpad_events(tx_hash,log_index,launchpad,event_name,topic0,"
                            "token,address,block_number,ts,topics,data) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                            "ON CONFLICT DO NOTHING",
                            (r.tx_hash.lower(), r.log_index, r.launchpad, r.event_name, r.topic0, r.token,
                             r.address.lower(), r.block_number, r.ts, ",".join(r.topics), r.data))
                n = cur.rowcount
            conn.commit()
            return n > 0
        finally:
            self.pool.putconn(conn)

    def upsert_wallet(self, address: str, ts, trade_delta: int = 1) -> bool:
        self._exec("INSERT INTO wallets(address,first_seen_ts,trade_count) VALUES(%s,%s,%s) "
                   "ON CONFLICT(address) DO UPDATE SET trade_count=wallets.trade_count+EXCLUDED.trade_count",
                   (address.lower(), ts, trade_delta))
        return True

    # --- batch (backfill path) ---
    def insert_swaps(self, rows) -> int:
        return self._batch("swaps", [(r.tx_hash.lower(), r.log_index, r.block_number, r.ts, r.token,
                                      r.wallet, r.side, r.amount_in, r.amount_out, r.price_implied,
                                      r.dex, r.pool) for r in rows])

    def insert_pool_v4_rows(self, rows) -> int:
        return self._batch("pools_v4", [(r.pool_id.lower(), r.currency0, r.currency1, r.fee,
                                         r.tick_spacing, r.hooks, r.sqrt_price_x96, r.tick,
                                         r.block_number, r.ts) for r in rows])

    def insert_transfers(self, rows) -> int:
        return self._batch("token_transfers", [(r.tx_hash.lower(), r.log_index, r.token.lower(),
                                                r.from_addr.lower(), r.to_addr.lower(), r.value,
                                                r.block_number, r.ts) for r in rows])

    def insert_v4_events(self, rows) -> int:
        return self._batch("v4_events", [(r.kind, r.tx_hash.lower(), r.log_index, r.pool_id, r.sender,
                                          r.amount0, r.amount1, r.block_number, r.ts) for r in rows])

    def insert_v4_liquidity_rows(self, rows) -> int:
        return self._batch("v4_liquidity", [(r.tx_hash.lower(), r.log_index, r.pool_id, r.sender,
                                             r.tick_lower, r.tick_upper, r.liquidity_delta, r.salt,
                                             r.block_number, r.ts) for r in rows])

    def insert_tx_senders(self, rows) -> int:
        return self._batch("tx_senders", [(tx.lower(), (fr or "").lower() or None,
                                           (to or "").lower() or None, blk)
                                          for tx, fr, to, blk in rows])

    # --- reads ---
    def get_pool_v4(self, pool_id: str):
        conn = self.pool.getconn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM pools_v4 WHERE pool_id=%s", (pool_id.lower(),))
                row = cur.fetchone()
                return dict(row) if row else None
        finally:
            self.pool.putconn(conn)

    def query_dev_buys_inferred(self, window_seconds: int = 86400, limit: int = 50):
        conn = self.pool.getconn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT tr.tx_hash, tr.log_index, tr.token, tr.to_addr AS creator_wallet, "
                    "tr.value AS amount, tr.ts AS transfer_ts, t.created_ts AS token_created_ts, "
                    "TRUE AS is_inferred, %s AS window_seconds FROM token_transfers tr "
                    "JOIN tokens t ON lower(t.address)=lower(tr.token) AND lower(t.creator)=lower(tr.to_addr) "
                    "WHERE t.created_ts IS NOT NULL AND tr.ts IS NOT NULL "
                    "AND tr.ts >= t.created_ts AND tr.ts <= t.created_ts + %s ORDER BY tr.ts LIMIT %s",
                    (window_seconds, window_seconds, limit))
                return [dict(r) for r in cur.fetchall()]
        finally:
            self.pool.putconn(conn)

    def counts(self) -> dict[str, int]:
        out = {}
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                for t in ("tokens", "swaps", "dev_buys", "launchpad_events", "wallets", "pools_v4", "token_transfers", "v4_events", "v4_liquidity", "tx_senders", "resolved_blocks", "wallet_scores", "dev_buys_inferred", "data_gaps"):
                    cur.execute(f"SELECT COUNT(*) FROM {t}")
                    out[t] = int(cur.fetchone()[0])
        finally:
            self.pool.putconn(conn)
        return out

    def distinct_swap_tx_hashes(self) -> list[str]:
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT DISTINCT tx_hash FROM swaps WHERE tx_hash IS NOT NULL")
                return [r[0] for r in cur.fetchall()]
        finally:
            self.pool.putconn(conn)

    def resolved_tx_hashes(self) -> set[str]:
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT tx_hash FROM tx_senders")
                return {r[0] for r in cur.fetchall()}
        finally:
            self.pool.putconn(conn)

    def distinct_swap_blocks(self) -> list[int]:
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT DISTINCT block_number FROM swaps WHERE block_number IS NOT NULL "
                            "ORDER BY block_number")
                return [int(r[0]) for r in cur.fetchall()]
        finally:
            self.pool.putconn(conn)

    def distinct_swap_blocks_range(self, lo: int, hi: int) -> list[int]:
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT DISTINCT s.block_number FROM swaps s "
                    "WHERE s.block_number >= %s AND s.block_number <= %s "
                    "AND NOT EXISTS (SELECT 1 FROM resolved_blocks r "
                    "                WHERE r.block_number = s.block_number) "
                    "ORDER BY s.block_number", (int(lo), int(hi)))
                return [int(r[0]) for r in cur.fetchall()]
        finally:
            self.pool.putconn(conn)

    def resolved_blocks(self) -> set[int]:
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT block_number FROM resolved_blocks")
                return {int(r[0]) for r in cur.fetchall()}
        finally:
            self.pool.putconn(conn)

    def mark_blocks_resolved(self, blocks: list) -> int:
        return self._batch("resolved_blocks", [(int(b),) for b in blocks])

    def sample(self, table: str, limit: int = 3):
        conn = self.pool.getconn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(f"SELECT * FROM {table} LIMIT {int(limit)}")
                return [dict(r) for r in cur.fetchall()]
        finally:
            self.pool.putconn(conn)
