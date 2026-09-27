import os
import tempfile
import unittest

from indexer.models import SwapRow
from indexer.resolve_senders import run, run_blocks
from indexer.storage import Storage


def swap(tx, wallet="0xrouter", block=1):
    return SwapRow(tx_hash=tx, log_index=0, block_number=block, ts=None, token="0xtok",
                   wallet=wallet, side="unknown", amount_in="1", amount_out="1",
                   price_implied=None, dex="uniswap_v4", pool="0xpool")


class ResolveSendersTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.storage = Storage(self.path)
        self.storage.migrate()

    def tearDown(self):
        self.storage.close()
        os.unlink(self.path)

    def test_resolves_and_is_idempotent(self):
        self.storage.insert_swap(swap("0xAA"))
        self.storage.insert_swap(swap("0xBB", block=2))
        calls = []

        def fake(url, hashes):
            calls.append(list(hashes))
            return [(h, "0xUser", "0xrouter", 1) for h in hashes]

        n = run(self.storage, "http://x", batch=100, fetcher=fake)
        self.assertEqual(n, 2)
        self.assertEqual(len(calls), 1)
        senders = {r["tx_hash"]: r["from_addr"] for r in self.storage.sample("tx_senders", 10)}
        self.assertEqual(senders["0xaa"], "0xuser")
        self.assertEqual(senders["0xbb"], "0xuser")

        # second run resolves nothing new
        n2 = run(self.storage, "http://x", batch=100, fetcher=fake)
        self.assertEqual(n2, 0)
        self.assertEqual(len(calls), 1)

    def test_limit_caps_work(self):
        for i in range(5):
            self.storage.insert_swap(swap(f"0x{i:02x}"))
        seen = []

        def fake(url, hashes):
            seen.extend(hashes)
            return [(h, "0xu", "0xr", 1) for h in hashes]

        run(self.storage, "http://x", batch=100, limit=2, fetcher=fake)
        self.assertEqual(len(seen), 2)

    def test_run_blocks_resolves_and_is_idempotent(self):
        for i in range(3):
            self.storage.insert_swap(swap(f"0x{i:02x}", block=100 + i))
        calls = []

        def fake(url, blocks):
            calls.append(list(blocks))
            return {b: [(f"0xtx{b}", "0xUser", "0xrouter") for _ in range(2)] for b in blocks}

        n = run_blocks(self.storage, "http://x", batch=5, fetcher=fake)
        self.assertEqual(n, 6)
        self.assertEqual({r["block_number"] for r in self.storage.sample("resolved_blocks", 10)},
                         {100, 101, 102})
        n2 = run_blocks(self.storage, "http://x", batch=5, fetcher=fake)
        self.assertEqual(n2, 0)
        self.assertEqual(len(calls), 1)

    def test_run_blocks_retries_missing_within_run(self):
        self.storage.insert_swap(swap("0xaa", block=100))
        calls = {"n": 0}

        def fake(url, blocks):
            calls["n"] += 1
            if calls["n"] == 1:
                return {}
            return {b: [("0xt", "0xu", "0xr")] for b in blocks}

        n = run_blocks(self.storage, "http://x", batch=5, max_attempts=3, fetcher=fake)
        self.assertEqual(n, 1)
        self.assertEqual(calls["n"], 2)

    def test_run_blocks_range_filter(self):
        for b in (100, 200, 300):
            self.storage.insert_swap(swap(f"0xb{b:02x}", block=b))
        seen = []

        def fake(url, blocks):
            seen.extend(blocks)
            return {b: [("0xt", "0xu", "0xr")] for b in blocks}

        run_blocks(self.storage, "http://x", batch=5, start=150, end=250, fetcher=fake)
        self.assertEqual(seen, [200])

    def test_run_blocks_retries_rate_limited_blocks(self):
        self.storage.insert_swap(swap("0xaa", block=100))

        def rate_limited(url, blocks):
            return {}

        self.assertEqual(run_blocks(self.storage, "http://x", batch=5, fetcher=rate_limited), 0)
        self.assertEqual(self.storage.sample("resolved_blocks", 10), [])

        def ok(url, blocks):
            return {b: [("0xt", "0xu", "0xr")] for b in blocks}

        self.assertEqual(run_blocks(self.storage, "http://x", batch=5, fetcher=ok), 1)
        self.assertEqual(len(self.storage.sample("resolved_blocks", 10)), 1)


if __name__ == "__main__":
    unittest.main()
