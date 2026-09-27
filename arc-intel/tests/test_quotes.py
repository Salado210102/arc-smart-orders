import unittest

from execution.quotes import build_buy_payload, buy_quote, stable_side

USDC = "0x3600000000000000000000000000000000000000"
TOK = "0x" + "a" * 40
EXEC = "0x" + "e" * 40
POOL = {"pool_id": "0x" + "1" * 64, "currency0": USDC, "currency1": TOK, "fee": 3000,
        "tick_spacing": 60, "hooks": "0x" + "0" * 40}


class QuoteTests(unittest.TestCase):
    def test_stable_side_stable_is_c0(self):
        z4o, tok_is_c0 = stable_side(POOL, USDC)
        self.assertTrue(z4o)
        self.assertFalse(tok_is_c0)

    def test_stable_side_stable_is_c1(self):
        z4o, tok_is_c0 = stable_side(POOL, TOK)
        self.assertFalse(z4o)
        self.assertTrue(tok_is_c0)

    def test_stable_not_in_pool(self):
        with self.assertRaises(ValueError):
            stable_side(POOL, "0x" + "b" * 40)

    def test_buy_quote_math(self):
        # $10 USDC at price 0.002 -> 5000 tokens; 2% slippage -> min 4900
        q = buy_quote(amount_in_base=10_000_000, token_price=0.002, token_decimals=18,
                      slippage_pct=2.0)
        self.assertAlmostEqual(q["expected_out"], 5000.0)
        self.assertAlmostEqual(q["min_out"], 4900.0)
        self.assertEqual(q["expected_out_base"], 5000 * 10 ** 18)
        self.assertEqual(q["min_out_base"], 4900 * 10 ** 18)

    def test_buy_quote_bad_inputs(self):
        with self.assertRaises(ValueError):
            buy_quote(amount_in_base=0, token_price=0.002, token_decimals=18, slippage_pct=1)
        with self.assertRaises(ValueError):
            buy_quote(amount_in_base=10_000_000, token_price=0, token_decimals=18, slippage_pct=1)

    def test_build_buy_payload_sides(self):
        p = build_buy_payload(chain_id=5042002, executor=EXEC, pool=POOL, stable=USDC,
                              amount_in_base=10_000_000, min_out_base=4900 * 10 ** 18,
                              recipient=TOK, order_nonce=7, permit_nonce=8, deadline=9999)
        self.assertTrue(p["zeroForOne"])
        msg = p["typedData"]["message"]
        self.assertEqual(msg["permitted"]["token"], USDC)
        self.assertEqual(msg["permitted"]["amount"], 10_000_000)
        self.assertEqual(msg["spender"], EXEC)
        self.assertEqual(msg["witness"]["minOut"], 4900 * 10 ** 18)
        self.assertEqual(msg["witness"]["recipient"], TOK)
        self.assertEqual(msg["witness"]["poolId"], POOL["pool_id"])
        self.assertEqual(p["typedData"]["domain"]["verifyingContract"],
                         "0x000000000022D473030F116dDEE9F6B43aC78BA3")

    def test_build_buy_payload_rejects_foreign_stable(self):
        with self.assertRaises(ValueError):
            build_buy_payload(chain_id=1, executor=EXEC, pool=POOL, stable="0x" + "b" * 40,
                              amount_in_base=1, min_out_base=1, recipient=TOK,
                              order_nonce=1, permit_nonce=1, deadline=1)


if __name__ == "__main__":
    unittest.main()
