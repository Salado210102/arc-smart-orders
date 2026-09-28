import json
import unittest

from execution import eip712


class Eip712Tests(unittest.TestCase):
    def test_type_string_matches_contract(self):
        # B2: the witness binds `deadline`
        self.assertIn("ArcIntelOrder(bytes32 poolId,bool zeroForOne,uint256 minOut,address recipient,"
                      "uint256 orderNonce,uint256 deadline)", eip712.WITNESS_TYPE_STRING)
        self.assertIn("TokenPermissions(address token,uint256 amount)", eip712.WITNESS_TYPE_STRING)
        self.assertTrue(eip712.WITNESS_TYPE_STRING.startswith("ArcIntelOrder witness)"))

    def test_types_shape(self):
        self.assertEqual(list(eip712.TYPES["ArcIntelOrder"]),
                         [{"name": "poolId", "type": "bytes32"},
                          {"name": "zeroForOne", "type": "bool"},
                          {"name": "minOut", "type": "uint256"},
                          {"name": "recipient", "type": "address"},
                          {"name": "orderNonce", "type": "uint256"},
                          {"name": "deadline", "type": "uint256"}])

    def test_typed_data_domain_and_message(self):
        td = eip712.order_typed_data(
            5042002, "0xEXEC", "0xTOKEN", 100, 1, 1790000000,
            "0x" + "ab" * 32, True, 70, "0xUSER", 7)
        self.assertEqual(td["primaryType"], "PermitWitnessTransferFrom")
        self.assertEqual(td["domain"]["name"], "Permit2")
        self.assertEqual(td["domain"]["chainId"], 5042002)
        self.assertEqual(td["domain"]["verifyingContract"], eip712.PERMIT2)
        w = td["message"]["witness"]
        self.assertEqual(w["minOut"], 70)
        self.assertTrue(w["zeroForOne"])
        self.assertEqual(w["deadline"], 1790000000)     # B2: deadline bound in the witness
        self.assertEqual(td["message"]["permitted"]["amount"], 100)

    def test_min_out_from_floor(self):
        self.assertEqual(eip712.min_out_from_floor(1.0, 100, 30), 70)
        self.assertEqual(eip712.min_out_from_floor(1.0, 100, 0), 100)
        self.assertEqual(eip712.min_out_from_floor(1.0, 100, 99), 1)
        with self.assertRaises(ValueError):
            eip712.min_out_from_floor(0, 100, 30)

    def test_nonces(self):
        self.assertIsInstance(eip712.new_nonce(), int)

    def test_build_sign_payload_direction(self):
        from execution.preorders import build_sign_payload
        p = build_sign_payload(chain_id=5042002, executor="0xEXEC", pool_id="0x" + "ab" * 32,
                               currency0="0xC0", currency1="0xC1", fee=3000, tick_spacing=60,
                               hooks="0x" + "00" * 20, token_in="0xC0", amount_in=100, min_out=70,
                               recipient="0xUSER", order_nonce=7, permit_nonce=1, deadline=1790000000)
        self.assertTrue(p["zeroForOne"])  # token_in == currency0
        self.assertEqual(p["typedData"]["domain"]["chainId"], 5042002)
        self.assertEqual(p["permit"]["amount"], 100)
        q = build_sign_payload(chain_id=5042002, executor="0xEXEC", pool_id="0x" + "ab" * 32,
                               currency0="0xC0", currency1="0xC1", fee=3000, tick_spacing=60,
                               hooks="0x" + "00" * 20, token_in="0xC1", amount_in=5, min_out=4,
                               recipient="0xUSER", order_nonce=8, permit_nonce=2, deadline=1790000000)
        self.assertFalse(q["zeroForOne"])  # token_in == currency1

    def test_executor_call_args(self):
        from execution.preorders import build_sign_payload, executor_call_args
        p = build_sign_payload(chain_id=5042002, executor="0xEXEC", pool_id="0x" + "ab" * 32,
                               currency0="0xC0", currency1="0xC1", fee=3000, tick_spacing=60,
                               hooks="0x" + "00" * 20, token_in="0xC0", amount_in=100, min_out=70,
                               recipient="0xUSER", order_nonce=7, permit_nonce=1, deadline=1790000000)
        preorder = {"sig_payload": json.dumps(p), "user": "0xUSER", "signature": "0xdead"}
        permit_arg, order_arg = executor_call_args(preorder)
        self.assertIn("0xC0", permit_arg)
        self.assertIn("true", order_arg)


if __name__ == "__main__":
    unittest.main()
