import unittest

from indexer.token_risk import (analyze_token, classify, extract_minimal_proxy_impl, keccak256,
                                scan_bytecode, selector)


class KeccakTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(keccak256(b"").hex(),
                         "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470")

    def test_abc(self):
        self.assertEqual(keccak256(b"abc").hex(),
                         "4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45")

    def test_selectors(self):
        self.assertEqual(selector("transfer(address,uint256)"), "0xa9059cbb")
        self.assertEqual(selector("mint(address,uint256)"), "0x40c10f19")
        self.assertEqual(selector("owner()"), "0x8da5cb5b")
        self.assertEqual(selector("pause()"), "0x8456cb59")


class ScanTests(unittest.TestCase):
    def test_no_code(self):
        r = scan_bytecode("0x")
        self.assertFalse(r["has_code"])

    def test_extract_minimal_proxy(self):
        code = "0x363d3d373d3d3d363d73" + "5fb8526d5fc7040959cb1a4f5a4dc88bf0468c28" + \
               "5af43d82803e903d91602b57fd5bf3"
        self.assertEqual(extract_minimal_proxy_impl(code),
                         "0x5fb8526d5fc7040959cb1a4f5a4dc88bf0468c28")
        self.assertIsNone(extract_minimal_proxy_impl("0x6080604052"))

    def test_analyze_resolves_minimal_proxy(self):
        proxy = "0x363d3d373d3d3d363d73" + "c" * 40 + "5af43d82803e903d91602b57fd5bf3"
        impl_code = "0x" + selector("mint(address,uint256)")[2:] + selector("pause()")[2:]

        def gc(a):
            return proxy if a == "0x" + "b" * 40 else impl_code

        out = analyze_token("0x" + "b" * 40, get_code=gc, call=lambda t, d: "0x",
                            get_storage=lambda t, s: "0x", use_cache=False)
        self.assertEqual(out["proxy_kind"], "minimal")
        self.assertIn("can_mint", out["reasons"])
        self.assertIn("minimal_proxy", out["reasons"])

    def test_detects_pause_and_mint(self):
        code = "0x" + "60" + selector("pause()")[2:] + "aa" + selector("mint(address,uint256)")[2:]
        r = scan_bytecode(code)
        self.assertTrue(r["has_code"])
        self.assertIn("pause", r["categories"])
        self.assertIn("mint", r["categories"])
        self.assertNotIn("blacklist", r["categories"])


class ClassifyTests(unittest.TestCase):
    def test_blacklist_is_high_honeypot_hint(self):
        c = classify({"has_code": True, "categories": ["blacklist"]}, None, False)
        self.assertEqual(c["level"], "high")
        self.assertTrue(c["honeypot_hint"])

    def test_mint_high(self):
        c = classify({"has_code": True, "categories": ["mint"]}, None, False)
        self.assertEqual(c["level"], "high")
        self.assertIn("can_mint", c["reasons"])

    def test_proxy_high(self):
        c = classify({"has_code": True, "categories": []}, None, True)
        self.assertEqual(c["level"], "high")
        self.assertIn("upgradeable_proxy", c["reasons"])

    def test_owner_active_medium(self):
        c = classify({"has_code": True, "categories": ["control"]}, "0x" + "a" * 40, False)
        self.assertEqual(c["level"], "medium")
        self.assertIn("owner_active", c["reasons"])

    def test_clean_low(self):
        c = classify({"has_code": True, "categories": []}, None, False)
        self.assertEqual(c["level"], "low")


class AnalyzeTests(unittest.TestCase):
    def test_analyze_with_fakes(self):
        code = "0x" + "60" + selector("mint(address,uint256)")[2:] + "00" + selector("pause()")[2:]
        owner_word = "0x" + "0" * 24 + "aa" * 20
        out = analyze_token("0x" + "b" * 40,
                            get_code=lambda t: code,
                            call=lambda t, d: owner_word,
                            get_storage=lambda t, s: "0x" + "0" * 64,
                            use_cache=False)
        self.assertEqual(out["level"], "high")
        self.assertIn("can_mint", out["reasons"])
        self.assertIn("can_pause", out["reasons"])
        self.assertEqual(out["owner"], "0x" + "aa" * 20)
        self.assertTrue(out["heuristic"])

    def test_analyze_no_code(self):
        out = analyze_token("0x" + "b" * 40, get_code=lambda t: "0x",
                            call=lambda t, d: "0x", get_storage=lambda t, s: "0x",
                            use_cache=False)
        self.assertEqual(out["level"], "unknown")

    def test_analyze_rpc_none(self):
        out = analyze_token("0x" + "b" * 40, get_code=lambda t: None,
                            call=lambda t, d: None, get_storage=lambda t, s: None,
                            use_cache=False)
        self.assertEqual(out["level"], "unknown")
        self.assertIn("rpc_unavailable", out["reasons"])


if __name__ == "__main__":
    unittest.main()
