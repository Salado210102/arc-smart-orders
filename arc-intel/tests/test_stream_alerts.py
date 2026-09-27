import os
import tempfile
import unittest

from indexer.stream_alerts import IncrementalState, bucket_of, save_state, load_state


def leg(w, t, block, side, qty, sv):
    return {"wallet": w, "token": t, "block": block, "side": side,
            "token_qty": qty, "stable_value": sv}


class StreamAlertsTests(unittest.TestCase):
    def test_bucket_of(self):
        self.assertEqual(bucket_of(1999, 1000), 1)

    def test_dev_sell_detected(self):
        st = IncrementalState(bucket_blocks=1000, lookback=12)
        creators = {"0xtok": "0xdev"}
        st.apply_leg(leg("0xdev", "0xtok", 100, "buy", 100.0, 1.0), creators, emit=False)
        alerts = st.apply_leg(leg("0xdev", "0xtok", 200, "sell", 100.0, 2.0), creators)
        kinds = [a.kind for a in alerts]
        self.assertIn("dev_sell", kinds)

    def test_no_emit_during_init(self):
        st = IncrementalState(bucket_blocks=1000)
        creators = {"0xtok": "0xdev"}
        st.apply_leg(leg("0xdev", "0xtok", 100, "buy", 100.0, 1.0), creators, emit=False)
        alerts = st.apply_leg(leg("0xdev", "0xtok", 200, "sell", 100.0, 2.0), creators, emit=False)
        self.assertEqual(alerts, [])

    def test_volume_collapse(self):
        st = IncrementalState(bucket_blocks=1000, lookback=12, z_threshold=-2.0)
        creators = {"0xtok": "0xother"}
        vals = [9, 10, 11, 10, 9, 10, 11, 10, 9, 10, 11, 10, 0]
        alerts = []
        for i, v in enumerate(vals):
            alerts += st.apply_leg(leg("0xo", "0xtok", i * 1000 + 1, "buy", 1.0, float(v)), creators)
        self.assertIn("volume_collapse", [a.kind for a in alerts])

    def test_compound_after_dev_sell(self):
        st = IncrementalState(bucket_blocks=1000, lookback=12, window_blocks=6000)
        st.last_dev_sell_block["0xtok"] = 8000
        creators = {"0xtok": "0xdev"}
        vals = [9, 10, 11, 10, 9, 10, 11, 10, 9, 10, 11, 10, 0]
        alerts = []
        for i, v in enumerate(vals):
            alerts += st.apply_leg(leg("0xo", "0xtok", i * 1000 + 1, "buy", 1.0, float(v)), creators)
        kinds = [a.kind for a in alerts]
        self.assertIn("volume_collapse", kinds)
        self.assertIn("compound", kinds)

    def test_volume_spike(self):
        st = IncrementalState(bucket_blocks=1000, lookback=12, min_spike_usdc=1000.0)
        creators = {"0xtok": "0xother"}
        vals = [400, 500, 450, 600, 550, 500, 450, 500, 550, 500, 450, 500, 5000]
        alerts = []
        for i, v in enumerate(vals):
            alerts += st.apply_leg(leg("0xo", "0xtok", i * 1000 + 1, "buy", 1.0, float(v)), creators)
        spikes = [a for a in alerts if a.kind == "volume_spike"]
        self.assertEqual(len(spikes), 1)
        self.assertGreaterEqual(spikes[0].context["z"], 2.5)
        self.assertEqual(spikes[0].severity, "high")

    def test_large_sell_non_creator(self):
        st = IncrementalState(bucket_blocks=1000, lookback=12, large_sell_usd=1000.0)
        creators = {"0xtok": "0xdev"}
        alerts = st.apply_leg(leg("0xwhale", "0xtok", 1000, "sell", 1000.0, 5000.0), creators)
        self.assertIn("large_sell", [a.kind for a in alerts])

    def test_large_sell_ignores_creator(self):
        st = IncrementalState(bucket_blocks=1000, lookback=12, large_sell_usd=1000.0)
        creators = {"0xtok": "0xdev"}
        st.apply_leg(leg("0xdev", "0xtok", 10, "buy", 100.0, 1.0), creators, emit=False)
        alerts = st.apply_leg(leg("0xdev", "0xtok", 1000, "sell", 100.0, 5000.0), creators)
        self.assertNotIn("large_sell", [a.kind for a in alerts])

    def test_old_pickle_is_forward_compatible(self):
        import pickle
        st = IncrementalState(bucket_blocks=1000, lookback=12)
        for k in ("spike_z", "min_spike_usdc", "large_sell_usd", "last_spike_bucket"):
            st.__dict__.pop(k, None)
        st2 = pickle.loads(pickle.dumps(st))
        self.assertEqual(st2.spike_z, 2.5)
        self.assertEqual(st2.large_sell_usd, 5000.0)
        self.assertEqual(st2.last_spike_bucket, {})

    def test_atomic_save_and_bak_fallback(self):
        st = IncrementalState(bucket_blocks=1000, lookback=12)
        fd, path = tempfile.mkstemp(suffix=".pkl")
        os.close(fd)
        try:
            save_state(path, st, 100)
            _, cur = load_state(path)
            self.assertEqual(cur, 100)
            save_state(path, st, 200)          # rotates previous into .bak
            with open(path, "wb") as fh:
                fh.write(b"garbage")           # corrupt the main file
            _, cur2 = load_state(path)
            self.assertEqual(cur2, 100)        # recovered from .bak
        finally:
            for p in (path, path + ".bak", path + ".tmp"):
                try:
                    os.unlink(p)
                except OSError:
                    pass

    def test_volume_spike_requires_price_up_and_buyers(self):
        st = IncrementalState(bucket_blocks=1000, lookback=12, min_spike_usdc=1.0)
        creators = {"0xtok": "0xother"}
        alerts = []
        # 12 buckets alternating small buys at price 0.01 (qty=100, sv=1 or 2)
        for i in range(12):
            sv = 1.0 if i % 2 == 0 else 2.0
            alerts += st.apply_leg(leg("0xo", "0xtok", i * 1000 + 1, "buy", 100.0, sv), creators)
        # big volume bucket but price CRASHES (qty=10000, sv=10 -> price 0.001)
        alerts += st.apply_leg(leg("0xo", "0xtok", 12 * 1000 + 1, "buy", 10000.0, 10.0), creators)
        self.assertNotIn("volume_spike", [a.kind for a in alerts])

    def test_price_surge(self):
        st = IncrementalState(bucket_blocks=1000, lookback=12, price_surge_pct=50.0)
        creators = {"0xtok": "0xother"}
        alerts = []
        for i in range(12):
            alerts += st.apply_leg(leg("0xo", "0xtok", i * 1000 + 1, "buy", 1000.0, 1.0), creators)
        alerts += st.apply_leg(leg("0xo", "0xtok", 12 * 1000 + 1, "buy", 1000.0, 2.0), creators)
        self.assertIn("price_surge", [a.kind for a in alerts])

    def test_whale_buy(self):
        st = IncrementalState(bucket_blocks=1000, lookback=12, whale_buy_usd=1000.0)
        creators = {"0xtok": "0xother"}
        alerts = st.apply_leg(leg("0xwhale", "0xtok", 1000, "buy", 1000.0, 3000.0), creators)
        self.assertIn("whale_buy", [a.kind for a in alerts])

    def test_dev_sell_volume_confirmation(self):
        st = IncrementalState(bucket_blocks=1000, lookback=12, min_confirm_usdc=500.0)
        creators = {"0xtok": "0xdev"}
        st.apply_leg(leg("0xdev", "0xtok", 10, "buy", 100.0, 1.0), creators, emit=False)
        st.apply_leg(leg("0xo", "0xtok", 1000, "buy", 50.0, 400.0), creators)
        alerts = st.apply_leg(leg("0xdev", "0xtok", 2000, "sell", 30.0, 200.0), creators)
        dev = [a for a in alerts if a.kind == "dev_sell"]
        self.assertEqual(len(dev), 1)
        self.assertTrue(dev[0].context["vol_confirmed"])
        self.assertEqual(dev[0].severity, "medium")   # bumped from "low" by volume

    def test_dev_sell_without_volume_not_confirmed(self):
        st = IncrementalState(bucket_blocks=1000, lookback=12, min_confirm_usdc=500.0)
        creators = {"0xtok": "0xdev"}
        st.apply_leg(leg("0xdev", "0xtok", 10, "buy", 100.0, 1.0), creators, emit=False)
        alerts = st.apply_leg(leg("0xdev", "0xtok", 2000, "sell", 30.0, 200.0), creators)
        dev = [a for a in alerts if a.kind == "dev_sell"]
        self.assertEqual(len(dev), 1)
        self.assertFalse(dev[0].context["vol_confirmed"])
        self.assertEqual(dev[0].severity, "low")

    def test_save_load_state_roundtrip(self):
        st = IncrementalState(bucket_blocks=1000, lookback=12)
        creators = {"0xtok": "0xdev"}
        st.apply_leg(leg("0xdev", "0xtok", 500, "buy", 10.0, 1.0), creators, emit=False)
        fd, path = tempfile.mkstemp(suffix=".pkl")
        os.close(fd)
        try:
            save_state(path, st, 777)
            st2, cur = load_state(path)
            self.assertEqual(cur, 777)
            self.assertIn(("0xdev", "0xtok"), st2.positions)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
