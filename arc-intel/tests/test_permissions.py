import unittest

from security.permissions import (
    create_approval, cancel, confirm, can_execute, mark_executed, is_expired,
    PENDING, CANCELLED, APPROVED, EXPIRED, EXECUTED,
)


def appr(amount=10.0, now=1000, cancel=300, ttl=3600, twofa=50.0):
    return create_approval("a1", "0xuser", {"action": "buy", "token": "0xt"}, amount, now,
                           cancel_seconds=cancel, ttl_seconds=ttl, twofa_threshold=twofa)


class PermissionsTests(unittest.TestCase):
    def test_cancel_window(self):
        a = appr(now=1000)
        self.assertTrue(cancel(a, 1100))
        self.assertEqual(a.status, CANCELLED)
        self.assertFalse(can_execute(a, 1100))

    def test_confirm_blocked_while_window_open(self):
        a = appr(now=1000, cancel=300)
        ok, reason = confirm(a, 1100, twofa_ok=True)
        self.assertFalse(ok)
        self.assertEqual(reason, "cancel_window_open")

    def test_confirm_after_window_low_amount(self):
        a = appr(amount=10.0, now=1000, cancel=300)
        ok, reason = confirm(a, 1400, twofa_ok=False)
        self.assertTrue(ok)
        self.assertEqual(a.status, APPROVED)
        self.assertFalse(a.requires_2fa)

    def test_2fa_required_above_threshold(self):
        a = appr(amount=100.0, now=1000, cancel=300, twofa=50.0)
        self.assertTrue(a.requires_2fa)
        ok, reason = confirm(a, 1400, twofa_ok=False)
        self.assertEqual(reason, "2fa_required")
        ok2, _ = confirm(a, 1400, twofa_ok=True)
        self.assertTrue(ok2)

    def test_expiry(self):
        a = appr(now=1000, cancel=300, ttl=600)
        self.assertTrue(is_expired(a, 1700))
        ok, reason = confirm(a, 1700, twofa_ok=True)
        self.assertFalse(ok)
        self.assertEqual(reason, "expired")
        self.assertEqual(a.status, EXPIRED)

    def test_execute_only_when_approved_and_fresh(self):
        a = appr(amount=10.0, now=1000, cancel=300, ttl=900)
        confirm(a, 1400, twofa_ok=True)
        self.assertTrue(can_execute(a, 1500))
        self.assertTrue(mark_executed(a, 1500))
        self.assertEqual(a.status, EXECUTED)
        self.assertFalse(mark_executed(a, 1600))  # not approved anymore

    def test_cannot_confirm_after_cancel(self):
        a = appr(now=1000)
        cancel(a, 1100)
        ok, reason = confirm(a, 1400, twofa_ok=True)
        self.assertFalse(ok)
        self.assertEqual(reason, "not_pending:cancelled")


if __name__ == "__main__":
    unittest.main()
