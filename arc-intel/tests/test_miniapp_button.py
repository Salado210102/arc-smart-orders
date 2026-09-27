import unittest

from bot.i18n import menu_buttons
from bot.telegram import _inline_keyboard


class MiniAppButtonTests(unittest.TestCase):
    def test_inline_keyboard_types(self):
        kb = _inline_keyboard([
            [{"text": "Open", "web_app": "https://app.basepump.dev/"}],
            [{"text": "A", "data": "cmd:/a"}, {"text": "Docs", "url": "https://d"}],
        ])
        self.assertEqual(kb[0][0], {"text": "Open", "web_app": {"url": "https://app.basepump.dev/"}})
        self.assertEqual(kb[1][0], {"text": "A", "callback_data": "cmd:/a"})
        self.assertEqual(kb[1][1], {"text": "Docs", "url": "https://d"})

    def test_menu_has_app_button_first(self):
        for lang in ("en", "es", "zh"):
            rows = menu_buttons(lang)
            first = rows[0][0]
            self.assertIn("web_app", first)
            self.assertTrue(first["web_app"].startswith("https://"))


if __name__ == "__main__":
    unittest.main()
