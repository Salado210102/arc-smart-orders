import json
import time
import unittest

from bot.store import SubscriptionStore
from bot.commands import command_reply, command_reply_rich, _handle_callback

ADDR = "0x" + "a" * 40
ADDR2 = "0x" + "b" * 40


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.store = SubscriptionStore(":memory:")
        self.exists = lambda t: t in (ADDR, ADDR2)
        self.check = lambda t: f"check {t} ok"

    def reply(self, text, chat=1, now=1000):
        return command_reply(text, chat, self.store, self.exists, self.check, now)

    def tearDown(self):
        self.store.close()

    def test_help(self):
        self.assertIn("SNIPER IA", self.reply("/help"))

    def test_start_onboarding_and_disclaimer(self):
        r = self.reply("/start")
        self.assertIn("SNIPER IA", r)
        self.assertIn("Not financial advice", r)

    def test_new_user_has_no_subscriptions(self):
        self.reply("/start")
        self.assertEqual(self.store.get(1)["tokens"], set())

    def test_subscribe_valid(self):
        r = self.reply(f"/subscribe {ADDR}")
        self.assertIn("Subscribed", r)
        self.assertIn(ADDR, self.store.get(1)["tokens"])
        self.assertEqual(self.store.get(1)["since_block"], 1000)

    def test_subscribe_invalid_address(self):
        self.assertIn("Invalid address", self.reply("/subscribe 0x123"))

    def test_subscribe_unknown_token(self):
        self.assertIn("not found", self.reply("/subscribe 0x" + "f" * 40))

    def test_subscribe_usage(self):
        self.assertIn("Usage", self.reply("/subscribe"))

    def test_unsubscribe(self):
        self.reply(f"/subscribe {ADDR}")
        r = self.reply(f"/unsubscribe {ADDR}")
        self.assertIn("Unsubscribed", r)
        self.assertEqual(self.store.get(1)["tokens"], set())

    def test_settings(self):
        self.assertIn("Kinds set", self.reply("/settings dev_sell,compound"))
        self.assertEqual(self.store.get(1)["kinds"], {"dev_sell", "compound"})
        self.assertIn("Allowed kinds", self.reply("/settings bad_kind"))

    def test_list(self):
        self.reply(f"/subscribe {ADDR}")
        self.assertIn(ADDR[:6], self.reply("/list"))

    def test_limit_per_user(self):
        for i in range(SubscriptionStore.MAX_TOKENS):
            self.store.add_token(1, "0x" + f"{i:040x}", now_block=0)
        r = self.reply(f"/subscribe {ADDR}")
        self.assertIn("limit", r.lower())

    def test_unknown_command(self):
        self.assertIn("Unknown", self.reply("/nonsense"))

    def test_stats_two_faces_and_low_n(self):
        for i in range(12):
            h = {"1h": {"benefit_delayed": 0.03, "benefit_instant": 0.04, "stale": False},
                 "6h": {"benefit_delayed": 0.05, "benefit_instant": 0.06, "stale": False},
                 "24h": {"benefit_delayed": 0.05, "benefit_instant": 0.06, "stale": False}}
            self.store.save_paper_outcome("dev_sell", f"0xt{i}", i, 45, 1000 + i, json.dumps(h))
        # one big adverse (token pumped ~11x after alert -> missed upside, not capital loss)
        h = {"1h": {"benefit_delayed": -10.0, "benefit_instant": -10.0, "stale": False}}
        self.store.save_paper_outcome("dev_sell", "0xtpump", 99, 45, 1100, json.dumps(h))
        for i in range(2):
            h = {"1h": {"benefit_delayed": 0.01, "benefit_instant": 0.01, "stale": False}}
            self.store.save_paper_outcome("compound", f"0xc{i}", i, 45, 2000 + i, json.dumps(h))
        r = self.reply("/stats")
        self.assertIn("dev_sell", r)
        self.assertIn("CI", r)
        self.assertIn("opportunity cost", r)
        self.assertIn("not a capital loss", r)
        self.assertIn("upside", r)
        self.assertNotIn("-1048", r)          # never the raw scary number
        self.assertIn("compound", r)
        self.assertIn("not enough data", r)

    def test_subscribe_recent(self):
        def recent(n, window_blocks=None):
            return [ADDR, ADDR2]

        r = command_reply("/subscribe_recent 2", 1, self.store, self.exists, self.check, 1000,
                          recent_fn=recent)
        self.assertIn("Subscribed to 2", r)
        self.assertEqual(self.store.get(1)["tokens"], {ADDR, ADDR2})

    def test_subscribe_recent_respects_limit(self):
        for i in range(SubscriptionStore.MAX_TOKENS):
            self.store.add_token(1, "0x" + f"{i:040x}", now_block=0)

        def recent(n, window_blocks=None):
            return [ADDR]

        r = command_reply("/subscribe_recent", 1, self.store, self.exists, self.check, 0,
                          recent_fn=recent)
        self.assertIn("skipped", r.lower())


    # --- UI enhancements: keyboard labels, CA paste, menu, positions, disclaimer ---

    def test_label_my_alerts_maps_to_list(self):
        self.reply(f"/subscribe {ADDR}")
        self.assertIn(ADDR[:6], self.reply("\U0001F4CB My alerts"))

    def test_paste_address_triggers_check(self):
        self.assertIn("check", self.reply(ADDR))

    def test_check_prompt_when_no_arg(self):
        self.assertIn("Paste a token CA", self.reply("/check"))

    def test_disclaimer(self):
        self.assertIn("Not financial advice", self.reply("/disclaimer"))

    def test_positions_empty(self):
        self.assertIn("[PAPER]", self.reply("/positions"))

    def test_positions_lists_approvals(self):
        aid = self.store.create_approval(1, ADDR, "dev_sell", "sell", 10.0, 5, 1000, 1300, 2000,
                                         False, None)
        r = self.reply("/positions")
        self.assertIn(f"#{aid}", r)
        self.assertIn(ADDR, r)

    def test_rich_start_carries_inline_grid(self):
        r = command_reply_rich("/start", 1, self.store, self.exists, self.check, 1000)
        self.assertIsInstance(r, dict)
        self.assertTrue(r["inline"])
        # Maestro-style grid: 12 rows; row 0 is the live prize-pool button, then the Mini App
        self.assertEqual(len(r["inline"]), 12)
        self.assertEqual(r["inline"][0][0]["data"], "cmd:/pozo")
        self.assertTrue(any("web_app" in b for row in r["inline"] for b in row))
        self.assertIn("SNIPER IA", r["text"])

    def test_pozo_command_and_menu_line(self):
        self.store.record_fill("tx1:buy", 1, ADDR, "buy", 1.0, 100.0, ts=int(time.time()))
        self.assertIn("Pool", self.reply("/pozo"))
        r = command_reply_rich("/start", 1, self.store, self.exists, self.check, 1000)
        self.assertIn("Prize pool", r["text"])

    def test_portfolio_screen_rugged_and_sell(self):
        self.store.save_custody(1, "0x" + "a" * 40, "enc")
        self.store.add_holding(1, ADDR)
        self.store.record_fill("t:buy", 1, ADDR, "buy", 10.0, 100.0, ts=1)
        self.store.add_alert({"token": ADDR, "kind": "liquidity_removal", "severity": "high",
                              "block": 9, "message": "lp"})
        r = command_reply_rich("/portfolio", 1, self.store, self.exists, self.check, 1000,
                               paper_price_fn=lambda t: [(1, 0.5)])
        self.assertIn("RUGGED", r["text"])
        self.assertTrue(any(b.get("data", "").startswith("custsell:")
                            for row in r["inline"] for b in row))

    def test_custsell_callback(self):
        calls = []

        def fake_sell(chat, token, pct):
            calls.append((chat, token, pct))
            return "ok"

        r = _handle_callback(f"custsell:{ADDR}:50", 1, self.store, self.exists, self.check, 1000,
                             custsell_fn=fake_sell)
        self.assertIn("Sold", r["text"])
        self.assertEqual(calls, [(1, ADDR, 50.0)])

    def test_portfolio_needs_custody(self):
        self.assertIn("bot wallet", self.reply("/portfolio"))

    def test_security_enroll_and_addaddr(self):
        import os
        from cryptography.fernet import Fernet
        from bot import totp as T
        from execution import signer
        old = os.environ.get("ARC_INTEL_SESSION_ENC_KEY")
        os.environ["ARC_INTEL_SESSION_ENC_KEY"] = Fernet.generate_key().decode()
        try:
            self.assertIn("2FA", self.reply("/security"))
            secret = signer.decrypt(1, self.store.get_totp(1), "totp")
            self.assertIn("registered", self.reply(f"/addaddr {ADDR} {T.code(secret)}"))
            self.assertIsNotNone(self.store.get_custody_addr(1, ADDR))
            self.assertIn("Bad", self.reply(f"/addaddr {ADDR2} 000000"))
        finally:
            if old is None:
                os.environ.pop("ARC_INTEL_SESSION_ENC_KEY", None)
            else:
                os.environ["ARC_INTEL_SESSION_ENC_KEY"] = old

    def test_token_risk_status(self):
        self.store.add_alert({"token": ADDR, "kind": "liquidity_removal", "severity": "high",
                              "block": 5, "message": "lp removed"})
        self.assertEqual(self.store.token_risk_status(ADDR), "rugged")
        self.assertEqual(self.store.token_risk_status(ADDR2), "")
        self.store.add_alert({"token": ADDR2, "kind": "dev_sell", "severity": "high",
                              "block": 6, "message": "dev sold"})
        self.assertEqual(self.store.token_risk_status(ADDR2), "dev_sell")

    def test_referral_screen(self):
        r = command_reply_rich("/referral", 1, self.store, self.exists, self.check, 1000)
        self.assertEqual(r["parse_mode"], "HTML")
        self.assertIn("30%", r["text"])
        self.assertIn(self.store.get_referral_code(1), r["text"])
        # a button to open the per-referral stats
        flat = [b for row in r["inline"] for b in row]
        self.assertTrue(any(b.get("data") == "ref:stats" for b in flat))

    def test_copytrade_command_lifecycle(self):
        self.assertIn("Copy-trade", self.reply("/copytrade"))
        # add a wallet via the inline flow (copy:add -> paste address)
        r = _handle_callback("copy:add", 1, self.store, self.exists, self.check, 1000)
        self.assertIn("Paste", r["text"])
        command_reply_rich(ADDR, 1, self.store, self.exists, self.check, 1000)
        self.assertIsNotNone(self.store.get_copy_wallet(1, ADDR))
        # filters screen + toggle mirror sells
        f = _handle_callback("copy:filters", 1, self.store, self.exists, self.check, 1000)
        self.assertIn("filters", f["text"].lower())
        _handle_callback("copy:mirror", 1, self.store, self.exists, self.check, 1000)
        self.assertFalse(self.store.get_copy_settings(1)["mirror_sells"])
        # edit min buy
        _handle_callback("copy:set:min", 1, self.store, self.exists, self.check, 1000)
        command_reply_rich("50", 1, self.store, self.exists, self.check, 1000)
        self.assertEqual(self.store.get_copy_settings(1)["min_buy_usdc"], 50.0)
        # remove the wallet
        _handle_callback(f"copy:rm:{ADDR}", 1, self.store, self.exists, self.check, 1000)
        self.assertIsNone(self.store.get_copy_wallet(1, ADDR))

    def test_referral_stats_button_and_screen(self):
        code = self.store.ensure_referral_code(1, "ABCDEFGH")
        self.store.bind_referral(2, 1, code)
        self.store.record_fill("t1:buy", 2, ADDR, "buy", 1.0, 100.0)
        r = _handle_callback("ref:stats", 1, self.store, self.exists, self.check, 1000)
        self.assertEqual(r["parse_mode"], "HTML")
        self.assertTrue(r.get("edit"))
        self.assertIn("0.30", r["text"])            # 30% of a $1.00 fee
        self.assertIn("2", r["text"])               # the referred user id
        back = [b for row in r["inline"] for b in row]
        self.assertTrue(any(b.get("data") == "ref:home" for b in back))
        home = _handle_callback("ref:home", 1, self.store, self.exists, self.check, 1000)
        self.assertIn(code, home["text"])

    def test_wallet_panel_watch_only_and_custody(self):
        r = self.reply("/wallet")
        self.assertIn("watch-only", r)
        self.assertIn("custody", r)

    def test_connect_wallet(self):
        self.assertIn("No wallet", self.reply("/wallet"))
        r = self.reply(f"/connect {ADDR}")
        self.assertIn(ADDR, r)
        self.assertEqual(self.store.get_wallet(1), ADDR)
        self.assertIn(ADDR, self.reply("/wallet"))

    def test_connect_bad_address(self):
        self.assertIn("/connect", self.reply("/connect 0x123"))

    def test_wallet_screen_buttons(self):
        from bot import tokenmeta as _tm
        _tm.native_balance_eth = lambda a: 0
        _tm.erc20_balance = lambda a: 0.0
        self.store.set_wallet(1, ADDR)
        r = command_reply_rich("/wallet", 1, self.store, self.exists, self.check, 1000)
        self.assertIsInstance(r, dict)
        self.assertTrue(r["inline"])

    def test_connect_button_then_paste_address(self):
        # pressing "Connect wallet" arms connect mode
        _handle_callback("cmd:/connect", 1, self.store, self.exists, self.check, 1000)
        self.assertEqual(str(self.store.get_state("awaiting_wallet:1")), "1")
        # pasting a bare address connects it (no /connect typed)
        r = command_reply(ADDR, 1, self.store, self.exists, self.check, 1000)
        self.assertIn(ADDR, r)
        self.assertEqual(self.store.get_wallet(1), ADDR)
        self.assertEqual(str(self.store.get_state("awaiting_wallet:1")), "0")

    def test_link_wallet_command(self):
        r = self.reply(f"/link_wallet {ADDR}")
        self.assertIn("linked", r.lower())
        self.assertEqual(self.store.get_linked_wallet(1), ADDR)
        self.assertEqual(self.store.get_wallet(1), ADDR)

    def test_link_wallet_invalid_address(self):
        self.assertIn("Invalid", self.reply("/link_wallet 0x123"))

    def test_unlink_wallet_command(self):
        self.reply(f"/link_wallet {ADDR}")
        self.store.add_auto_sub(1, ADDR, now_block=0)
        r = self.reply("/unlink_wallet")
        self.assertIn("unlinked", r.lower())
        self.assertEqual(self.store.get_linked_wallet(1), "")

    def test_wallet_disconnect(self):
        self.store.set_wallet(1, ADDR)
        _handle_callback("disconnect", 1, self.store, self.exists, self.check, 1000)
        self.assertEqual(self.store.get_wallet(1), "")

    def test_help_has_docs_link(self):
        r = command_reply_rich("/help", 1, self.store, self.exists, self.check, 1000)
        self.assertIsInstance(r, dict)
        self.assertTrue(any("url" in b for row in r["inline"] for b in row))

    def test_check_has_buy_sell_buttons(self):
        r = command_reply_rich(f"/check {ADDR}", 1, self.store, self.exists, self.check, 1000)
        self.assertIsInstance(r, dict)
        datas = [b.get("data", "") for row in r["inline"] for b in row]
        self.assertTrue(any("buymenu:" in d for d in datas))

    def test_buy_menu_and_amount(self):
        price_fn = lambda t: [(1, 0.5)]
        r = _handle_callback(f"buymenu:{ADDR}", 1, self.store, self.exists, self.check, 1000,
                             paper_price_fn=price_fn)
        self.assertIsInstance(r, dict)
        _handle_callback(f"buyamt:{ADDR}:50", 1, self.store, self.exists, self.check, 1000,
                         paper_price_fn=price_fn)
        self.assertGreater(self.store.get_position(1, ADDR)["qty"], 0)

    def test_sell_pct_buttons(self):
        price_fn = lambda t: [(1, 1.0)]
        _handle_callback(f"buyamt:{ADDR}:50", 1, self.store, self.exists, self.check, 1000,
                         paper_price_fn=price_fn)
        r = _handle_callback(f"sellpct:{ADDR}:25", 1, self.store, self.exists, self.check, 1000,
                             paper_price_fn=price_fn)
        self.assertIn("25%", r)
        self.assertAlmostEqual(self.store.get_position(1, ADDR)["qty"], 37.5)

    def test_buy_custom_amount_flow(self):
        price_fn = lambda t: [(1, 2.0)]
        _handle_callback(f"buycustom:{ADDR}", 1, self.store, self.exists, self.check, 1000,
                         paper_price_fn=price_fn)
        self.assertEqual(str(self.store.get_state("awaiting_amount:1")), ADDR)
        r = command_reply("30", 1, self.store, self.exists, self.check, 1000, paper_price_fn=price_fn)
        self.assertIn("Bought", r)
        self.assertAlmostEqual(self.store.get_position(1, ADDR)["qty"], 15.0)

    def test_paper_buy_then_sell(self):
        price_fn = lambda t: [(1, 0.5)]
        r1 = _handle_callback(f"buy:{ADDR}", 1, self.store, self.exists, self.check, 1000,
                              paper_price_fn=price_fn)
        self.assertIn("Bought", r1)
        self.assertGreater(self.store.get_position(1, ADDR)["qty"], 0)
        r2 = _handle_callback(f"sell:{ADDR}", 1, self.store, self.exists, self.check, 1000,
                              paper_price_fn=price_fn)
        self.assertIn("Sold", r2)
        self.assertAlmostEqual(self.store.get_position(1, ADDR)["qty"], 0.0)

    def test_protect_flow_arms_preorder(self):
        price_fn = lambda t: [(1, 1.0)]
        _handle_callback(f"buyamt:{ADDR}:100", 1, self.store, self.exists, self.check, 1000,
                         paper_price_fn=price_fn)
        r = _handle_callback(f"protectfloor:{ADDR}:50:30", 1, self.store, self.exists, self.check,
                             1000, paper_price_fn=price_fn)
        self.assertIn("ARMED", r)
        pos = self.store.preorders_for_token(ADDR)
        self.assertEqual(len(pos), 1)
        self.assertEqual(pos[0]["pct"], 50.0)

    def test_fire_preorders_sells_on_alert(self):
        from bot.commands import fire_preorders
        price_fn = lambda t: [(1, 1.0)]
        _handle_callback(f"buyamt:{ADDR}:100", 1, self.store, self.exists, self.check, 1000,
                         paper_price_fn=price_fn)
        _handle_callback(f"protectfloor:{ADDR}:100:30", 1, self.store, self.exists, self.check,
                         1000, paper_price_fn=price_fn)

        class T:
            def send(self, *a, **k):
                pass

        class Th:
            def wait(self, *a, **k):
                pass

        n = fire_preorders(self.store, [{"kind": "dev_sell", "token": ADDR}], T(), Th(), price_fn)
        self.assertEqual(n, 1)
        self.assertAlmostEqual(self.store.get_position(1, ADDR)["qty"], 0.0)
        self.assertEqual(self.store.preorders_for_token(ADDR), [])

    def test_settings_screen_has_toggles(self):
        r = command_reply_rich("/settings", 1, self.store, self.exists, self.check, 1000)
        self.assertIsInstance(r, dict)
        self.assertEqual(len(r["inline"]), 7)   # 6 alert kinds + Auto-Protect
        self.assertTrue(any(b.get("data") == "setap" for row in r["inline"] for b in row))

    def test_settings_autoprotect_toggle(self):
        self.assertEqual(self.store.get_state("autoprotect:1", "1"), "1")
        _handle_callback("setap", 1, self.store, self.exists, self.check, 1000)
        self.assertEqual(self.store.get_state("autoprotect:1", "1"), "0")

    def test_settings_toggle_off_one(self):
        _handle_callback("setkind:dev_sell", 1, self.store, self.exists, self.check, 1000)
        self.assertEqual(self.store.get(1)["kinds"],
                         {"compound", "liquidity_removal", "large_sell", "whale_buy", "graduation"})

    def test_settings_toggle_all_off_mutes(self):
        for k in ("dev_sell", "compound", "liquidity_removal", "large_sell", "whale_buy",
                  "graduation"):
            _handle_callback(f"setkind:{k}", 1, self.store, self.exists, self.check, 1000)
        self.assertEqual(self.store.get(1)["kinds"], {"none"})

    def test_soon_callback(self):
        r = _handle_callback("soon:Signals", 1, self.store, self.exists, self.check, 1000)
        self.assertIn("soon", r.lower())

    def test_list_shows_symbol(self):
        self.reply(f"/subscribe {ADDR}")
        r = command_reply("/list", 1, self.store, self.exists, self.check, 1000,
                          symbol_fn=lambda t: "PEPE")
        self.assertIn("PEPE", r)
        self.assertIn(ADDR[:6], r)

    def test_rich_non_menu_is_plain_string(self):
        self.assertIsInstance(self.reply("/stats"), str)
        self.assertIsInstance(command_reply_rich("/disclaimer", 1, self.store, self.exists,
                                                 self.check, 1000), str)

    def test_language_command_returns_three_options(self):
        r = command_reply_rich("/language", 1, self.store, self.exists, self.check, 1000)
        self.assertIsInstance(r, dict)
        self.assertEqual(len(r["inline"][0]), 3)  # English / Español / 中文

    def test_language_callback_sets_lang_and_menu(self):
        r = _handle_callback("lang:es", 1, self.store, self.exists, self.check, 1000)
        self.assertIsInstance(r, dict)
        self.assertEqual(self.store.get_state("lang:1"), "es")
        self.assertIn("Idioma", r["text"])

    def test_welcome_is_localized(self):
        _handle_callback("lang:zh", 1, self.store, self.exists, self.check, 1000)
        r = command_reply_rich("/start", 1, self.store, self.exists, self.check, 1000)
        self.assertIn("SNIPER IA", r["text"])
        self.assertIn("\u6b22\u8fce", r["text"])  # "欢迎"


if __name__ == "__main__":
    unittest.main()
