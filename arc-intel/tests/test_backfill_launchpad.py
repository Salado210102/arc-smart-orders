import os
import tempfile
import unittest

from indexer import backfill
from indexer.config import default_launchpads
from indexer.storage import Storage

TOKEN_CREATED = "0x1d8917231579f8ce39407f0d616f36f357b07329b0ce5164d0754ac15145ce0a"
TOKEN = "0x1111111111111111111111111111111111111111"
CREATOR = "0x2222222222222222222222222222222222222222"


def _enc_string(s: str) -> bytes:
    b = s.encode()
    pad = (-len(b)) % 32
    return len(b).to_bytes(32, "big") + b + b"\x00" * pad


def make_token_created(name="BTS", symbol="BTS", pool_id=b"\xaa" * 32):
    base = 7 * 32
    enc = {k: _enc_string(v) for k, v in (
        ("name", name), ("symbol", symbol), ("image", ""), ("website", "http://x"),
        ("twitter", ""), ("telegram", ""))}
    offsets = {}
    cur = base
    for k in ("name", "symbol", "image", "website", "twitter", "telegram"):
        offsets[k] = cur
        cur += len(enc[k])
    head = [offsets["name"], offsets["symbol"], int.from_bytes(pool_id, "big"),
            offsets["image"], offsets["website"], offsets["twitter"], offsets["telegram"]]
    data = "0x" + "".join(f"{w:064x}" for w in head) + b"".join(
        enc[k] for k in ("name", "symbol", "image", "website", "twitter", "telegram")
    ).hex()
    return {
        "transactionHash": "0x" + "ab" * 32, "logIndex": "0x0", "blockNumber": "0x1400000",
        "address": default_launchpads()[0].address,
        "topics": [TOKEN_CREATED, "0x" + "0" * 24 + TOKEN[2:], "0x" + "0" * 24 + CREATOR[2:]],
        "data": data,
    }


class LaunchpadBackfillTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.storage = Storage(self.path)
        self.storage.migrate()

    def tearDown(self):
        self.storage.close()
        os.unlink(self.path)

    def test_token_created_populates_creator(self):
        logs = [make_token_created()]

        def fake(source, address, topic, a, b, job, storage, min_size=50, max_retries=6, stats=None):
            return logs if topic == TOKEN_CREATED else []

        class Src:
            launchpads = default_launchpads()

        orig = backfill._fetch_topic_logs
        backfill._fetch_topic_logs = fake
        try:
            stats = backfill.backfill_launchpad_run(self.storage, Src(), 0, 10, chunk=100)
        finally:
            backfill._fetch_topic_logs = orig

        self.assertEqual(stats["tokens"], 1)
        tok = self.storage.sample("tokens", 1)[0]
        self.assertEqual(tok["address"], TOKEN)
        self.assertEqual(tok["creator"], CREATOR)
        self.assertEqual(tok["symbol"], "BTS")

    def test_token_created_strips_nul_bytes(self):
        logs = [make_token_created(name="A\x00B", symbol="X\x00Y")]

        def fake(source, address, topic, a, b, job, storage, min_size=50, max_retries=6, stats=None):
            return logs if topic == TOKEN_CREATED else []

        class Src:
            launchpads = default_launchpads()

        orig = backfill._fetch_topic_logs
        backfill._fetch_topic_logs = fake
        try:
            backfill.backfill_launchpad_run(self.storage, Src(), 0, 10, chunk=100)
        finally:
            backfill._fetch_topic_logs = orig

        tok = self.storage.sample("tokens", 1)[0]
        self.assertEqual(tok["name"], "AB")
        self.assertEqual(tok["symbol"], "XY")


if __name__ == "__main__":
    unittest.main()
