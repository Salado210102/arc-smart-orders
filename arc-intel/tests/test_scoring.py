import unittest

from indexer.scoring import (
    WalletEvent, confidence_for, insider_wallets, is_insider, detect_likely_mev,
    sybil_clusters, collapse_sybil, base_metrics, decay_weight, pit_filter,
    score_wallets, walk_forward, combine_scores, walk_forward_trades, WEIGHTS_VERSION,
)
from indexer.pnl import WalletPnl, ClosedTrade


def ev(wallet, block, token="0xtok", pool="0xpool", ain="1", aout="1", ts=None):
    return WalletEvent(wallet=wallet, token=token, pool=pool, block_number=block, ts=ts,
                       amount_in=ain, amount_out=aout)


class ScoringTests(unittest.TestCase):
    def test_confidence_thresholds(self):
        self.assertEqual(confidence_for(0), "insuficiente")
        self.assertEqual(confidence_for(8), "baja")
        self.assertEqual(confidence_for(20), "media")
        self.assertEqual(confidence_for(50), "alta")

    def test_insider_filter(self):
        ins = insider_wallets({"0xtok": "0xAbC"}, {"0xtok": {"0xdef"}})
        self.assertTrue(is_insider(ins, "0xabc", "0xtok"))
        self.assertTrue(is_insider(ins, "0xDEF", "0xtok"))
        self.assertFalse(is_insider(ins, "0xabc", "0xother"))
        self.assertFalse(is_insider(ins, "0x999", "0xtok"))

    def test_mev_detection_same_block_and_quiet(self):
        mev_events = [ev("0xmev", b) for b in (1, 1, 1, 2, 2)]
        quiet = [ev("0xquiet", b, ts=t) for b, t in zip((1, 5, 10, 20, 40), (0, 1000, 2000, 3000, 4000))]
        flagged = detect_likely_mev(mev_events + quiet)
        self.assertIn("0xmev", flagged)
        self.assertNotIn("0xquiet", flagged)

    def test_sybil_clusters_window(self):
        edges = [("0xa", "funder1", 100), ("0xb", "funder1", 200), ("0xc", "funder2", 100)]
        clusters = sybil_clusters(edges, window_seconds=3600)
        self.assertEqual(clusters["0xa"], clusters["0xb"])
        self.assertNotEqual(clusters["0xa"], clusters["0xc"])

    def test_sybil_outside_window_not_clustered(self):
        edges = [("0xa", "funder1", 100), ("0xb", "funder1", 100000)]
        clusters = sybil_clusters(edges, window_seconds=3600)
        self.assertNotEqual(clusters["0xa"], clusters["0xb"])

    def test_collapse_sybil_relabels(self):
        events = [ev("0xa", 1), ev("0xb", 2)]
        collapsed = collapse_sybil(events, {"0xa": 7, "0xb": 7})
        self.assertEqual({e.wallet for e in collapsed}, {"cluster:7"})

    def test_base_metrics_and_decay_and_pit(self):
        events = [ev("0xw", 1, ain="10", aout="20", ts=0), ev("0xw", 5, token="0xt2", pool="0xp2", ain="1", aout="2", ts=10)]
        m = base_metrics(events)["0xw"]
        self.assertEqual(m.swaps, 2)
        self.assertEqual(m.volume_in, 11.0)
        self.assertEqual(len(m.tokens), 2)
        self.assertEqual(m.first_block, 1)
        self.assertEqual(decay_weight(0), 1.0)
        self.assertTrue(0 < decay_weight(30 * 86400) < 1)
        self.assertEqual(len(pit_filter(events, 5)), 1)
        self.assertEqual(len(pit_filter(events, -1)), 0)

    def test_score_wallets_explainable(self):
        metrics = base_metrics([ev("0xa", 1)] * 10 + [ev("0xb", 1)] * 2)
        scores = score_wallets(metrics)
        self.assertEqual(scores["0xa"]["confidence"], "baja")
        self.assertEqual(scores["0xb"]["confidence"], "insuficiente")
        for w, d in scores.items():
            self.assertAlmostEqual(sum(d["breakdown"].values()), d["score"], places=4)
            self.assertEqual(d["weights_version"], WEIGHTS_VERSION)
        self.assertGreater(scores["0xa"]["score"], scores["0xb"]["score"])

    def test_combine_scores_min_sample_and_explainable(self):
        def wp(w, trades, wr, em, var, pnl=0.0):
            return WalletPnl(w, trades, int(wr * trades), wr, pnl, em, em, var, 0.0, 1, "ok")

        pnl = {
            "0xa": wp("0xa", 10, 1.0, 3.0, 1.0, 100.0),
            "0xb": wp("0xb", 10, 0.5, 1.0, 4.0, -50.0),
            "0xc": wp("0xc", 3, 1.0, 9.0, 0.0, 999.0),  # below min sample
        }
        entry = {"0xa": 0.9, "0xb": 0.1, "0xc": 0.5}
        out = combine_scores(pnl, entry, min_trades=8)
        self.assertEqual(set(out), {"0xa", "0xb"})
        for d in out.values():
            self.assertAlmostEqual(sum(d["breakdown"].values()), d["score"], places=4)
        self.assertGreater(out["0xa"]["score"], out["0xb"]["score"])

    def test_walk_forward_trades_predicts(self):
        def ct(w, eb, real):
            return ClosedTrade(w, "0xt", 1.0, 1.0, 1.0 + real, real, 1.0 + real, eb - 1, eb)

        trades = []
        for i in range(8):
            trades.append(ct(f"0xg{i}", 10, 5.0))
            trades.append(ct(f"0xg{i}", 100, 5.0))
            trades.append(ct(f"0xb{i}", 10, -5.0))
            trades.append(ct(f"0xb{i}", 100, -5.0))
        res = walk_forward_trades(trades, split_block=50, horizon_blocks=100, min_train=1)
        self.assertEqual(res["status"], "OK")
        self.assertAlmostEqual(res["real_corr"], 1.0, places=6)
        self.assertEqual(res["candidates"], 16)

    def test_walk_forward_real_vs_shuffled(self):
        insuff = walk_forward([(1.0, 2.0)])
        self.assertEqual(insuff["status"], "INSUFFICIENT_SAMPLE")
        pairs = [(float(i), float(i) * 2.0) for i in range(10)]
        res = walk_forward(pairs, seed=1)
        self.assertEqual(res["status"], "OK")
        self.assertAlmostEqual(res["real_corr"], 1.0, places=6)


if __name__ == "__main__":
    unittest.main()
