import unittest

from indexer.reputation import (
    FundingEdge, funding_edges_from_transfers, detect_bridge, bootstrap_priors,
)

BRIDGE = "0xbridge00000000000000000000000000000000"


class ReputationTests(unittest.TestCase):
    def test_funding_edges_filters_zero_and_empty(self):
        transfers = [
            {"to_addr": "0xW", "from_addr": "0x0" + "0" * 39, "value": "10", "block_number": 1},
            {"to_addr": "0xW", "from_addr": "0xF", "value": "0", "block_number": 1},
            {"to_addr": "0xW", "from_addr": "0xF", "value": "5", "block_number": 2},
        ]
        edges = funding_edges_from_transfers(transfers)
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0].funder, "0xf")

    def test_detect_bridge(self):
        self.assertEqual(detect_bridge(BRIDGE, {BRIDGE: "ethereum"}), "ethereum")
        self.assertIsNone(detect_bridge("0xunknown", {BRIDGE: "ethereum"}))

    def test_bootstrap_prior_ok(self):
        edges = [FundingEdge("0xNew", BRIDGE, 100)]
        providers = [lambda funder, chain: 0.8 if chain == "ethereum" else None]
        out = bootstrap_priors(edges, providers, bridges={BRIDGE: "ethereum"})
        self.assertEqual(out["0xnew"]["status"], "ok")
        self.assertAlmostEqual(out["0xnew"]["prior"], 0.8)

    def test_bootstrap_unknown_funder_not_available(self):
        edges = [FundingEdge("0xNew", "0xrandom", 100)]
        out = bootstrap_priors(edges, [], bridges={BRIDGE: "ethereum"})
        self.assertEqual(out["0xnew"]["status"], "NOT_AVAILABLE")
        self.assertEqual(out["0xnew"]["reason"], "funder_not_a_known_bridge")

    def test_bootstrap_skips_established_wallets(self):
        edges = [FundingEdge("0xOld", BRIDGE, 100)]
        providers = [lambda f, c: 0.9]
        out = bootstrap_priors(edges, providers, bridges={BRIDGE: "base"},
                               min_history=8, arc_history={"0xold": 20})
        self.assertEqual(out, {})


if __name__ == "__main__":
    unittest.main()
