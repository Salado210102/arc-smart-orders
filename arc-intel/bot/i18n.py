"""i18n for the SNIPER IA bot: English / Spanish / Chinese.

The welcome is HTML (bold labels + anchor links), Maestro-style. Menu labels are localized.
Deeper command outputs fall back to English for now (translation is incremental).
"""
from __future__ import annotations

import os

LANGS = ("en", "es", "zh")
DEFAULT = "en"

DOCS_URL = os.environ.get("ARC_INTEL_DOCS_URL",
                          "https://github.com/Salado210102/arc-smart-orders/tree/main/docs")
REPO_URL = os.environ.get("ARC_INTEL_REPO_URL",
                          "https://github.com/Salado210102/arc-smart-orders")
MINIAPP_URL = os.environ.get("ARC_INTEL_MINIAPP_URL", "https://app.basepump.dev/")

_WELCOME = {
    "en": ("\u2728 <b>Welcome to SNIPER IA</b>, your on-chain safety assistant for Arc!\n\n"
           "\U0001F514 <b>Alerts:</b> follow tokens and get danger alerts.\n"
           "\U0001F50E <b>Check:</b> quick market/activity check for any token.\n"
           "\U0001F4CA <b>Stats:</b> signal value (both faces).\n"
           "\u23F3 <b>Pending:</b> your [PAPER] proposals.\n"
           "\U0001F4BC <b>Positions:</b> your [PAPER] positions.\n"
           "\u2699\uFE0F <b>Settings:</b> customize the bot.\n"
           "\U0001F310 <b>Language:</b> English / Español / 中文.\n\n"
           "\u26A1 <b>Paste a token CA to check it immediately!</b>\n\n"
           "<i>Not financial advice.</i>"),
    "es": ("\u2728 <b>Bienvenido a SNIPER IA</b>, tu asistente de seguridad on-chain para Arc.\n\n"
           "\U0001F514 <b>Alertas:</b> sigue tokens y recibe avisos de peligro.\n"
           "\U0001F50E <b>Consultar:</b> chequeo rápido de cualquier token.\n"
           "\U0001F4CA <b>Estadísticas:</b> valor de la señal (ambas caras).\n"
           "\u23F3 <b>Pendientes:</b> tus propuestas [PAPER].\n"
           "\U0001F4BC <b>Posiciones:</b> tus posiciones [PAPER].\n"
           "\u2699\uFE0F <b>Ajustes:</b> personaliza el bot.\n"
           "\U0001F310 <b>Idioma:</b> English / Español / 中文.\n\n"
           "\u26A1 <b>¡Pega una CA de token para revisarla al instante!</b>\n\n"
           "<i>No es consejo financiero.</i>"),
    "zh": ("\u2728 <b>欢迎使用 SNIPER IA</b> —— 你的 Arc 链上安全助手！\n\n"
           "\U0001F514 <b>提醒：</b>关注代币并接收风险提醒。\n"
           "\U0001F50E <b>查询：</b>快速查询任意代币。\n"
           "\U0001F4CA <b>统计：</b>信号价值（两面）。\n"
           "\u23F3 <b>待处理：</b>你的 [PAPER] 提案。\n"
           "\U0001F4BC <b>持仓：</b>你的 [PAPER] 持仓。\n"
           "\u2699\uFE0F <b>设置：</b>自定义机器人。\n"
           "\U0001F310 <b>语言：</b>English / Español / 中文。\n\n"
           "\u26A1 <b>粘贴代币合约地址即可立即查询！</b>\n\n"
           "<i>非投资建议。</i>"),
}

