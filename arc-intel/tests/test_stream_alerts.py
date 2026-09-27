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
