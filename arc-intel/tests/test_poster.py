import unittest

from bot import poster as P


class PosterTests(unittest.TestCase):
    def test_caption(self):
        c = P.poster_caption(1234.56, {"user": "@a", "volume": 1000, "prize": 10}, None,
                             "https://app.basepump.dev/")
        self.assertIn("1,234.56", c)
        self.assertIn("@a", c)
        self.assertIn("sin volumen", c)          # affiliate is None
        self.assertIn("https://app.basepump.dev/", c)

    def test_round_label(self):
        self.assertIn("UTC", P.round_label(0))

    @unittest.skipUnless(P.pillow_available(), "Pillow not installed")
    def test_png_signature(self):
        png = P.render_contest_poster(pozo=100.0, trader={"user": "@a", "volume": 1000, "prize": 5},
                                      affiliate=None)
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        self.assertGreater(len(png), 1000)


if __name__ == "__main__":
    unittest.main()
