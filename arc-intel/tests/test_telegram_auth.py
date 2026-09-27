import json
import unittest
from urllib.parse import urlencode

from bot.telegram_auth import sign_init_data, validate_init_data

TOKEN = "123456:TESTTOKENabcdefghijklmnopqrstuvwxyz"


def make(fields):
    f = dict(fields)
    f["hash"] = sign_init_data(f, TOKEN)
    return urlencode(f)


class TelegramAuthTests(unittest.TestCase):
    def test_valid(self):
        init = make({"auth_date": "1000", "user": json.dumps({"id": 42, "first_name": "V"})})
        d = validate_init_data(init, TOKEN, now=1000)
        self.assertIsNotNone(d)
        self.assertEqual(d["user"]["id"], 42)
        self.assertEqual(d["auth_date"], 1000)

    def test_bad_hash(self):
        init = make({"auth_date": "1000", "user": json.dumps({"id": 42})})
        init = init.replace("hash=", "hash=00", 1)
        self.assertIsNone(validate_init_data(init, TOKEN, now=1000))

    def test_tampered_user(self):
        init = make({"auth_date": "1000", "user": json.dumps({"id": 42})})
        tampered = init.replace("%22id%22%3A+42", "%22id%22%3A+99")
        self.assertIsNone(validate_init_data(tampered, TOKEN, now=1000))

    def test_wrong_token(self):
        init = make({"auth_date": "1000", "user": json.dumps({"id": 42})})
        self.assertIsNone(validate_init_data(init, "999:OTHER", now=1000))

    def test_expired(self):
        init = make({"auth_date": "1000", "user": json.dumps({"id": 42})})
        self.assertIsNone(validate_init_data(init, TOKEN, max_age=60, now=5000))

    def test_missing_hash_or_empty(self):
        self.assertIsNone(validate_init_data("", TOKEN))
        self.assertIsNone(validate_init_data("auth_date=1&user=%7B%7D", TOKEN))
        self.assertIsNone(validate_init_data("x=1", ""))


if __name__ == "__main__":
    unittest.main()
