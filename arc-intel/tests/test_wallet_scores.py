import os
import tempfile
import unittest

from indexer.storage import Storage


def score(w, val, trades=10):
    return {"wallet": w, "score": val, "version": "v3", "trades": trades, "win_rate": 0.8,
            "avg_mult": 2.0, "pnl": 5.0, "variance": 0.1, "entry_pct": 0.7, "confidence": "media"}


class WalletScoresTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.storage = Storage(self.path)
        self.storage.migrate()

    def tearDown(self):
        self.storage.close()
        os.unlink(self.path)

    def test_save_and_load_with_thresholds(self):
        self.storage.save_wallet_scores([score("0xA", 0.9), score("0xB", 0.5)])
        rows = self.storage.load_wallet_scores(min_score=0.6, min_trades=8)
        self.assertEqual([r["wallet"] for r in rows], ["0xa"])
        self.assertEqual(rows[0]["version"], "v3")

    def test_upsert_updates_existing(self):
        self.storage.save_wallet_scores([score("0xA", 0.3)])
        self.storage.save_wallet_scores([score("0xA", 0.95)])
        rows = self.storage.load_wallet_scores(min_score=0.9, min_trades=8)
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["score"], 0.95)

    def test_min_trades_filter(self):
        self.storage.save_wallet_scores([score("0xA", 0.9, trades=3)])
        self.assertEqual(self.storage.load_wallet_scores(min_score=0.0, min_trades=8), [])


if __name__ == "__main__":
    unittest.main()
