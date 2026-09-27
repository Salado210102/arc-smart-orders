import threading
import time
import unittest
import urllib.error

from bot.sender import SenderPool, DirectSender


class FakeTransport:
    def __init__(self, hang_text=None, retry_once=False):
        self.sent = []
        self.hang_text = hang_text
        self.retry_once = retry_once
        self._n = 0
        self._lock = threading.Lock()

    def send(self, chat, text, parse_mode=None, keyboard=None, inline=None,
             remove_keyboard=False, timeout=30):
        if self.retry_once:
            with self._lock:
                self._n += 1
                n = self._n
            if n == 1:
                raise urllib.error.HTTPError("u", 429, "Too Many",
                                             {"Retry-After": "0"}, None)
        if self.hang_text is not None and text == self.hang_text:
            time.sleep(1.0)  # simulate the ~30 s hang we saw live
        with self._lock:
            self.sent.append((text, time.time()))

    def edit_message(self, *a, **k):
        pass


class SenderPoolTests(unittest.TestCase):
    def test_direct_passthrough(self):
        ft = FakeTransport()
        DirectSender(ft).send(1, "hi")
        self.assertEqual([s[0] for s in ft.sent], ["hi"])

    def test_enqueue_is_non_blocking(self):
        ft = FakeTransport(hang_text="X")
        pool = SenderPool(ft, workers=1, timeout=10)
        t0 = time.time()
        pool.send(1, "X")
        self.assertLess(time.time() - t0, 0.2, "send() must return immediately")
        pool.close()

    def test_pool_breaks_the_cascade(self):
        """A hung send must NOT block the next command's reply (the #6/#13 case)."""
        ft = FakeTransport(hang_text="A")
        pool = SenderPool(ft, workers=2, timeout=10)
        t0 = time.time()
        pool.send(1, "A")      # hangs ~1 s
        time.sleep(0.05)
        pool.send(1, "B")      # must be delivered by the other thread
        deadline = time.time() + 2
        while time.time() < deadline and "B" not in [s[0] for s in ft.sent]:
            time.sleep(0.01)
        b_times = [s[1] for s in ft.sent if s[0] == "B"]
        self.assertTrue(b_times, "B was never delivered")
        self.assertLess(b_times[0] - t0, 0.9, "B was blocked behind the hanging send")
        pool.close()

    def test_respects_429_retry_after(self):
        ft = FakeTransport(retry_once=True)
        pool = SenderPool(ft, workers=1, timeout=10)
        pool.send(1, "hello")
        deadline = time.time() + 2
        while time.time() < deadline and not ft.sent:
            time.sleep(0.01)
        self.assertTrue(ft.sent, "429 retry did not deliver")
        self.assertEqual(ft._n, 2)
        pool.close()


if __name__ == "__main__":
    unittest.main()
