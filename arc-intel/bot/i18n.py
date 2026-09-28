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
    "btn_autoprotect": {"en": "\U0001F6E1\uFE0F Auto-Protect: {v}", "es": "\U0001F6E1\uFE0F Auto-Protect: {v}",
                        "zh": "\U0001F6E1\uFE0F \u81ea\u52a8\u4fdd\u62a4\uff1a{v}"},
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
    "btn_copytrade": {"en": "\U0001F465 Copytrade", "es": "\U0001F465 Copytrade",
                      "zh": "\U0001F465 跟单"},
    "btn_bridge": {"en": "\U0001F309 Bridge", "es": "\U0001F309 Bridge",
                   "zh": "\U0001F309 跨链桥"},
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
        "en": ("\U0001F517 <b>Linked wallet (watch-only)</b>\n"
               "Link your own wallet (read-only, no keys) to auto-follow the tokens it holds "
               "(future alerts only).\n\n"
               "\U0001F45B To <b>trade instantly</b>, create your <b>bot wallet</b> (custody) in the "
               "Mini App \u2192 Cartera. Deposit USDC and the bot operates for you; withdraw anytime."),
        "es": ("\U0001F517 <b>Cartera enlazada (solo lectura)</b>\n"
               "Enlaza tu propia cartera (solo lectura, sin claves) para seguir automáticamente los "
               "tokens que tenga (solo alertas futuras).\n\n"
               "\U0001F45B Para <b>operar al instante</b>, crea tu <b>wallet del bot</b> (custodia) en la "
               "Mini App \u2192 Cartera. Deposita USDC y el bot opera por ti; retira cuando quieras."),
        "zh": ("\U0001F517 <b>已关联钱包（只读）</b>\n"
               "关联你自己的钱包（只读，无私钥）以自动关注其中的代币（仅未来提醒）。\n\n"
               "\U0001F45B 想要<b>即时交易</b>，请在 Mini App \u2192 钱包 中创建<b>机器人钱包</b>（托管）。"
               "存入 USDC，机器人代为操作；随时可提取。"),
    },
    "btn_check_now": {"en": "\u26A1 Check a token now", "es": "\u26A1 Consultar un token ahora",
                      "zh": "\u26A1 立即查询代币"},
    "btn_referral": {"en": "\U0001F381 Referrals", "es": "\U0001F381 Referidos", "zh": "\U0001F381 推荐"},
    "referral_text": {
        "en": ("\U0001F381 <b>Referrals \u2014 earn 30% for life</b>\n"
               "Invite friends and earn <b>30%</b> of the 1% fee on everything they trade, forever.\n\n"
               "Your code: <code>{code}</code>\n"
               "Your link: {link}\n\n"
               "\U0001F465 Invited: <b>{referred}</b>\n"
               "\U0001F4B5 Accrued: <b>${accrued:.2f}</b>\n"
               "\u23F3 Pending payout: <b>${pending:.2f}</b>\n\n"
               "<i>Paid in USDC. Not financial advice.</i>"),
        "es": ("\U0001F381 <b>Referidos \u2014 gana 30% de por vida</b>\n"
               "Invita amigos y gana el <b>30%</b> de la comisión del 1% de todo lo que operen, siempre.\n\n"
               "Tu código: <code>{code}</code>\n"
               "Tu enlace: {link}\n\n"
               "\U0001F465 Invitados: <b>{referred}</b>\n"
               "\U0001F4B5 Acumulado: <b>${accrued:.2f}</b>\n"
               "\u23F3 Pendiente de pago: <b>${pending:.2f}</b>\n\n"
               "<i>Se paga en USDC. No es consejo financiero.</i>"),
        "zh": ("\U0001F381 <b>推荐 \u2014 终身赚取 30%</b>\n"
               "邀请好友，终身赚取其每笔交易 1% 手续费的 <b>30%</b>。\n\n"
               "你的代码：<code>{code}</code>\n"
               "你的链接：{link}\n\n"
               "\U0001F465 已邀请：<b>{referred}</b>\n"
               "\U0001F4B5 累计：<b>${accrued:.2f}</b>\n"
               "\u23F3 待支付：<b>${pending:.2f}</b>\n\n"
               "<i>以 USDC 支付。非投资建议。</i>"),
    },
    "referral_nolink": {
        "en": "Your code: <code>{code}</code> (share it; the bot will attribute new users).",
        "es": "Tu código: <code>{code}</code> (compártelo; el bot atribuirá a los nuevos usuarios).",
        "zh": "你的代码：<code>{code}</code>（分享它，机器人将归因新用户）。",
    },
    "btn_ref_stats": {"en": "\U0001F4CA Referral stats", "es": "\U0001F4CA Estadísticas",
                      "zh": "\U0001F4CA 推荐统计"},
    "btn_ref_back": {"en": "\u2B05\uFE0F Back", "es": "\u2B05\uFE0F Volver", "zh": "\u2B05\uFE0F 返回"},
    "referral_stats_text": {
        "en": ("\U0001F4CA <b>Your referral stats</b>\n\n"
               "\U0001F465 Invited: <b>{referred}</b>\n"
               "\U0001F4B5 Accrued: <b>${accrued:.2f}</b>\n"
               "\u23F3 Pending payout: <b>${pending:.2f}</b>\n\n"
               "<b>By referred user</b>\n{detail}"),
        "es": ("\U0001F4CA <b>Estadísticas de tus referidos</b>\n\n"
               "\U0001F465 Invitados: <b>{referred}</b>\n"
               "\U0001F4B5 Acumulado: <b>${accrued:.2f}</b>\n"
               "\u23F3 Pendiente de pago: <b>${pending:.2f}</b>\n\n"
               "<b>Por usuario referido</b>\n{detail}"),
        "zh": ("\U0001F4CA <b>你的推荐统计</b>\n\n"
               "\U0001F465 已邀请：<b>{referred}</b>\n"
               "\U0001F4B5 累计：<b>${accrued:.2f}</b>\n"
               "\u23F3 待支付：<b>${pending:.2f}</b>\n\n"
               "<b>按被推荐用户</b>\n{detail}"),
    },
    "referral_stats_empty": {
        "en": "No referred volume yet. Share your link to start earning.",
        "es": "Aún no hay volumen referido. Comparte tu enlace para empezar a ganar.",
        "zh": "暂无推荐交易量。分享你的链接即可开始赚取。",
    },
    "copy_title": {
        "en": "\U0001F3AE <b>Copy-trade</b>\nMirrors the buys of tracked wallets with your bot wallet.",
        "es": "\U0001F3AE <b>Copy-trade</b>\nReplica las compras de las wallets seguidas con tu wallet del bot.",
        "zh": "\U0001F3AE <b>\u8ddf\u5355</b>\n\u7528\u4f60\u7684\u673a\u5668\u4eba\u94b1\u5305\u590d\u5236\u8ddf\u8e2a\u94b1\u5305\u7684\u4e70\u5165\u3002",
    },
    "copy_hint": {
        "en": "Filters: min size, max open, proportional sizing, mirror sells.",
        "es": "Filtros: tama\u00f1o m\u00ednimo, m\u00e1x. abiertas, tama\u00f1o proporcional, replicar ventas.",
        "zh": "\u8fc7\u6ee4\uff1a\u6700\u5c0f\u91d1\u989d\u3001\u6700\u5927\u6301\u4ed3\u3001\u6bd4\u4f8b\u4ed3\u4f4d\u3001\u8ddf\u5356\u3002",
    },
    "copy_none": {
        "en": "No tracked wallets yet.",
        "es": "A\u00fan no sigues ninguna wallet.",
        "zh": "\u5c1a\u672a\u8ddf\u8e2a\u4efb\u4f55\u94b1\u5305\u3002",
    },
    "copy_add_wallet": {"en": "\u2795 Add wallet", "es": "\u2795 A\u00f1adir wallet",
                        "zh": "\u2795 \u6dfb\u52a0\u94b1\u5305"},
    "copy_filters": {"en": "\U0001F39B\uFE0F Filters", "es": "\U0001F39B\uFE0F Filtros",
                     "zh": "\U0001F39B\uFE0F \u8fc7\u6ee4\u5668"},
    "copy_paste_wallet": {
        "en": "\U0001F4E5 Paste the wallet address to track (0x + 40 hex).",
        "es": "\U0001F4E5 Pega la direcci\u00f3n de la wallet a seguir (0x + 40 hex).",
        "zh": "\U0001F4E5 \u7c98\u8d34\u8981\u8ddf\u8e2a\u7684\u94b1\u5305\u5730\u5740\uff080x + 40 \u4f4d\u5341\u516d\u8fdb\u5236\uff09\u3002",
    },
    "copy_enter_value": {
        "en": "\u270F\uFE0F Send the value (number).",
        "es": "\u270F\uFE0F Env\u00eda el valor (n\u00famero).",
        "zh": "\u270F\uFE0F \u53d1\u9001\u6570\u503c\u3002",
    },
    "copy_bad": {
        "en": "Invalid address. Send 0x + 40 hex.",
        "es": "Direcci\u00f3n inv\u00e1lida. Env\u00eda 0x + 40 hex.",
        "zh": "\u5730\u5740\u65e0\u6548\u3002\u8bf7\u53d1\u9001 0x + 40 \u4f4d\u5341\u516d\u8fdb\u5236\u3002",
    },
    "copy_bad_num": {
        "en": "Invalid number.",
        "es": "N\u00famero inv\u00e1lido.",
        "zh": "\u6570\u503c\u65e0\u6548\u3002",
    },
    "copy_filters_text": {
        "en": ("\U0001F39B\uFE0F <b>Copy-trade filters</b> (apply to every tracked wallet)\n"
               "\u2022 Copy only buys \u2265 <b>${min}</b> by the leader\n"
               "\u2022 Max open copied positions: <b>{maxopen}</b>\n"
               "\u2022 Size: <b>{sizing}</b> (flat ${size})\n"
               "\u2022 Mirror sells: <b>{mirror}</b>\n\n"
               "Protection defaults (TP / SL / trailing / dump guard) are attached to every copied fill."),
        "es": ("\U0001F39B\uFE0F <b>Filtros de copy-trade</b> (aplican a todas las wallets)\n"
               "\u2022 Copiar solo compras \u2265 <b>${min}</b> del l\u00edder\n"
               "\u2022 M\u00e1x. posiciones abiertas: <b>{maxopen}</b>\n"
               "\u2022 Tama\u00f1o: <b>{sizing}</b> (flat ${size})\n"
               "\u2022 Replicar ventas: <b>{mirror}</b>\n\n"
               "La protecci\u00f3n por defecto (TP / SL / trailing / dump guard) se aplica a cada compra copiada."),
        "zh": ("\U0001F39B\uFE0F <b>\u8ddf\u5355\u8fc7\u6ee4\u5668</b>\uff08\u9002\u7528\u4e8e\u6240\u6709\u94b1\u5305\uff09\n"
               "\u2022 \u4ec5\u590d\u5236\u9886\u8896\u2265 <b>${min}</b> \u7684\u4e70\u5165\n"
               "\u2022 \u6700\u5927\u6301\u4ed3\uff1a<b>{maxopen}</b>\n"
               "\u2022 \u4ed3\u4f4d\uff1a<b>{sizing}</b>\uff08\u56fa\u5b9a ${size}\uff09\n"
               "\u2022 \u8ddf\u5356\uff1a<b>{mirror}</b>\n\n"
               "\u9ed8\u8ba4\u4fdd\u62a4\uff08TP / SL / \u8ddf\u8e2a / \u9632\u5d29\u76d8\uff09\u9644\u52a0\u5230\u6bcf\u7b14\u590d\u5236\u4e70\u5165\u3002"),
    },
    "copy_min": {"en": "min buy ${v} \u270F\uFE0F", "es": "min buy ${v} \u270F\uFE0F",
                 "zh": "\u6700\u5c0f\u4e70\u5165 ${v} \u270F\uFE0F"},
    "copy_maxopen": {"en": "max open {v} \u270F\uFE0F", "es": "max open {v} \u270F\uFE0F",
                     "zh": "\u6700\u5927\u6301\u4ed3 {v} \u270F\uFE0F"},
    "copy_size": {"en": "flat size ${v} \u270F\uFE0F", "es": "tama\u00f1o flat ${v} \u270F\uFE0F",
                  "zh": "\u56fa\u5b9a\u4ed3\u4f4d ${v} \u270F\uFE0F"},
    "copy_sizing": {"en": "size: {v} \U0001F4CF", "es": "tama\u00f1o: {v} \U0001F4CF",
                    "zh": "\u4ed3\u4f4d\uff1a{v} \U0001F4CF"},
    "copy_mirror": {"en": "\U0001FA9E Mirror sells: {v}", "es": "\U0001FA9E Replicar ventas: {v}",
                    "zh": "\U0001FA9E \u8ddf\u5356\uff1a{v}"},
    "copy_protect_btn": {"en": "\U0001F6E1\uFE0F Protection", "es": "\U0001F6E1\uFE0F Protecci\u00f3n",
                         "zh": "\U0001F6E1\uFE0F \u4fdd\u62a4"},
    "copy_protect_text": {
        "en": ("\U0001F6E1\uFE0F <b>Protection defaults</b> (attached to every copied buy)\n"
               "TP <b>{tp}%</b> \u00b7 SL <b>{sl}%</b> \u00b7 trailing <b>{trail}%</b> \u00b7 dump guard <b>{dg}</b>"),
        "es": ("\U0001F6E1\uFE0F <b>Protecci\u00f3n por defecto</b> (se aplica a cada compra copiada)\n"
               "TP <b>{tp}%</b> \u00b7 SL <b>{sl}%</b> \u00b7 trailing <b>{trail}%</b> \u00b7 dump guard <b>{dg}</b>"),
        "zh": ("\U0001F6E1\uFE0F <b>\u9ed8\u8ba4\u4fdd\u62a4</b>\uff08\u9644\u52a0\u5230\u6bcf\u7b14\u590d\u5236\u4e70\u5165\uff09\n"
               "TP <b>{tp}%</b> \u00b7 SL <b>{sl}%</b> \u00b7 \u8ddf\u8e2a <b>{trail}%</b> \u00b7 \u9632\u5d29\u76d8 <b>{dg}</b>"),
    },
    "copy_tp": {"en": "TP {v}% \u270F\uFE0F", "es": "TP {v}% \u270F\uFE0F", "zh": "TP {v}% \u270F\uFE0F"},
    "copy_sl": {"en": "SL {v}% \u270F\uFE0F", "es": "SL {v}% \u270F\uFE0F", "zh": "SL {v}% \u270F\uFE0F"},
    "copy_trail": {"en": "Trailing {v}% \u270F\uFE0F", "es": "Trailing {v}% \u270F\uFE0F",
                   "zh": "\u8ddf\u8e2a {v}% \u270F\uFE0F"},
    "copy_dump": {"en": "\U0001F6A8 Dump guard: {v}", "es": "\U0001F6A8 Dump guard: {v}",
                  "zh": "\U0001F6A8 \u9632\u5d29\u76d8\uff1a{v}"},
    "copy_off": {
        "en": "\U0001F6D1 Copytrading stopped.",
        "es": "\U0001F6D1 Copytrade detenido.",
        "zh": "\U0001F6D1 \u5df2\u505c\u6b62\u8ddf\u5355\u3002",
    },
    "pozo_line": {
        "en": "\U0001F3C6 Prize pool: <b>${pozo:.2f}</b> \u00b7 ends in <b>{left}</b>",
        "es": "\U0001F3C6 Pozo de la ronda: <b>${pozo:.2f}</b> \u00b7 termina en <b>{left}</b>",
        "zh": "\U0001F3C6 \u5956\u6c60\uff1a<b>${pozo:.2f}</b> \u00b7 \u7ed3\u675f\u4e8e <b>{left}</b>",
    },
    "pozo_btn": {
        "en": "\U0001F3C6 Pool ${pozo:.2f}",
        "es": "\U0001F3C6 Pozo ${pozo:.2f}",
        "zh": "\U0001F3C6 \u5956\u6c60 ${pozo:.2f}",
    },
    "contest_text": {
        "en": ("\U0001F3C6 <b>Volume contest</b> \u00b7 ends in <b>{left}</b>\n"
               "Pool: <b>${pozo:.2f}</b> (50/50 trader \u00b7 affiliate)\n"
               "Round volume: <b>${total:,.0f}</b>\n\n"
               "\U0001F7E2 <b>Trader</b>\n{trader_lines}\n\n"
               "\U0001F465 <b>Affiliate</b>\n{aff_lines}\n\n"
               "Your rank \u2014 trader #{me_trader} \u00b7 affiliate #{me_affiliate}\n\n"
               "<i>Merit by volume (no lottery). Not financial advice.</i>"),
        "es": ("\U0001F3C6 <b>Concurso por volumen</b> \u00b7 termina en <b>{left}</b>\n"
               "Pozo: <b>${pozo:.2f}</b> (50/50 trader \u00b7 afiliado)\n"
               "Volumen de la ronda: <b>${total:,.0f}</b>\n\n"
               "\U0001F7E2 <b>Trader</b>\n{trader_lines}\n\n"
               "\U0001F465 <b>Afiliado</b>\n{aff_lines}\n\n"
               "Tu puesto \u2014 trader #{me_trader} \u00b7 afiliado #{me_affiliate}\n\n"
               "<i>M\u00e9rito por volumen (sin azar). No es consejo financiero.</i>"),
        "zh": ("\U0001F3C6 <b>\u4ea4\u6613\u91cf\u7ade\u8d5b</b> \u00b7 \u7ed3\u675f\u4e8e <b>{left}</b>\n"
               "\u5956\u6c60\uff1a<b>${pozo:.2f}</b>\uff08\u4ea4\u6613\u8005/\u63a8\u8350\u4eba\u5404 50%\uff09\n"
               "\u672c\u8f6e\u4ea4\u6613\u91cf\uff1a<b>${total:,.0f}</b>\n\n"
               "\U0001F7E2 <b>\u4ea4\u6613\u8005</b>\n{trader_lines}\n\n"
               "\U0001F465 <b>\u63a8\u8350\u4eba</b>\n{aff_lines}\n\n"
               "\u4f60\u7684\u6392\u540d \u2014 \u4ea4\u6613\u8005 #{me_trader} \u00b7 \u63a8\u8350\u4eba #{me_affiliate}\n\n"
               "<i>\u6309\u4ea4\u6613\u91cf\u8ba1\u540d\uff08\u65e0\u62bd\u5956\uff09\u3002\u975e\u6295\u8d44\u5efa\u8bae\u3002</i>"),
    },
    "contest_empty": {
        "en": "no volume yet",
        "es": "sin volumen a\u00fan",
        "zh": "\u6682\u65e0\u4ea4\u6613\u91cf",
    },
    "bridge_text": {
        "en": ("\U0001F309 <b>Bridge USDC to Arc</b>\n"
               "Send USDC from <b>{chains}</b> to your bot wallet on Arc using an official bridge "
               "(Circle CCTP):\n\n<code>{addr}</code>\n\n"
               "I'll notify you the moment it arrives. Non-custodial: you bridge with your own wallet."),
        "es": ("\U0001F309 <b>Puentea USDC a Arc</b>\n"
               "Env\u00eda USDC desde <b>{chains}</b> a tu wallet del bot en Arc con un bridge oficial "
               "(Circle CCTP):\n\n<code>{addr}</code>\n\n"
               "Te aviso en cuanto llegue. No-custodial: puenteas con tu propia wallet."),
        "zh": ("\U0001F309 <b>\u8de8\u94fe USDC \u5230 Arc</b>\n"
               "\u4f7f\u7528\u5b98\u65b9\u8de8\u94fe\u6865\uff08Circle CCTP\uff09\u5c06 USDC \u4ece <b>{chains}</b> "
               "\u53d1\u9001\u5230\u4f60\u5728 Arc \u4e0a\u7684\u673a\u5668\u4eba\u94b1\u5305\uff1a\n\n<code>{addr}</code>\n\n"
               "\u5230\u8d26\u540e\u6211\u4f1a\u7acb\u5373\u901a\u77e5\u4f60\u3002\u975e\u6258\u7ba1\uff1a\u4f60\u7528\u81ea\u5df1\u7684\u94b1\u5305\u8de8\u94fe\u3002"),
    },
    "bridge_open": {
        "en": "\U0001F517 Open bridge",
        "es": "\U0001F517 Abrir bridge",
        "zh": "\U0001F517 \u6253\u5f00\u8de8\u94fe\u6865",
    },
    "tier_text": {
        "en": ("\U0001F48E <b>Your fee tier</b>\nLevel: <b>{label}</b> \u00b7 Fee: <b>{fee}%</b>\n"
               "30-day volume: ${vol}\n\n"
               "<i>VIP by volume; referred users pay 0.90% for 30 days.</i>"),
        "es": ("\U0001F48E <b>Tu tarifa</b>\nNivel: <b>{label}</b> \u00b7 Comisi\u00f3n: <b>{fee}%</b>\n"
               "Volumen 30 d\u00edas: ${vol}\n\n"
               "<i>VIP por volumen; los referidos pagan 0.90% durante 30 d\u00edas.</i>"),
        "zh": ("\U0001F48E <b>\u4f60\u7684\u8d39\u7387</b>\n\u7b49\u7ea7\uff1a<b>{label}</b> \u00b7 "
               "\u8d39\u7387\uff1a<b>{fee}%</b>\n30 \u5929\u4ea4\u6613\u91cf\uff1a${vol}\n\n"
               "<i>\u6309\u4ea4\u6613\u91cf\u5347\u7ea7 VIP\uff1b\u88ab\u63a8\u8350\u7528\u6237 30 \u5929\u5185 0.90%\u3002</i>"),
    },
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
        [b("btn_wallet", "cmd:/connect"), b("btn_help", "cmd:/help")],
        [b("btn_signals", "soon:Signals"), b("btn_copytrade", "cmd:/copytrade")],
        [b("btn_bridge", "cmd:/bridge"), b("btn_premium", "soon:Premium")],
        [b("btn_referral", "cmd:/referral")],
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
