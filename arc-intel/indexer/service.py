"""IndexerService: polling loop with reconnect/backoff, cursor, health + file logging."""
from __future__ import annotations

import logging
import time

from .processor import EventProcessor
from .sources import EventSource
from .storage import Storage


def setup_logging(log_path: str) -> logging.Logger:
    logger = logging.getLogger("arc_indexer")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


class IndexerService:
    def __init__(
        self,
        source: EventSource,
        processor: EventProcessor,
        storage: Storage,
        logger: logging.Logger,
        poll_seconds: int = 5,
        max_range_blocks: int = 200,
        sleep=time.sleep,
        now=time.time,
        event_delay_seconds: float = 0.0,
    ):
        self.source = source
        self.processor = processor
        self.storage = storage
        self.logger = logger
        self.poll_seconds = poll_seconds
        self.max_range_blocks = max_range_blocks
        self.sleep = sleep
        self.now = now
        self.event_delay_seconds = event_delay_seconds
        self.processed_total = 0
        self.duplicates_total = 0

    def _head(self) -> int:
        head = getattr(self.source, "head", None)
        return int(head()) if callable(head) else 0

    def run(
        self,
        start_block: int,
        max_ticks: int | None = None,
        stop_when_synced: bool = False,
        max_consecutive_errors: int = 20,
    ) -> None:
        cursor = self.storage.get_cursor(default=start_block - 1)
        if cursor < start_block - 1:
            cursor = start_block - 1
        self.storage.set_cursor(cursor)
        ticks = 0
        consecutive_errors = 0
        while True:
            try:
                head = self._head()
                if head and head <= cursor:
                    self.storage.record_health(0, cursor, 0, self.source.name)
                    if stop_when_synced:
                        break
                    self.sleep(self.poll_seconds)
                    continue
                to = min(head, cursor + self.max_range_blocks) if head else cursor + self.max_range_blocks
                events = self.source.poll(cursor + 1, to)
                got = 0
                for ev in events:
                    res = self.processor.process(ev)
                    got += 1
                    self.processed_total += 1
                    self.duplicates_total += res.duplicates
                    if self.event_delay_seconds:
                        self.sleep(self.event_delay_seconds)
                self.storage.set_cursor(to)
                lag = max(0, head - to) if head else 0
                self.storage.record_health(got, to, lag, self.source.name)
                self.logger.info("tick blocks=%d-%d events=%d lag=%d dup_total=%d",
                                 cursor + 1, to, got, lag, self.duplicates_total)
                cursor = to
                ticks += 1
                consecutive_errors = 0
                if max_ticks is not None and ticks >= max_ticks:
                    break
                if head and head <= cursor:
                    if stop_when_synced:
                        break
                    self.sleep(self.poll_seconds)
            except Exception as exc:
                # Reconnect path: do NOT advance the cursor; retry same range with backoff.
                consecutive_errors += 1
                self.logger.warning("source_error (%d/%d): %s; reconnecting",
                                    consecutive_errors, max_consecutive_errors, exc)
                if consecutive_errors >= max_consecutive_errors:
                    self.logger.error("aborting after %d consecutive errors", consecutive_errors)
                    break
                self.sleep(self.poll_seconds)
        # cursor == last fully processed block; persisted in meta
