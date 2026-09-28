import unittest

from security.urls import safe_url, is_https, sanitize_dex
from bot.sign_server import _csp


class UrlSanitizerTests(unittest.TestCase):
    def test_allows_https_only(self):
        self.assertEqual(safe_url("https://x.com/a?b=1"), "https://x.com/a?b=1")
        self.assertEqual(safe_url("http://x.com"), "")
        self.assertEqual(safe_url("javascript:alert(1)"), "")
        self.assertEqual(safe_url("JavaScript:alert(1)"), "")
        self.assertEqual(safe_url("data:text/html,<script>alert(1)</script>"), "")
        self.assertEqual(safe_url('"><img src=x onerror=alert(1)>'), "")
        self.assertEqual(safe_url("//x.com"), "")
        self.assertEqual(safe_url(""), "")
        self.assertFalse(is_https("data:image/png;base64,AAAA"))
        self.assertTrue(is_https("https://cdn/x.png"))

    def test_sanitize_dex(self):
        dex = {"logo": "javascript:alert(1)", "embed": "https://dexscreener.com/arc/0x1?embed=1",
               "socials": [{"url": "https://t.me/x", "type": "telegram"},
                           {"url": "data:text/html,x", "type": "web"}],
               "websites": [{"url": "http://x.com", "label": "web"},
                            {"url": "https://ok.com", "label": "web"}]}
        d = sanitize_dex(dex)
        self.assertNotIn("logo", d)                                  # javascript: dropped
        self.assertEqual(d["embed"], "https://dexscreener.com/arc/0x1?embed=1")
        self.assertEqual([s["url"] for s in d["socials"]], ["https://t.me/x"])
        self.assertEqual([s["url"] for s in d["websites"]], ["https://ok.com"])

    def test_csp_has_hash_and_restrictions(self):
        html = b'<html><script type="module">console.log(1)</script></html>'
        csp = _csp(html)
        self.assertIn("default-src 'self'", csp)
        self.assertIn("'sha256-", csp)
        self.assertIn("https://telegram.org", csp)
        self.assertIn("frame-ancestors https://web.telegram.org", csp)
        self.assertNotIn("'unsafe-eval'", csp)


if __name__ == "__main__":
    unittest.main()
