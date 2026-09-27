"""Command-reply sender with a tiny worker pool.

Why: the command poller used to send replies inline. When Telegram occasionally
hangs (~30 s, the urllib timeout), the single worker blocked and every later
command queued behind it (the "sometimes it freezes" cascade). Sends now run in
1-2 dedicated threads, so one slow call can't block the poller or the next replies.

Strictly separate from the ALERT path (telegram.dispatch), which keeps its own
throttle/queue and is untouched.
"""
from __future__ import annotations

import queue
import threading
import time
import urllib.error


class DirectSender:
    """Synchronous passthrough (tests/demo). No threads."""

    def __init__(self, transport):
        self.transport = transport

    def send(self, chat, text, parse_mode=None, keyboard=None, inline=None, remove_keyboard=False):
        return self.transport.send(chat, text, parse_mode=parse_mode, keyboard=keyboard,
                                   inline=inline, remove_keyboard=remove_keyboard)

    def edit(self, chat, message_id, text, parse_mode=None, inline=None):
        return self.transport.edit_message(chat, message_id, text, parse_mode=parse_mode,
                                           inline=inline)

    def close(self):
        pass


class SenderPool:
    """A couple of threads draining a queue of send/edit jobs for COMMAND replies."""

    def __init__(self, transport, workers: int = 2, timeout: int = 10):
        self.transport = transport
        self.timeout = timeout
        self.q: queue.Queue = queue.Queue()
        self._threads = [threading.Thread(target=self._run, daemon=True) for _ in range(workers)]
        for t in self._threads:
            t.start()

    def send(self, chat, text, parse_mode=None, keyboard=None, inline=None, remove_keyboard=False):
        self.q.put(("send", (chat, text, parse_mode, keyboard, inline, remove_keyboard)))

    def edit(self, chat, message_id, text, parse_mode=None, inline=None):
        self.q.put(("edit", (chat, message_id, text, parse_mode, inline)))

    def _do(self, kind, args) -> None:
        if kind == "send":
            chat, text, parse_mode, keyboard, inline, rk = args
            try:
                self.transport.send(chat, text, parse_mode=parse_mode, keyboard=keyboard,
                                    inline=inline, remove_keyboard=rk, timeout=self.timeout)
            except urllib.error.HTTPError:
                raise  # 429 / others handled by _run
            except Exception:
                if parse_mode:  # a bad HTML must not drop the message
                    self.transport.send(chat, text, parse_mode=None, keyboard=keyboard,
                                        inline=inline, remove_keyboard=rk, timeout=self.timeout)
        else:
            chat, mid, text, parse_mode, inline = args
            self.transport.edit_message(chat, mid, text, parse_mode=parse_mode,
                                        inline=inline, timeout=self.timeout)

    def _run(self) -> None:
        while True:
            item = self.q.get()
            if item is None:
                self.q.task_done()
                return
            kind, args = item
            try:
                self._do(kind, args)
            except urllib.error.HTTPError as exc:
                if exc.code == 429:
                    ra = exc.headers.get("Retry-After") if exc.headers else None
                    wait = float(ra) if (ra and str(ra).isdigit()) else 2.0
                    time.sleep(min(wait, 30))
                    try:
                        self._do(kind, args)
                    except Exception:
                        pass
            except Exception:
                pass
            finally:
                self.q.task_done()

    def close(self) -> None:
        for _ in self._threads:
            self.q.put(None)
