"""Incremental alert engine: processes only NEW legs (block > cursor) with persistent state,
instead of rescanning the full history each cycle.

Pure core (`IncrementalState.apply_legs`) is testable; the PG wrapper streams new legs and
persists the block cursor. Reuses the Phase-3 alert rules (dev-sell significance, volume
z-score collapse, compound).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .alerts import Alert, is_significant_sell, pct_of_position, severity_for
from .risk import rolling_zscore

SECONDS_PER_BLOCK = 0.52


def bucket_of(block: int, bucket_blocks: int) -> int:
    return int(block) // int(bucket_blocks)


@dataclass
class IncrementalState:
    bucket_blocks: int = 1154            # ~10 min
    lookback: int = 12
    z_threshold: float = -2.0
    window_blocks: int = 6000            # compound window
    positions: dict = field(default_factory=dict)        # (wallet, token) -> [qty, cost, entry]
    volume: dict = field(default_factory=dict)           # token -> {bucket: vol}
    last_dev_sell_block: dict = field(default_factory=dict)
    last_collapse_bucket: dict = field(default_factory=dict)

    def apply_leg(self, leg: dict, creators: dict, emit: bool = True) -> list[Alert]:
        token = (leg.get("token") or "").lower()
        wallet = (leg.get("wallet") or "").lower()
        block = int(leg.get("block") or 0)
        qty = float(leg.get("token_qty") or 0.0)
        sv = float(leg.get("stable_value") or 0.0)
        side = leg.get("side")
        alerts: list[Alert] = []

        buck = bucket_of(block, self.bucket_blocks)
        vols = self.volume.setdefault(token, {})
        vols[buck] = vols.get(buck, 0.0) + sv
        keep = self.lookback * 4
        if len(vols) > keep:
            for b in sorted(vols)[:-keep]:
                vols.pop(b, None)

        creator = (creators.get(token) or "").lower()
        if wallet == creator and creator:
            key = (wallet, token)
            pos = self.positions.get(key)
            if side == "buy":
                if pos is None:
                    self.positions[key] = [qty, sv, block]
                else:
                    pos[0] += qty
                    pos[1] += sv
            elif side == "sell" and pos and pos[0] > 0:
                sell_qty = min(qty, pos[0])
                frac = (sell_qty / qty) if qty else 0.0
                proceeds = sv * frac
                if emit and is_significant_sell(sell_qty, pos[0], proceeds):
                    pct = pct_of_position(sell_qty, pos[0])
                    a = Alert(token=token, kind="dev_sell", severity=severity_for(pct, proceeds),
                              block=block, wallet=wallet, role="creator", amount_usdc=proceeds,
                              pct_position=pct, context={"pos_before": pos[0]})
                    a.message = (f"{wallet} (creator) sold {pct * 100:.0f}% of its {token} "
                                 f"position (~${proceeds:,.0f}) at block {block}")
                    alerts.append(a)
                    self.last_dev_sell_block[token] = block
                cogs = (pos[1] / pos[0]) * sell_qty
                pos[1] = max(0.0, pos[1] - cogs)
                pos[0] -= sell_qty
                if pos[0] <= 1e-18:
                    self.positions.pop(key, None)

        series = sorted(self.volume[token].items())
        z = rolling_zscore(series, self.lookback)
        if (z and z[-1][1] is not None and z[-1][0] == buck and z[-1][1] <= self.z_threshold
                and self.last_collapse_bucket.get(token) != buck):
            self.last_collapse_bucket[token] = buck
            val = round(z[-1][1], 3)
            if emit:
                a = Alert(token=token, kind="volume_collapse",
                          severity="high" if val <= -3 else "medium", block=block,
                          context={"z": val})
                a.message = f"{token}: volume collapse at block {block} (z={val})"
                alerts.append(a)
                sb = self.last_dev_sell_block.get(token)
                if sb is not None and 0 <= block - sb <= self.window_blocks:
                    c = Alert(token=token, kind="compound", severity="high", block=block,
                              context={"sell_block": sb, "z": val})
                    c.message = (f"{token}: dev-sell at block {sb} followed by volume collapse "
                                 f"at {block} (z={val})")
                    alerts.append(c)
        return alerts

    def apply_legs(self, legs: list, creators: dict, emit: bool = True) -> list[Alert]:
        out: list[Alert] = []
        for leg in legs:
            out.extend(self.apply_leg(leg, creators, emit=emit))
        return out


def load_symbols(storage) -> dict:
    conn = storage.pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT lower(address), symbol FROM tokens WHERE symbol IS NOT NULL")
            return {a: s for a, s in cur.fetchall() if s}
    finally:
        storage.pool.putconn(conn)


def load_creators(storage) -> dict:
    conn = storage.pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT lower(address), lower(creator) FROM tokens WHERE creator IS NOT NULL")
            return {t: c for t, c in cur.fetchall()}
    finally:
        storage.pool.putconn(conn)


def build_initial_state(storage, state: IncrementalState, creators: dict, upto_block: int,
                        on_progress=None) -> int:
    """Rebuild state from history (block <= upto_block) WITHOUT emitting alerts."""
    conn = storage.pool.getconn()
    n = 0
    try:
        with conn.cursor(name="legs_init") as sc:
            sc.itersize = 200000
            sc.execute("SELECT wallet, token, block, side, token_qty, stable_value FROM legs "
                       "WHERE block <= %s ORDER BY block, log_index", (int(upto_block),))
            for wallet, token, block, side, qty, sv in sc:
                state.apply_leg({"wallet": wallet, "token": token, "block": block, "side": side,
                                 "token_qty": qty, "stable_value": sv}, creators, emit=False)
                n += 1
                if on_progress and n % 500000 == 0:
                    on_progress(n)
    finally:
        storage.pool.putconn(conn)
    return n


def fetch_new_legs(storage, after_block: int, upto_block: int, limit: int = 200000) -> list:
    conn = storage.pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT wallet, token, block, side, token_qty, stable_value FROM legs "
                        "WHERE block > %s AND block <= %s ORDER BY block, log_index LIMIT %s",
                        (int(after_block), int(upto_block), int(limit)))
            return [{"wallet": w, "token": t, "block": b, "side": s, "token_qty": q, "stable_value": v}
                    for w, t, b, s, q, v in cur.fetchall()]
    finally:
        storage.pool.putconn(conn)


def save_state(path: str, state, cursor: int) -> None:
    import pickle
    try:
        with open(path, "wb") as fh:
            pickle.dump({"state": state, "cursor": int(cursor)}, fh)
    except OSError:
        pass


def load_state(path: str):
    import pickle
    try:
        with open(path, "rb") as fh:
            d = pickle.load(fh)
        return d.get("state"), int(d.get("cursor", 0))
    except Exception:
        return None, None


def load_price_series(storage, token: str) -> list:
    """[(block, price)] for a token, ordered by block (for the paper counterfactual)."""
    conn = storage.pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT block, price FROM legs WHERE token=%s ORDER BY block",
                        (token.lower(),))
            return [(int(b), float(p or 0.0)) for b, p in cur.fetchall()]
    finally:
        storage.pool.putconn(conn)


def max_leg_block(storage) -> int:
    conn = storage.pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT max(block) FROM legs")
            return int(cur.fetchone()[0] or 0)
    finally:
        storage.pool.putconn(conn)


def recent_active_tokens(storage, n: int = 10, window_blocks: int = 100000,
                         min_wallets: int = 2) -> list:
    """Top-N most traded tokens in the recent window (with >= min_wallets distinct wallets)."""
    conn = storage.pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT max(block) FROM legs")
            head = int(cur.fetchone()[0] or 0)
            cur.execute(
                "SELECT token, count(*) c FROM legs WHERE block > %s "
                "GROUP BY token HAVING count(DISTINCT wallet) >= %s "
                "ORDER BY c DESC LIMIT %s",
                (head - int(window_blocks), int(min_wallets), int(n)))
            return [r[0] for r in cur.fetchall()]
    finally:
        storage.pool.putconn(conn)

