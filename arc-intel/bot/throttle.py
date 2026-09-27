"""Rate limiting for Telegram delivery (official limits: <=1 msg/s per chat,
<=20/min per group, ~30 msg/s total). Uses conservative margins and is injectable
for tests (no real sleeping required).
"""
from __future__ import annotations

import time


class Throttle:
    def __init__(self, global_per_sec: float = 20.0, per_chat_per_sec: float = 1.0,
                 time_fn=time.monotonic, sleep_fn=time.sleep):
        self.gmin = (1.0 / global_per_sec) if global_per_sec > 0 else 0.0
        self.cmin = (1.0 / per_chat_per_sec) if per_chat_per_sec > 0 else 0.0
        self.time_fn = time_fn
        self.sleep_fn = sleep_fn
        self.last_global = float("-inf")
        self.last_chat: dict = {}

    def wait(self, chat_id) -> float:
        now = self.time_fn()
        wait = max(self.last_global + self.gmin - now,
                   self.last_chat.get(chat_id, float("-inf")) + self.cmin - now)
        if wait > 0:
            self.sleep_fn(wait)
            now = self.time_fn()
        self.last_global = now
        self.last_chat[chat_id] = now
        return now
