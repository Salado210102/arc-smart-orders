import os
import tempfile
import unittest

from indexer.models import RawEvent, SwapRow, TokenRow, TokenTransferRow
from indexer.processor import EventProcessor, decode_v3_swap, decode_token_created, decode_initialize, decode_v4_swap
from indexer.backfill import classify_rpc_error
from indexer.service import IndexerService
from indexer.sources import EventSource
from indexer.storage import Storage
from indexer.config import (
    LaunchpadConfig,
    TRANSFER_TOPIC0,
    UNISWAP_V3_SWAP_TOPIC0,
    V4_DONATE_TOPIC0,
    V4_INITIALIZE_TOPIC0,
    V4_SWAP_TOPIC0,
)

ARGUS_TOKEN_CREATED = "0x1d8917231579f8ce39407f0d616f36f357b07329b0ce5164d0754ac15145ce0a"


def _enc_string(s: str) -> bytes:
    b = s.encode("utf-8")
    pad = (32 - len(b) % 32) % 32
    return len(b).to_bytes(32, "big") + b + b"\x00" * pad


def encode_token_created(name, symbol, pool_id, image="", website="", twitter="", telegram="") -> str:
    strs = [name, symbol, image, website, twitter, telegram]
    tails = [_enc_string(s) for s in strs]
    head_size = 7 * 32
    offs, cur = [], head_size
    for t in tails:
        offs.append(cur)
        cur += len(t)
    head = [offs[0], offs[1], int(pool_id, 16), offs[2], offs[3], offs[4], offs[5]]
    data = b"".join(w.to_bytes(32, "big") for w in head) + b"".join(tails)
    return "0x" + data.hex()


def token_created_event(tx, idx, block, token, creator) -> RawEvent:
    topics = [ARGUS_TOKEN_CREATED, "0x" + token[2:].rjust(64, "0"), "0x" + creator[2:].rjust(64, "0")]
    return RawEvent(source="test", kind="launchpad", tx_hash=tx, log_index=idx, block_number=block,
                    block_time=1_700_000_000 + block, address="0xb021be536808f551b31789422fd28a6c9c6e97da",
                    topics=topics, data=encode_token_created("Argus Test", "ATST", "0x" + "ab" * 32),
                    launchpad="argus")



def signed_word(v: int, bits: int) -> str:
    mod = 1 << bits
    x = mod + v if v < 0 else v
    return format(x, "064x")


def v3_swap_event(tx: str, idx: int, block: int, pool: str, sender: str) -> RawEvent:
    data = "0x" + "".join([
        signed_word(5, 256), signed_word(-7, 256), format(1 << 96, "064x"),
        format(1000, "064x"), signed_word(100, 256),
    ])
    topics = [UNISWAP_V3_SWAP_TOPIC0, "0x" + "11" * 20, "0x" + "22" * 20]
    return RawEvent(source="test", kind="dex_swap", tx_hash=tx, log_index=idx,
                    block_number=block, block_time=1_700_000_000 + block,
                    address=pool, topics=topics, data=data, dex="uniswap_v3")


class MockSource(EventSource):
    name = "mock"

    def __init__(self, head, events, fail_first=False):
        self._head = head
        self._events = events
        self.fail_first = fail_first
        self.calls = 0

    def head(self) -> int:
        return self._head

    def poll(self, from_block, to_block):
        self.calls += 1
        if self.fail_first and self.calls == 1:
            raise RuntimeError("websocket dropped")
        return [e for e in self._events if from_block <= e.block_number <= to_block]


class LoggerStub:
    def info(self, *a, **k):
        pass

    def warning(self, *a, **k):
        pass

    def error(self, *a, **k):
        pass


def make_storage():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = Storage(path)
    s.migrate()
    return s, path


