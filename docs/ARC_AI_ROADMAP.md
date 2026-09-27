# ARC AI — Análisis competitivo + roadmap (para competir)

> Objetivo: competir en el mercado de **trading bots de memecoins**. Regla: priorizar features
> **medibles** y **defendibles**; no vender humo (nuestras señales de compra dieron **sin edge**).
> Fecha: 2026-09-27.

## 1. Qué hace la competencia (research)
**Bots Telegram (Banana Gun, Maestro, Trojan, BonkBot, GMGN, Photon, Cove):**
- Ejecución **rápida**, **sniping** (comprar en el primer bloque del pool), **copy-trade**, **órdenes
  límite**, **DCA**, **auto-sell**, **TP/SL**, **MEV protection**, multi-chain, fees **0.5–1%**.
- **Banana Gun:** **simulación pre-trade** que **caza honeypots antes de mover fondos**.
**Scanners de seguridad (RugCheck, GoPlus, Bubblemaps, NodeFlare):**
- **Score 0–100**, honeypot, **buy/sell tax**, **mint authority**, **ownership**, **blacklist**,
  **holder concentration**, **LP lock**, liquidez viva, **clusters de wallets** (Bubblemaps).

## 2. Qué YA tenemos (fosos)
- Datos Arc propios (legs, pools, tokens, creadores), **alertas de riesgo validadas** (dev-sell, LP,
  large-sell, compound), **escáner de contrato** (honeypot/mint/pause/blacklist/tax/proxy), **wallet
  de bot (custodia)** con ejecución instantánea, **executor + sesiones** no-custodial, Mini App, i18n.
- **Honestidad medida**: sabemos que las señales de compra NO predicen (documentado).

## 3. Gaps para competir (priorizados por valor y viabilidad)
| # | Feature | Por qué | Viabilidad | Medible |
|---|---|---|---|---|
| **P0** | **Score de Seguridad del token (0–100)** | Es el estándar del mercado y **agrega nuestro foso**; generador de confianza | Alta (ya tenemos las piezas) | Sí |
| **P0** | **Concentración de holders + clusters** | Riesgo de dump; Bubblemaps-lite | Media (con `token_transfers`) | Sí |
| **P0** | **Auto-Protect** (proteger cada compra automáticamente) | Nuestro **edge validado**; único | Alta (ya existe Protect) | Sí |
| **P1** | **LP lock / burned LP badge** | Señal de seriedad (Argus la bloquea) | Media (verificar burn addr) | Sí |
| **P1** | **Simulación pre-trade (buy→sell)** | Banana Gun lo tiene; caza honeypots | Media-baja (requiere simular en el pool) | Sí |
| **P1** | **Órdenes límite / DCA / TP-SL-Trailing con ejecución** | Lo esperado por el usuario | Alta (ya guardamos planes; falta ejecutar) | Sí |
| **P1** | **Copy-trade** (seguir una wallet y copiar) | Muy pedido (aunque el edge es dudoso) | Media | Sí |
| **P2** | **Sniping con filtros** (comprar al graduarse, solo si el score es alto) | Staple; con filtros de seguridad es defendible | Media | Sí |
| **P2** | **Multi-wallet** / **Referidos** / **RPC dedicado** (velocidad) | Competitividad/UX | Alta | No |

## 4. Recomendación (posicionamiento)
**"El bot MÁS SEGURO de Arc."** El foso es **seguridad anti-rug + score + auto-protección**, no
predecir pumps. Coincide con el paper (*Catching the Rug*) y con los scanners líderes.

**Orden sugerido:** 
1. **P0 — Safety Score (0–100)** ✅ + **holder concentration** ✅ (aprox. desde `legs`) + **Auto-Protect** ✅.
   - Safety Score: `indexer/safety.py` (agrega contrato+creador+liquidez+edad+thin+concentración);
     visible en `/check` y en la Mini App.
   - Holder concentration: top-10 por posiciones netas de `legs` (sin depender de `token_transfers`,
     que está vacía).
   - Auto-Protect: `execution/autoprotect.py` — al detectar **riesgo** en un token que tienes, **vende
     sola** con la wallet del bot; toggle en la Mini App (`/autoprotect`; por defecto **ON**).
   - Caveat: el **RPC 429** limita `total_supply`/precios → el score queda incompleto a veces.
2. **P1 — LP lock badge**, **ejecución de TP/SL/Trailing**, **copy-trade**.
3. **P2 — sniping con filtros**, multi-wallet, referidos, RPC.

## 5. Honestidad (regla)
- Toda feature nueva se **mide** (backtest/paper) antes de promocionarse.
- Se muestran **ambas caras** y el **track record** público.
