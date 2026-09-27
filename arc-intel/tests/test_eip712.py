import unittest

from execution import eip712


class Eip712Tests(unittest.TestCase):
    def test_type_string_matches_contract(self):
        self.assertIn("ArcIntelOrder(bytes32 poolId,bool zeroForOne,uint256 minOut,address recipient,"
                      "uint256 orderNonce)", eip712.WITNESS_TYPE_STRING)
        self.assertIn("TokenPermissions(address token,uint256 amount)", eip712.WITNESS_TYPE_STRING)
        self.assertTrue(eip712.WITNESS_TYPE_STRING.startswith("ArcIntelOrder witness)"))

    def test_types_shape(self):
        self.assertEqual(list(eip712.TYPES["ArcIntelOrder"]),
                         [{"name": "poolId", "type": "bytes32"},
                          {"name": "zeroForOne", "type": "bool"},
                          {"name": "minOut", "type": "uint256"},
                          {"name": "recipient", "type": "address"},
                          {"name": "orderNonce", "type": "uint256"}])

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
        self.assertEqual(td["message"]["permitted"]["amount"], 100)

    def test_min_out_from_floor(self):
        self.assertEqual(eip712.min_out_from_floor(1.0, 100, 30), 70)
        self.assertEqual(eip712.min_out_from_floor(1.0, 100, 0), 100)
        self.assertEqual(eip712.min_out_from_floor(1.0, 100, 99), 1)
        with self.assertRaises(ValueError):
            eip712.min_out_from_floor(0, 100, 30)

    def test_nonces(self):
        self.assertIsInstance(eip712.new_nonce(), int)


if __name__ == "__main__":
    unittest.main()