TEXTS: dict[str, dict[str, str]] = {
    "disclaimer": {
        "en": ("Not financial advice. Alerts are informational, derived from on-chain data, and can be wrong. "
               "Always do your own research."),
        "es": ("No es consejo financiero. Las alertas son informativas, derivadas de datos on-chain, y pueden "
               "fallar. Haz siempre tu propia investigación."),
        "zh": "非投资建议。提醒仅供参考，基于链上数据，可能有误。请自行研究。",
    },
    "paste_prompt": {
        "en": "Paste a token CA (0x + 40 hex) and I'll check it.",
        "es": "Pega una CA de token (0x + 40 hex) y la reviso.",
        "zh": "粘贴代币合约地址（0x + 40 位十六进制），我来查询。",
    },
    "no_subs": {
        "en": "No subscriptions yet. Tap 🔔 My alerts or use /subscribe <token>.",
        "es": "Aún no tienes suscripciones. Toca 🔔 Mis alertas o usa /subscribe <token>.",
        "zh": "还没有订阅。点击 🔔 我的提醒，或使用 /subscribe <token>。",
    },
    "subs_header": {"en": "Subscribed tokens:", "es": "Tokens suscritos:", "zh": "已订阅代币："},
    "language_choose": {"en": "Choose your language:", "es": "Elige tu idioma:", "zh": "请选择语言："},
    "settings_text": {
        "en": "\u2699\uFE0F <b>Alert settings</b>\nTap to turn each alert on/off:",
        "es": "\u2699\uFE0F <b>Ajustes de alertas</b>\nToca para activar/desactivar cada alerta:",
        "zh": "\u2699\uFE0F <b>提醒设置</b>\n点击开启/关闭每种提醒：",
    },
    "language_set": {"en": "Language set to English.", "es": "Idioma cambiado a Español.",
                     "zh": "语言已设置为中文。"},
    "btn_app": {"en": "\U0001F680 Open app", "es": "\U0001F680 Abrir app",
                "zh": "\U0001F680 \u6253\u5f00\u5e94\u7528"},
    "btn_alerts": {"en": "\U0001F514 My alerts", "es": "\U0001F514 Mis alertas", "zh": "\U0001F514 我的提醒"},
    "btn_check": {"en": "\U0001F50E Check token", "es": "\U0001F50E Consultar token", "zh": "\U0001F50E 查询代币"},
    "btn_stats": {"en": "\U0001F4CA Stats", "es": "\U0001F4CA Estadísticas", "zh": "\U0001F4CA 统计"},
    "btn_pending": {"en": "\u23F3 Pending", "es": "\u23F3 Pendientes", "zh": "\u23F3 待处理"},
    "btn_positions": {"en": "\U0001F4BC Positions", "es": "\U0001F4BC Posiciones", "zh": "\U0001F4BC 持仓"},
    "btn_settings": {"en": "\u2699\uFE0F Settings", "es": "\u2699\uFE0F Ajustes", "zh": "\u2699\uFE0F 设置"},
    "btn_language": {"en": "\U0001F1EC\U0001F1E7 Language", "es": "\U0001F1EA\U0001F1F8 Idioma",
                     "zh": "\U0001F1E8\U0001F1F3 语言"},
    "btn_help": {"en": "\u2753 Help", "es": "\u2753 Ayuda", "zh": "\u2753 帮助"},
    "btn_docs": {"en": "\U0001F4DA Documentation", "es": "\U0001F4DA Documentaci\u00F3n",
                 "zh": "\U0001F4DA \u6587\u6863"},
    "btn_wallet": {"en": "\U0001F517 Connect wallet", "es": "\U0001F517 Conectar cartera",
                   "zh": "\U0001F517 连接钱包"},
    "btn_signals": {"en": "\U0001F4C8 Signals \u00B7 soon", "es": "\U0001F4C8 Señales \u00B7 pronto",
                    "zh": "\U0001F4C8 信号 \u00B7 即将"},
    "btn_copytrade": {"en": "\U0001F465 Copytrade \u00B7 soon", "es": "\U0001F465 Copytrade \u00B7 pronto",
                      "zh": "\U0001F465 跟单 \u00B7 即将"},
    "btn_bridge": {"en": "\U0001F309 Bridge \u00B7 soon", "es": "\U0001F309 Bridge \u00B7 pronto",
                   "zh": "\U0001F309 跨链桥 \u00B7 即将"},
    "btn_premium": {"en": "\U0001F48E Premium \u00B7 soon", "es": "\U0001F48E Premium \u00B7 pronto",
                    "zh": "\U0001F48E 高级 \u00B7 即将"},
    "soon_text": {"en": "\U0001F6A7 Coming soon.", "es": "\U0001F6A7 Próximamente.", "zh": "\U0001F6A7 即将上线。"},
    "connect_prompt": {
        "en": "Send your wallet address to connect it (watch-only, no keys):\n/connect 0x\u2026",
        "es": "Envía tu dirección de cartera para conectarla (solo lectura, sin claves):\n/connect 0x\u2026",
        "zh": "发送你的钱包地址以连接（只读，无私钥）：\n/connect 0x\u2026",
    },
    "link_ok": {
        "en": "\u2705 Wallet linked (read-only): <code>{addr}</code>\nI'll auto-follow the tokens in "
              "this wallet (future alerts only). Use /unlink_wallet to remove it.",
        "es": "\u2705 Cartera vinculada (solo lectura): <code>{addr}</code>\nVigilaré automáticamente "
              "los tokens de esta cartera (solo alertas futuras). Usa /unlink_wallet para quitarla.",
        "zh": "\u2705 已关联钱包（只读）：<code>{addr}</code>\n我会自动关注该钱包中的代币（仅未来提醒）。使用 /unlink_wallet 取消。",
    },
    "link_bad": {
        "en": "Invalid address. Usage: /link_wallet 0x + 40 hex.",
        "es": "Dirección inválida. Uso: /link_wallet 0x + 40 hex.",
        "zh": "地址无效。用法：/link_wallet 0x + 40 位十六进制。",
    },
    "unlink_ok": {
        "en": "\U0001F5D1\uFE0F Wallet unlinked. Removed {n} auto-subscription(s). Manual subscriptions stay.",
        "es": "\U0001F5D1\uFE0F Cartera desvinculada. Eliminadas {n} suscripción(es) automáticas. Las manuales se mantienen.",
        "zh": "\U0001F5D1\uFE0F 已取消关联。移除了 {n} 个自动订阅。手动订阅保留。",
    },
    "connect_paste": {
        "en": "\U0001F517 <b>Paste your wallet address</b> in the message bar and hit send "
              "(watch-only, no keys).",
        "es": "\U0001F517 <b>Pega tu dirección de cartera</b> en la barra de mensajes y envía "
              "(solo lectura, sin claves).",
        "zh": "\U0001F517 <b>在消息栏粘贴你的钱包地址</b>并发送（只读，无私钥）。",
    },
    "connect_ok": {
        "en": "\u2705 Wallet connected (watch-only): <code>{addr}</code>",
        "es": "\u2705 Cartera conectada (solo lectura): <code>{addr}</code>",
        "zh": "\u2705 钱包已连接（只读）：<code>{addr}</code>",
    },
    "connect_bad": {
        "en": "Invalid address. Use /connect 0x + 40 hex.",
        "es": "Dirección inválida. Usa /connect 0x + 40 hex.",
        "zh": "地址无效。请使用 /connect 0x + 40 位十六进制。",
    },
    "wallet_none": {
        "en": "\U0001F517 No wallet connected yet. Use <b>Connect wallet</b> or /connect 0x\u2026",
        "es": "\U0001F517 Aún no hay cartera conectada. Usa <b>Conectar cartera</b> o /connect 0x\u2026",
        "zh": "\U0001F517 尚未连接钱包。点击<b>连接钱包</b>或使用 /connect 0x\u2026",
    },
    "wallet_connected": {
        "en": "\U0001F517 Connected wallet (watch-only): <code>{addr}</code>",
        "es": "\U0001F517 Cartera conectada (solo lectura): <code>{addr}</code>",
        "zh": "\U0001F517 已连接钱包（只读）：<code>{addr}</code>",
    },
    "wallet_balances": {
        "en": "\U0001F4B0 Balance: <b>{native:.4f} USDC</b> (native) \u00B7 <b>{usdc:.2f} USDC</b> (ERC-20)",
        "es": "\U0001F4B0 Saldo: <b>{native:.4f} USDC</b> (nativo) \u00B7 <b>{usdc:.2f} USDC</b> (ERC-20)",
        "zh": "\U0001F4B0 余额：<b>{native:.4f} USDC</b>（原生）\u00B7 <b>{usdc:.2f} USDC</b>（ERC-20）",
    },
    "btn_connect": {"en": "\U0001F517 Connect wallet", "es": "\U0001F517 Conectar cartera",
                    "zh": "\U0001F517 连接钱包"},
    "btn_change_wallet": {"en": "\U0001F504 Change wallet", "es": "\U0001F504 Cambiar cartera",
                          "zh": "\U0001F504 更换钱包"},
    "btn_disconnect": {"en": "\u274C Disconnect", "es": "\u274C Desconectar", "zh": "\u274C 断开"},
    "btn_refresh": {"en": "\U0001F501 Refresh", "es": "\U0001F501 Actualizar", "zh": "\U0001F501 刷新"},
    "wallet_disconnected": {"en": "\u2705 Wallet disconnected.", "es": "\u2705 Cartera desconectada.",
                            "zh": "\u2705 钱包已断开。"},
    "wallet_text": {
        "en": ("\U0001F510 <b>Wallet (non-custodial)</b>\n"
               "SNIPER IA never holds your funds or keys. You trade with <b>your own wallet</b> and "
               "sign every order yourself. No deposit/withdraw inside the bot."),
        "es": ("\U0001F510 <b>Cartera (no-custodial)</b>\n"
               "SNIPER IA nunca guarda tus fondos ni tus claves. Operas con <b>tu propia cartera</b> y "
               "firmas tú cada orden. Sin depósito/retiro dentro del bot."),
        "zh": ("\U0001F510 <b>钱包（非托管）</b>\n"
               "SNIPER IA 从不保管你的资金或私钥。你使用<b>自己的钱包</b>交易并亲自签署每笔订单。机器人内无充值/提现。"),
    },
    "btn_check_now": {"en": "\u26A1 Check a token now", "es": "\u26A1 Consultar un token ahora",
                      "zh": "\u26A1 立即查询代币"},
}


