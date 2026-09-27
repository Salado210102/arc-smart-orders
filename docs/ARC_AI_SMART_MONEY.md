# ARC AI — Smart Money: investigación y medición (honesta)

> Como ingeniero cuantitativo: investigamos cómo se construye "smart money", lo implementamos y lo
> **medimos**. Regla: **solo se shippea si hay edge demostrado**. Fecha: 2026-09-27.

## Qué dice la industria/papers (research)
- **Papel con evidencia real**: *"Catching the Rug"* (arXiv 2608.20271) — 6.4 M memecoins, detecta
  **rug pulls** con **dinámica de trading** (liquidez + volumen) y **XGBoost** con los **primeros 5
  min**, **sin** features de código. → el enfoque con edge es **anti-rug**, no "predecir pumps".
- **Smart money / copy-trading** (guías Nansen/Thrive/etc.): se construye por **backtest de
  rendimiento por wallet** (PnL, win-rate), early-buyer, entidades. Advertencias explícitas:
  **latencia**, **sesgo de supervivencia**, **manipulación** (wallets que fingen comprar y dumpean),
  **sybil/wash trading**. La propia industria dice: *"trading signal, not copy signal"*.

## Qué hicimos (riguroso)
`indexer/smart_money.py` (walk-forward, solo lectura):
1. **Score de wallets** con datos **hasta** `train_end` (flujo neto de USDC por wallet: vendido −
   comprado; winners = neto > 0, con ≥8 trades).
2. **Señales** en la ventana **posterior**: compras de wallets "smart".
3. **Medida** del retorno forward (1 h / 4 h) de la token comprada, **frente a baseline** (todas las
   compras).

## Resultado (medido, bloque train ≤ 22,700,000 → test ≤ 23,080,000)
| Grupo | 1h mediana | 1h %pos | 4h mediana | 4h %pos |
|---|---|---|---|---|
| **SMART** (49,321 wallets) | **−14.0%** | **20%** | **−22.7%** | 19% |
| baseline (todas las compras) | −11.5% | 27% | −20.6% | 25% |

**Veredicto: el "smart money" NO tiene edge** (incluso **peor** que el baseline). Coherente con la
invalidación previa del **wallet score** (Fase 2.2). **No se implementa como señal de compra.**

> Caveat de datos: hay precios basura (saltos tipo +11,924,065% = glitch de decimales) que hay que
> limpiar para cualquier backtest serio.

## Decisión (producto)
- **NO** vender señales de compra / smart money / copytrading: **no funcionan** (medido).
- **SÍ** posicionar el producto en lo **validado**: **seguridad anti-rug** (dev-sell, liquidez,
  dinámica de trading) + **escáner de contrato** + **honestidad** (mostrar lo medido).
- Coincide con el **paper**: el edge defendible está en **detectar fraude/rug**, no en adivinar pumps.

## Si se quiere insistir en "smart money"
- Enfoque honesto: tratarlo como **descartado** (como la wallet score). Reinvertir en **anti-rug**.
- Alternativa con potencial: **clustering de wallets** + **entidades** + **flow a exchanges** — pero
  requiere research y **medición**; no prometemos edge.
