import unittest

from indexer.creator_rep import creator_report


class CreatorRepTests(unittest.TestCase):
    def test_empty_creator_returns_empty(self):
        class FakeStorage:
            pass

        self.assertEqual(creator_report(FakeStorage(), ""), {})
        self.assertEqual(creator_report(FakeStorage(), "0x" + "0" * 40), {})
        self.assertEqual(creator_report(FakeStorage(), None), {})


if __name__ == "__main__":
    unittest.main()