def normalize_lang(code) -> str:
    code = (code or "").strip().lower()
    return code if code in LANGS else DEFAULT


def t(key: str, lang: str = DEFAULT) -> str:
    lang = normalize_lang(lang)
    row = TEXTS.get(key, {})
    return row.get(lang) or row.get(DEFAULT) or key


def welcome_text(lang: str) -> str:
    lang = normalize_lang(lang)
    return _WELCOME[lang].format(docs=DOCS_URL, repo=REPO_URL)


def menu_buttons(lang: str = DEFAULT) -> list:
    """Maestro-style inline grid (2 columns) + a full-width bottom button."""
    lang = normalize_lang(lang)

    def b(key, data):
        return {"text": t(key, lang), "data": data}

    return [
        [{"text": t("btn_app", lang), "web_app": MINIAPP_URL}],
        [b("btn_alerts", "cmd:/list"), b("btn_check", "cmd:/check")],
        [b("btn_stats", "cmd:/stats"), b("btn_pending", "cmd:/pending")],
        [b("btn_positions", "cmd:/positions"), b("btn_settings", "cmd:/settings")],
        [b("btn_wallet", "cmd:/wallet"), b("btn_help", "cmd:/help")],
        [b("btn_signals", "soon:Signals"), b("btn_copytrade", "soon:Copytrade")],
        [b("btn_bridge", "soon:Bridge"), b("btn_premium", "soon:Premium")],
        # equal-length, no flags -> identical button widths across clients
        [{"text": "English", "data": "lang:en"},
         {"text": "Español", "data": "lang:es"},
         {"text": "Chinese", "data": "lang:zh"}],
        [b("btn_check_now", "cmd:/check")],
    ]


def language_buttons() -> list:
    return [[{"text": "English", "data": "lang:en"},
             {"text": "Español", "data": "lang:es"},
             {"text": "中文", "data": "lang:zh"}]]
