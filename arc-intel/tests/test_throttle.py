import unittest

from bot.throttle import Throttle


def make_throttle(global_per_sec=20.0, per_chat_per_sec=1.0):
    clock = {"t": 0.0}
    sleeps = []

    def sleep(s):
        sleeps.append(s)
        clock["t"] += s

    thr = Throttle(global_per_sec=global_per_sec, per_chat_per_sec=per_chat_per_sec,
                   time_fn=lambda: clock["t"], sleep_fn=sleep)
    return thr, clock, sleeps


class ThrottleTests(unittest.TestCase):
    def test_per_chat_one_per_second(self):
        thr, clock, sleeps = make_throttle(global_per_sec=1000, per_chat_per_sec=1.0)
        thr.wait("chat1")
        thr.wait("chat1")
        self.assertTrue(sleeps)
        self.assertAlmostEqual(sleeps[-1], 1.0, places=6)

    def test_global_limit(self):
        thr, clock, sleeps = make_throttle(global_per_sec=2.0, per_chat_per_sec=1000)
        thr.wait("a")
        thr.wait("b")
        self.assertTrue(sleeps)
        self.assertAlmostEqual(sleeps[-1], 0.5, places=6)


if __name__ == "__main__":
    unittest.main()