class IndexerTests(unittest.TestCase):
    def tearDown(self):
        for s in getattr(self, "_pg", []):
            try:
                s.close()
            except Exception:
                pass
        for p in getattr(self, "_paths", []):
            for suffix in ("", "-wal", "-shm"):
                try:
                    os.remove(p + suffix)
                except OSError:
                    pass

    def _storage(self):
        dsn = os.environ.get("INDEXER_TEST_DATABASE_URL")
        if dsn:
            from indexer.pg_storage import PostgresStorage
            s = PostgresStorage(dsn)
            s.migrate()
            s.truncate_all()
            self._pg = getattr(self, "_pg", []) + [s]
            return s
        s, path = make_storage()
        self._paths = getattr(self, "_paths", []) + [path]
        return s

    def test_storage_is_idempotent(self):
        s = self._storage()
        ev = v3_swap_event("0xabc", 0, 10, "0xpool", "0x" + "11" * 20)
        proc = EventProcessor(s, [])
        r1 = proc.process(ev)
        r2 = proc.process(ev)
        self.assertEqual(r1.swaps, 1)
        self.assertEqual(r2.swaps, 0)
        self.assertEqual(r2.duplicates, 1)
        self.assertEqual(s.counts()["swaps"], 1)

    def test_decode_v3_swap_signed_tick_and_amounts(self):
        ev = v3_swap_event("0xabc", 0, 10, "0xpool", "0x" + "11" * 20)
        d = decode_v3_swap(ev)
        self.assertEqual(d["amount0"], "5")
        self.assertEqual(d["amount1"], "-7")
        self.assertEqual(d["tick"], 100)
        self.assertEqual(d["sender"], "0x" + "11" * 20)

    def test_processor_creates_token_rows_via_resolver(self):
        s = self._storage()
        ev = v3_swap_event("0xabc", 0, 10, "0xpool", "0x" + "11" * 20)
        proc = EventProcessor(s, [], token_resolver=lambda pool: ("0xtokA", "0xtokB"))
        proc.process(ev)
        c = s.counts()
        self.assertEqual(c["swaps"], 1)
        self.assertEqual(c["tokens"], 2)
        self.assertEqual(c["wallets"], 1)

    def test_launchpad_event_captured_raw(self):
        s = self._storage()
        ev = RawEvent(source="test", kind="launchpad", tx_hash="0xlp", log_index=0, block_number=5,
                      block_time=1, address="0xb021be536808f551b31789422fd28a6c9c6e97da",
                      topics=["0xdeadbeef"], data="0x00", launchpad="argus")
        proc = EventProcessor(s, [LaunchpadConfig(name="argus", address=ev.address)])
        proc.process(ev)
        rows = s.sample("launchpad_events")
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["event_name"])
        self.assertEqual(rows[0]["topic0"], "0xdeadbeef")

    def test_token_created_decodes_name_symbol_creator(self):
        s = self._storage()
        ev = token_created_event("0xlaunch", 0, 9, "0x" + "cd" * 20, "0x" + "ef" * 20)
        d = decode_token_created(ev)
        self.assertEqual(d["name"], "Argus Test")
        self.assertEqual(d["symbol"], "ATST")
        self.assertEqual(d["creator"], "0x" + "ef" * 20)
        self.assertEqual(d["pool_id"], "0x" + "ab" * 32)
        cfg = LaunchpadConfig(name="argus", address=ev.address,
                              topic_map={ARGUS_TOKEN_CREATED: "TokenCreated"})
        EventProcessor(s, [cfg]).process(ev)
        rows = s.sample("tokens")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "ATST")
        self.assertEqual(rows[0]["name"], "Argus Test")
        self.assertEqual(rows[0]["launchpad"], "argus")
        self.assertEqual(rows[0]["creator"], "0x" + "ef" * 20)
        lpe = s.sample("launchpad_events")
        self.assertEqual(lpe[0]["event_name"], "TokenCreated")


    def test_dev_buys_inferred_window_and_separation(self):
        s = self._storage()
        creator = "0x" + "aa" * 20
        other = "0x" + "bb" * 20
        s.insert_token(TokenRow(address="0xtok", creator=creator, created_ts=1000, launchpad="argus"))
        # Transfer of the launched token TO the creator, within window
        s.insert_token_transfer(TokenTransferRow(tx_hash="0xd1", log_index=0, token="0xtok",
                                                 from_addr="0x" + "00" * 20, to_addr=creator,
                                                 value="123", block_number=1, ts=1100))
        # Transfer TO creator but outside window (90000s later)
        s.insert_token_transfer(TokenTransferRow(tx_hash="0xd2", log_index=0, token="0xtok",
                                                 from_addr="0x" + "00" * 20, to_addr=creator,
                                                 value="123", block_number=2, ts=91000))
        # Transfer to someone else
        s.insert_token_transfer(TokenTransferRow(tx_hash="0xd3", log_index=0, token="0xtok",
                                                 from_addr="0x" + "00" * 20, to_addr=other,
                                                 value="123", block_number=3, ts=1200))
        inferred = s.query_dev_buys_inferred(86400)
        self.assertEqual(len(inferred), 1)
        self.assertEqual(inferred[0]["tx_hash"], "0xd1")
        self.assertEqual(inferred[0]["creator_wallet"], creator)
        self.assertEqual(inferred[0]["is_inferred"], 1)
        # confirmed dev_buys table stays empty and separate
        self.assertEqual(s.counts()["dev_buys"], 0)
        self.assertEqual(s.counts()["dev_buys_inferred"], 1)

    def test_v4_initialize_and_swap_decode_and_pools_v4(self):
        s = self._storage()
        pool_id = "0x" + "ab" * 32
        c0 = "0x" + "cd" * 20
        c1 = "0x" + "ef" * 20
        init = RawEvent(source="test", kind="pool_init", tx_hash="0xinit", log_index=0, block_number=7,
                        block_time=1_700_000_007, address="0x8366a39cc670b4001a1121b8f6a443a643e40951",
                        topics=[V4_INITIALIZE_TOPIC0, pool_id, "0x" + ("cd" * 20).rjust(64, "0"), "0x" + ("ef" * 20).rjust(64, "0")],
                        data="0x" + "".join([
                            format(10000, "064x"), signed_word(200, 256), "0" * 64,
                            format(1 << 96, "064x"), signed_word(100, 256),
                        ]))
        d = decode_initialize(init)
        self.assertEqual(d["pool_id"], pool_id)
        self.assertEqual(d["currency0"], c0)
        self.assertEqual(d["currency1"], c1)
        self.assertEqual(d["fee"], 10000)
        self.assertEqual(d["tick_spacing"], 200)
        self.assertEqual(d["tick"], 100)
        EventProcessor(s, []).process(init)
        self.assertEqual(s.counts()["pools_v4"], 1)
        stored = s.get_pool_v4(pool_id)
        self.assertEqual(stored["currency0"], c0)

        swap = RawEvent(source="test", kind="dex_swap", tx_hash="0xv4", log_index=0, block_number=8,
                        block_time=1_700_000_008, address="0x8366a39cc670b4001a1121b8f6a443a643e40951",
                        topics=[V4_SWAP_TOPIC0, pool_id, "0x" + ("11" * 20).rjust(64, "0")],
                        data="0x" + "".join([
                            signed_word(-7, 256), signed_word(5, 256), format(1 << 96, "064x"),
                            format(1000, "064x"), signed_word(-100, 256), format(3000, "064x"),
                        ]), dex="uniswap_v4")
        d2 = decode_v4_swap(swap)
        self.assertEqual(d2["amount0"], "-7")
        self.assertEqual(d2["amount1"], "5")
        self.assertEqual(d2["tick"], -100)
        self.assertEqual(d2["sender"], "0x" + "11" * 20)
        EventProcessor(s, []).process(swap)
        rows = s.sample("swaps")
        self.assertEqual(rows[0]["dex"], "uniswap_v4")
        self.assertEqual(rows[0]["pool"], pool_id)
        self.assertEqual(rows[0]["token"], c0)  # resolved via pools_v4

    def test_transfer_event_stored_and_donate_decoded(self):
        from indexer.processor import decode_donate
        s = self._storage()
        tr = RawEvent(source="test", kind="token_transfer", tx_hash="0xtr", log_index=0, block_number=5,
                      block_time=1700000005, address="0xtok",
                      topics=[TRANSFER_TOPIC0, "0x" + ("00" * 20).rjust(64, "0"),
                              "0x" + ("aa" * 20).rjust(64, "0")],
                      data="0x" + format(99, "064x"))
        EventProcessor(s, []).process(tr)
        rows = s.sample("token_transfers")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["to_addr"], "0x" + "aa" * 20)
        self.assertEqual(rows[0]["value"], "99")
        don = RawEvent(source="test", kind="v4_donate", tx_hash="0xdn", log_index=1, block_number=6,
                       block_time=1700000006, address="0x8366a39cc670b4001a1121b8f6a443a643e40951",
                       topics=[V4_DONATE_TOPIC0, "0x" + "ab" * 32, "0x" + ("bb" * 20).rjust(64, "0")],
                       data="0x" + format(7, "064x") + format(8, "064x"))
        d = decode_donate(don)
        self.assertEqual(d["amount0"], "7")
        self.assertEqual(d["amount1"], "8")
        EventProcessor(s, []).process(don)
        self.assertEqual(s.counts()["v4_events"], 1)

    def test_classify_rpc_error_and_data_gaps(self):
        self.assertEqual(classify_rpc_error("rate limit exceeded"), "rate_limit")
        self.assertEqual(classify_rpc_error("HTTP Error 403: Forbidden"), "rate_limit")
        self.assertEqual(classify_rpc_error("query exceeds max results 20000, retry with the range 1-2"), "result_limit")
        self.assertEqual(classify_rpc_error("boom"), "other")
        s = self._storage()
        s.insert_gap("job1", 100, 199, "rate_limit", 6, 1700000000)
        s.insert_gap("job1", 300, 349, "result_limit", 1, 1700000001)
        gaps = s.list_gaps("job1")
        self.assertEqual(len(gaps), 2)
        self.assertEqual(gaps[0]["from_block"], 100)
        self.assertEqual(s.counts()["data_gaps"], 2)

    def test_reconnect_no_loss_no_duplicate(self):
        s = self._storage()
        events = [
            v3_swap_event("0xt1", 0, 10, "0xp", "0x" + "11" * 20),
            v3_swap_event("0xt2", 0, 11, "0xp", "0x" + "22" * 20),
        ]
        source = MockSource(head=11, events=events, fail_first=True)
        proc = EventProcessor(s, [])
        service = IndexerService(source, proc, s, LoggerStub(), poll_seconds=0,
                                 max_range_blocks=10, sleep=lambda *_: None)
        service.run(start_block=10, max_ticks=3, stop_when_synced=True)
        self.assertEqual(s.counts()["swaps"], 2)
        self.assertEqual(s.get_cursor(0), 11)

    def test_cursor_persists_across_runs(self):
        s = self._storage()
        events = [v3_swap_event("0xt1", 0, 10, "0xp", "0x" + "11" * 20)]
        source = MockSource(head=10, events=events)
        service = IndexerService(source, EventProcessor(s, []), s, LoggerStub(),
                                 max_range_blocks=10, sleep=lambda *_: None)
        service.run(start_block=10, max_ticks=2, stop_when_synced=True)
        self.assertEqual(s.get_cursor(0), 10)
        # second run re-polls same range -> no new rows
        service2 = IndexerService(MockSource(head=10, events=events), EventProcessor(s, []), s,
                                  LoggerStub(), max_range_blocks=10, sleep=lambda *_: None)
        service2.run(start_block=10, max_ticks=1, stop_when_synced=True)
        self.assertEqual(s.counts()["swaps"], 1)


if __name__ == "__main__":
    unittest.main()
