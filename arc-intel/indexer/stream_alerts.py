"""Incremental alert engine: processes only NEW legs (block > cursor) with persistent state,
instead of rescanning the full history each cycle.

Pure core (`IncrementalState.apply_legs`) is testable; the PG wrapper streams new legs and
persists the block cursor. Reuses the Phase-3 alert rules (dev-sell significance, volume
z-score collapse, compound).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from dataclasses import fields as _dc_fields
from dataclasses import MISSING as _DC_MISSING

from .alerts import Alert, is_significant_sell, pct_of_position, severity_for, rolling_zscore

SECONDS_PER_BLOCK = 0.52


def bucket_of(block: int, bucket_blocks: int) -> int:
    return int(block) // int(bucket_blocks)


@dataclass
class IncrementalState:
    bucket_blocks: int = 1154            # ~10 min
    lookback: int = 12
    z_threshold: float = -2.0
    window_blocks: int = 6000            # compound window
    spike_z: float = 2.5                 # volume spike: z >= +2.5
    min_spike_usdc: float = 500.0        # ...and >= $500 in the bucket (avoid noise)
    min_confirm_usdc: float = 500.0      # recent volume that confirms a dev-sell
    large_sell_usd: float = 5000.0       # whale/team dump: single sell >= $5k
    large_sell_ratio: float = 0.5        # ...and >= 50% of the token's recent (6-bucket) volume
    price_surge_pct: float = 50.0        # discovery: price +>=50% vs ~lookback buckets ago
    whale_buy_usd: float = 1000.0        # discovery: single buy >= $1k (whale) with price up
    seen: set = field(default_factory=set)  # tokens already seen on the v4 DEX (graduation)
    spike_min_price_pct: float = 0.0     # volume spike ONLY if price is up >= this % (not a dump)
    spike_min_buy_ratio: float = 1.2     # ...and buy volume >= sell volume * this (net buyers)
    prices: dict = field(default_factory=dict)          # token -> {bucket: price}
    buys: dict = field(default_factory=dict)            # token -> {bucket: buy_vol}
    sells: dict = field(default_factory=dict)           # token -> {bucket: sell_vol}
    last_surge_bucket: dict = field(default_factory=dict)
    positions: dict = field(default_factory=dict)        # (wallet, token) -> [qty, cost, entry]
    volume: dict = field(default_factory=dict)           # token -> {bucket: vol}
    last_dev_sell_block: dict = field(default_factory=dict)
    last_collapse_bucket: dict = field(default_factory=dict)
    last_spike_bucket: dict = field(default_factory=dict)

    def __setstate__(self, d: dict) -> None:
        """Forward-compatible with older pickles: fill any missing field with its default.

        Robustness: adding a new field to this dataclass must NOT break loading a state saved by
        an older version (that would crash the loop). Missing attributes get their default.
        """
        for f in _dc_fields(self):
            if f.name not in d:
                if f.default_factory is not _DC_MISSING:
                    d[f.name] = f.default_factory()
                elif f.default is not _DC_MISSING:
                    d[f.name] = f.default
        self.__dict__.update(d)

    def apply_leg(self, leg: dict, creators: dict, emit: bool = True) -> list[Alert]:
        token = (leg.get("token") or "").lower()
        wallet = (leg.get("wallet") or "").lower()
        block = int(leg.get("block") or 0)
        qty = float(leg.get("token_qty") or 0.0)
        sv = float(leg.get("stable_value") or 0.0)
        side = leg.get("side")
        alerts: list[Alert] = []

        # Graduation: a token appears on the v4 DEX for the first time (launchpad -> DEX pool live).
        if emit and token and token not in self.seen:
            a = Alert(token=token, kind="graduation", severity="medium", block=block, context={})
            a.message = f"{token}: new token on the DEX (graduated) at block {block}"
            alerts.append(a)
        if token:
            self.seen.add(token)

        buck = bucket_of(block, self.bucket_blocks)
        vols = self.volume.setdefault(token, {})
        vols[buck] = vols.get(buck, 0.0) + sv
        keep = self.lookback * 4
        if len(vols) > keep:
            for b in sorted(vols)[:-keep]:
                vols.pop(b, None)
        price = (sv / qty) if qty > 0 else 0.0
        if price > 0:
            pr = self.prices.setdefault(token, {})
            pr[buck] = price
            if len(pr) > keep:
                for b in sorted(pr)[:-keep]:
                    pr.pop(b, None)
        # Buy/sell FLOW per bucket (who's in control): only bullish flow should alert buys.
        fs = self.buys if side == "buy" else (self.sells if side == "sell" else None)
        if fs is not None:
            fd = fs.setdefault(token, {})
            fd[buck] = fd.get(buck, 0.0) + sv
            if len(fd) > keep:
                for b in sorted(fd)[:-keep]:
                    fd.pop(b, None)

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
                    sev = severity_for(pct, proceeds)
                    vol_recent = sum(v for b, v in vols.items() if b >= buck - 6)
                    confirmed = vol_recent >= self.min_confirm_usdc
                    if confirmed and sev != "high":
                        sev = "medium" if sev == "low" else "high"
                    a = Alert(token=token, kind="dev_sell", severity=sev,
                              block=block, wallet=wallet, role="creator", amount_usdc=proceeds,
                              pct_position=pct, context={"pos_before": pos[0],
                                                         "vol_recent": round(vol_recent, 0),
                                                         "vol_confirmed": confirmed})
                    a.message = (f"{wallet} (creator) sold {pct * 100:.0f}% of its {token} "
                                 f"position (~${proceeds:,.0f})"
                                 + (" [high volume]" if confirmed else "") + f" at block {block}")
                    alerts.append(a)
                    self.last_dev_sell_block[token] = block
                cogs = (pos[1] / pos[0]) * sell_qty
                pos[1] = max(0.0, pos[1] - cogs)
                pos[0] -= sell_qty
                if pos[0] <= 1e-18:
                    self.positions.pop(key, None)

        # Whale / team dump: a large non-creator sell that dominates recent traded volume.
        if emit and side == "sell" and wallet != creator and sv >= self.large_sell_usd:
            vol_recent = sum(v for b, v in vols.items() if b >= buck - 6)
            if vol_recent <= 0 or sv >= self.large_sell_ratio * vol_recent:
                sev = "high" if sv >= self.large_sell_usd * 4 else "medium"
                share = (sv / vol_recent * 100.0) if vol_recent else 0.0
                a = Alert(token=token, kind="large_sell", severity=sev, block=block,
                          wallet=wallet, role="holder", amount_usdc=sv,
                          context={"usd": round(sv, 0), "vol_recent": round(vol_recent, 0),
                                   "share_pct": round(share, 1)})
                a.message = (f"{wallet} sold ~${sv:,.0f} of {token} "
                             f"({share:.0f}% of recent volume) at block {block}")
                alerts.append(a)

        # Discovery: whale buy (a large buy dominating recent volume) with price up.
        if emit and side == "buy" and sv >= self.whale_buy_usd and self._price_up(token, buck):
            vol_recent = sum(v for b, v in vols.items() if b >= buck - 6)
            if vol_recent <= 0 or sv >= 0.5 * vol_recent:
                a = Alert(token=token, kind="whale_buy",
                          severity="high" if sv >= self.whale_buy_usd * 5 else "medium",
                          block=block, wallet=wallet, amount_usdc=sv, context={"usd": round(sv, 0)})
                a.message = f"{wallet} bought ~${sv:,.0f} of {token} (price up) at block {block}"
                alerts.append(a)

        # Discovery: price surge vs ~lookback buckets ago.
        if emit and price > 0 and self.last_surge_bucket.get(token) != buck:
            pr = self.prices.get(token, {})
            past = [b for b in pr if b <= buck - self.lookback]
            if past:
                old = pr[max(past)]
                if old > 0 and (price / old - 1.0) * 100.0 >= self.price_surge_pct:
                    self.last_surge_bucket[token] = buck
                    pct = (price / old - 1.0) * 100.0
                    a = Alert(token=token, kind="price_surge",
                              severity="high" if pct >= 200 else "medium", block=block,
                              context={"pct": round(pct, 1)})
                    a.message = f"{token}: price +{pct:.0f}% (to {price:.2e}) at block {block}"
                    alerts.append(a)

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

        flow_buy = sum(v for b, v in self.buys.get(token, {}).items() if b >= buck - 6)
        flow_sell = sum(v for b, v in self.sells.get(token, {}).items() if b >= buck - 6)
        price_up = self._price_up(token, buck)
        net_buy = flow_buy > 0 and flow_buy >= flow_sell * self.spike_min_buy_ratio
        # QUALITY: volume up AND price up AND net buyers (never a dump disguised as a spike).
        if (z and z[-1][1] is not None and z[-1][0] == buck and z[-1][1] >= self.spike_z
                and vols.get(buck, 0.0) >= self.min_spike_usdc
                and price_up and net_buy
                and self.last_spike_bucket.get(token) != buck):
            self.last_spike_bucket[token] = buck
            val = round(z[-1][1], 3)
            if emit:
                a = Alert(token=token, kind="volume_spike",
                          severity="high" if val >= self.spike_z + 1.0 else "medium", block=block,
                          context={"z": val, "vol_usdc": round(vols.get(buck, 0.0), 0),
                                   "buy_usd": round(flow_buy, 0), "sell_usd": round(flow_sell, 0)})
                a.message = (f"{token}: volume UP + price UP at block {block} · "
                             f"vol ~${vols.get(buck, 0.0):,.0f} · buys ${flow_buy:,.0f} vs "
                             f"sells ${flow_sell:,.0f} (last hour)")
                alerts.append(a)
        return alerts

    def _price_up(self, token, buck) -> bool:
        """True if the price is up >= spike_min_price_pct vs ~lookback buckets ago."""
        pr = self.prices.get(token, {})
        past = [b for b in pr if b <= buck - self.lookback]
        if not past:
            return False
        old = pr[max(past)]
        cur = pr.get(buck, 0.0)
        if old <= 0 or cur <= 0:
            return False
        return (cur / old - 1.0) * 100.0 >= self.spike_min_price_pct

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


def load_symbols_for(storage, tokens) -> dict:
    """Symbols for a bounded set of tokens (per-cycle refresh)."""
    toks = [str(t).lower() for t in tokens if t]
    if not toks:
        return {}
    conn = storage.pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT lower(address), symbol FROM tokens "
                        "WHERE symbol IS NOT NULL AND lower(address) = ANY(%s)", (toks,))
            return {a: s for a, s in cur.fetchall() if s}
    finally:
        storage.pool.putconn(conn)


def load_creators_for(storage, tokens) -> dict:
    """Creators for a bounded set of tokens (per-cycle refresh -> no stale map)."""
    toks = [str(t).lower() for t in tokens if t]
    if not toks:
        return {}
    conn = storage.pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT lower(address), lower(creator) FROM tokens "
                        "WHERE creator IS NOT NULL AND lower(address) = ANY(%s)", (toks,))
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
    """Atomic, durable save: write .tmp, keep previous as .bak, then os.replace."""
    import os
    import pickle
    tmp = f"{path}.tmp"
    try:
        with open(tmp, "wb") as fh:
            pickle.dump({"state": state, "cursor": int(cursor)}, fh)
        if os.path.exists(path):
            try:
                os.replace(path, path + ".bak")
            except OSError:
                pass
        os.replace(tmp, path)
    except OSError:
        pass


def load_state(path: str):
    import pickle
    for p in (path, path + ".bak"):
        try:
            with open(p, "rb") as fh:
                d = pickle.load(fh)
            return d.get("state"), int(d.get("cursor", 0))
        except Exception:
            continue
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

