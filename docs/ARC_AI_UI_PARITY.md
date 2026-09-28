# Arc AI — Paridad de UI (bot de Telegram ↔ Mini App)

> **Regla fija (2026-09-27).** **Todo cartel (texto/etiqueta) y botón que implementemos debe existir en
> las DOS interfaces: el bot de Telegram y la Mini App.** No se entrega una función en una sola.
> Y **todo cambio se documenta** (ver "Cómo documentar").

## Cómo documentar
- Cada cambio se apunta en **`docs/ARC_AI_DECISIONES_BOT.md` §10 (Registro cronológico)** con fecha,
  qué se hizo, en qué interfaces, endpoints y nº de tests.
- Si toca modelo/economía → actualizar también `ARC_AI_ECONOMIC_MODEL.md` (+ `.csv`).

## Checklist de paridad (estado actual)
| Función | Bot Telegram | Mini App | Notas |
|---|---|---|---|
| Alertas de riesgo | `/list`, avisos con botón Comprar/Vender | pestaña **Alertas** + gráfico | ✅ |
| Ficha de token + Safety + **RUGGED** | `/check` (Safety, estado RUGGED/dev-sold) | pestaña **Compra** (Safety, badge RUGGED) | ✅ |
| Caza rápida (TP/SL/Trailing) | `/check` → Protect (paper) | pestaña **Posiciones** (SL/TP/Trail por posición) | parcial |
| **Auto-Protect** | `/settings` (toggle) | pestaña **Cartera** (toggle) | ✅ |
| Wallet custodial (Modo Maestro) | `/wallet` (enlace), Mini App | pestaña **Cartera** (crear/retirar/vender) | ✅ |
| Wallet watch-only | `/connect`, `/link_wallet` | pestaña **Cartera** (mostrar) | ✅ |
| Referidos + estadísticas | `/referral` (código, enlace, stats) | pestaña **Cartera** (tarjeta + desglose) | ✅ |
| Pozo del concurso | `/pozo` + botón dinámico en el menú | banner superior + ranking | ✅ |
| Publicación del ganador (canal) | canal oficial (`ARC_INTEL_CHANNEL`) | — (solo canal) | pendiente config |
| Copytrade (multi-wallet + filtros) | `/copytrade` (Añadir wallet / Filtros) | pestaña **Copy** | ✅ |
| Bridge USDC → Arc | `/bridge` | tarjeta en **Cartera** | ✅ |
| Tarifa / VIP / bienvenida | `/tier` | tarjeta en **Cartera** | ✅ |
| Idiomas EN/ES/ZH | `/language` | sigue el idioma del bot (`/me`) | ✅ |

## Al añadir algo nuevo
1. Implementar el endpoint/dato una sola vez (fuente única).
2. Añadir el **texto i18n** (EN/ES/ZH) en el bot y el equivalente en la Mini App.
3. Añadir el **botón/comando** en el bot **y** el control en la Mini App.
4. Tests de ambos lados.
5. Documentar en `ARC_AI_DECISIONES_BOT.md` §10.
