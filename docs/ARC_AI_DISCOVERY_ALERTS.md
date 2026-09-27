# ARC AI — Señales de descubrimiento (para que compren)

> Objetivo: **feed público** de oportunidades para atraer al usuario a comprar. Se empujan **por
> Telegram a todos** (con botón **🟢 Comprar** → Mini App) y se muestran en la pestaña **Alertas**.
> Distinto de las **alertas de riesgo** (dev-sell…), que son **por usuario** y **solo si tienes el
> token** (botón **🔴 Vender**). Fecha: 2026-09-27.

## Modelo
- **Descubrimiento (público, a todos):** `volume_spike`, `price_surge`, `whale_buy`.
- **Riesgo (privado, solo holdings):** `dev_sell`, `compound`, `liquidity_removal`, `large_sell`.
- El mensaje de descubrimiento lleva botón **Comprar** (`web_app` → `app.basepump.dev/?token=<CA>`).

## Implementadas
| Señal | Qué detecta | Cálculo | Estado |
|---|---|---|---|
| `volume_spike` | subida anómala de volumen | z ≥ +2.5 y ≥ $500/bucket | ✅ |
| `price_surge` | subida fuerte de precio | precio ≥ +50% vs ~lookback (≈2 h) | ✅ |
| `whale_buy` | compra grande (ballena) | compra ≥ $2k y ≥50% del volumen reciente | ✅ |

## Estudio: siguientes candidatas (con los datos que YA tenemos)
| Señal | Qué detecta | Cómo (datos) | Prioridad |
|---|---|---|---|
| `new_token` | token **recién creado** (oportunidad temprana) | `launchpad_events` `TokenCreated` → alertar en la creación | **Alta** |
| `liquidity_add` | entrada de **liquidez** (señal de seriedad) | `v4_liquidity` deltas positivos (> umbral) | **Alta** |
| `buy_pressure` | más **compras** que ventas | ratio buys/sells de `legs` en ventana (p. ej. ≥ 3:1) | Media |
| `holder_growth` | crecen los **holders** | `count(distinct wallet)` de `legs` sube > X% en ventana | Media |
| `trending` | **top** por volumen/txns creciente | ranking por `legs` (o `launchpad_rank`) | Media |
| `creator_good` | **creador con buen historial** | `creator_rep` (creados / volcados) + creación nueva | Media |
| `breakout` | ruptura de rango (precio rompe máximos N buckets) | `prices` (ya lo trackeamos) | Baja-Media |
| `smart_money_in` | **wallet** histórica compra | requiere wallets validadas (la score se invalidó) | **[BLOQUEADA]** |

Notas:
- `new_token` y `creator_good` dependen de metadatos del launchpad (ya indexamos `TokenCreated`).
- `smart_money_in` está **bloqueada** porque el **score de wallets se invalidó** (no predice) — no
  la usaremos.
- Umbrales **configurables** para ajustar ruido/señal.

## Anti-spam (crítico en feed público)
- Cap por usuario por ciclo (`per_chat_cap`) + dedup persistente (`delivered`).
- Cooldown por token+kind (ya existe para collapse; extender a descubrimiento).
- Solo señales con **volumen real** (sueldos en USD) para no spamear tokens muertos.

## Embudo
`descubrimiento (público) → el usuario compra (1 clic desde el botón) → el bot vigila ESE token →
alertas de riesgo (privadas) → el usuario vende/protege`.
