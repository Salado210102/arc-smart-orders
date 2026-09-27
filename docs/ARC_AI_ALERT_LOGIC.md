# ARC AI — Lógica de cada alerta (calidad primero)

> Regla de oro: **una alerta que empuja a comprar debe indicar que ENTRA dinero** (volumen al alza,
> precio al alza, más compras que ventas). Un volumen que sube con **precio cayendo** = gente
> **saliendo** → NO se alerta como compra. Fecha: 2026-09-27.

## Descubrimiento (público, "compra") — en VERDE 🟢
| Señal | Regla (todas deben cumplirse) | Por qué |
|---|---|---|
| **volume_spike** | z(vol) ≥ **+2.5** **Y** vol ≥ **$500**/bucket **Y** **precio al alza** (≥ +0% vs ~2 h) **Y** **net buy** (compras ≥ ventas × 1.2 en la última hora) | Volumen + precio + flow al alza = dinero **entrando** |
| **price_surge** | precio ≥ **+50%** vs ~2 h | Momentum fuerte |
| **whale_buy** | compra única ≥ **$2k** que domina (≥50%) el volumen reciente | Mano grande comprando |

> **Antes estaba mal:** `volume_spike` solo miraba el volumen → disparaba en **dumps** (precio
> cayendo). **Arreglado:** ahora exige precio al alza **y** net buy.

## Riesgo (privado, solo si TIENES el token) — ROJO 🔴 (botón Vender)
| Señal | Regla | Uso |
|---|---|---|
| **dev_sell** | el **creator** vende ≥50% de su posición (o ≥$100) | Salir |
| **compound** | dev_sell seguido de colapso de volumen | Salir |
| **large_sell** | venta no-creator ≥ $5k y ≥50% del volumen reciente | Ballena saliendo |
| **liquidity_removal** | retirada de liquidez del pool | Rug |

`volume_collapse` se calcula **solo como insumo** de `compound`; **no se muestra**.

## Flow (compras vs ventas) — nuevo
Se acumula **volumen de compras y de ventas por bucket**. El spike exige **net buy**
(`buy_vol ≥ sell_vol × 1.2` en la última hora). Esto elimina el caso "volumen alto porque todos
venden".

## Umbrales (configurables) y anti-ruido
- `spike_z=+2.5`, `min_spike_usdc=$500`, `spike_min_price_pct=0`, `spike_min_buy_ratio=1.2`
- `price_surge_pct=+50%`, `whale_buy_usd=$2k`
- **Cooldown** por token+kind (no repetir) + **cap** por usuario/ciclo + **dedup** persistente.
- **Prioridad: pocas y buenas.** 48 malas de 50 = 0 valor (y espanta al usuario).

## Cómo se valida (medición, no opinión)
- **Paper eval**: para cada alerta, resultado a 1h (mediana de movimiento). Se etiqueta **[PAPER]**.
- Revisar que **% positivos** y **mediana** sean buenos antes de promocionar una señal.
- Mostrar **ambas caras** (también la cola de riesgo).

## Medición (backtest real) — 2026-09-27
`indexer/backtest_spike.py` (replay de `legs` + retornos forward). Ventana desde bloque 22,700,000:

| Señal | 1h mediana / %pos | 4h | 24h |
|---|---|---|---|
| **volume_spike** | −3.6% / **30%** (n=44) | −3.9% / 36% | +9.3% / 62% (n=8) |
| **price_surge** | −4.1% / 38% (n=539) | −7.5% / 34% | −15.5% / 38% |
| **whale_buy** (≥$1k, price up) | −1.1% / 30% (n=11) | −2.1% / 22% | −11.4% / 0% |
| **graduation** (nuevo token en DEX) | −2.0% / **20%** (n=1527) | −1.9% / 27% | −5.3% / 26% |

**Veredicto: las señales de compra NO tienen edge** (mediana negativa, %positivos < 50%). **NO deben
empujarse como "Comprar"** — haría perder dinero al usuario. El valor defendible del producto es el
**riesgo** (dev-sell, rug; validado).

## Decisión
- **Desactivar el feed público de "compra"** (volume_spike / price_surge / whale_buy) salvo que se
  demuestre edge con research serio. **✅ HECHO (2026-09-27):** ya no se empujan ni se muestran; el
  bot queda centrado en **riesgo** (holdings).
- Mantener **alertas de RIESGO** (validadas) como núcleo del producto + **escáner de seguridad**.
- Si algún día hay una señal con edge medido, se promociona; mientras, **honestidad**: no vender
  señales de compra que no funcionan.

## Pendiente de calidad
- Umbrales por liquidez; `new_token`/`liquidity_add` (solo si se miden con edge).
- Mostrar siempre las dos caras y el disclaimer.
