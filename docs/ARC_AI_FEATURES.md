# ARC AI — Catálogo completo de funcionalidades

> Documento maestro de **todo** lo que hace el producto, pensado para (a) que el equipo no pierda
> ninguna función de vista y (b) reutilizar como base de **marketing** (sección 9: hooks en inglés).
> Honestidad obligatoria: **no es consejo financiero**, **no custodia**, sin promesas de retorno.
> Fecha: 2026-09-27.

Leyenda de estado: **[LIVE]** ya operativo · **[TESTNET]** probado en testnet, no mainnet ·
**[PAPER]** simulado · **[PRONTO]** planificado.

---

## 1. Datos on-chain (indexer de Arc)

| Función | Qué es | Estado |
|---|---|---|
| Indexer Uniswap **v4 / v3 / v2** | Captura swaps del PoolManager v4 (`0x8366…0951`) y de v3/v2 | [LIVE] |
| **Backfill completo** con verificación de gaps | Bloques `21,068,653 → 22,721,550`, ~6.7 M swaps, **gaps = 0** | [LIVE] |
| **Legs** (trades normalizados) | wallet, token, pool, lado, cantidad, valor estable, precio implícito | [LIVE] |
| Detectores de **launchpad** (Argus) | `TokenCreated` → token (nombre/símbolo/creator/pool) | [LIVE] |
| **Metadata de token** | símbolo on-chain (`symbol()`), logo (IPFS Argus → DexScreener fallback) | [LIVE] |
| **Reputación del creador** | nº de tokens creados, cuántos **volcó**, % de rug, valor | [LIVE] |
| **Escáner de contrato** (heurística) | detecta maquinaria de **honeypot/mint/pause/blacklist/tax/limits** por selectores en el bytecode (resuelve **proxies EIP-1167**) + **owner activo** y proxy upgradeable | [LIVE] |
| **Simulación de transferencia** | `eth_call` de un `transfer` desde un holder **con saldo** al pool; si **revierte** → posible honeypot. Si no hay holder con saldo, se indica `null` (no se inventa el resultado) | [LIVE] |
| **Thin-market check** | sin trades / un solo wallet tras N bloques | [LIVE] |
| **Ranking de launchpads** | volumen/actividad por launchpad | [LIVE] |

## 2. Señales y vigilancia (el corazón anti-rug)

| Señal | Qué detecta | Estado |
|---|---|---|
| **dev-sell** | el **creator** vende su posición (FP ~1%) | [LIVE] |
| **compound** | dev-sell **seguido de** colapso de volumen | [LIVE] |
| **volume spike** | subida anómala de volumen (z ≥ +2.5 y ≥ $500/bucket) — **dos caras** | [LIVE] |
| **liquidity removal** | retirada de liquidez del pool (rug) | [LIVE] |
| **large sell** | venta grande no-creator (≥ $5 k y ≥ 50% del volumen reciente) | [LIVE] |
| **Confirmación por volumen** | un dev-sell con volumen reciente alto **sube de severidad** | [LIVE] |
| **Vigilancia de TUS tokens** | al comprar, el bot **vigila ese token** y avisa de anomalías; al cerrar, deja de seguir | [LIVE] |
| **Wallet tracking** | sigues una **dirección pública** (watch-only) y auto-sigues sus tokens | [LIVE] |
| Anti-spam / dedup | cooldowns por token+tipo, dedup persistente, ingesta idempotente | [LIVE] |
| **Observabilidad** | log por ciclo (`lag`, `signals`, `watch`, `queue`) | [LIVE] |

## 3. Bot de Telegram (@arc_intel_test_bot)

| Comando / función | Qué hace | Estado |
|---|---|---|
| `/start` + onboarding | alta, allowlist (beta cerrada), disclaimer | [LIVE] |
| `/check <token>` | ficha: precio, **market cap**, **vol 24h**, **thin-market**, **reputación del creador**, **riesgo de contrato** (heurística), launchpad, logo, explorer | [LIVE] |
| `/subscribe`, `/subscribe_recent`, `/list` | seguir tokens / top recientes / tus suscripciones | [LIVE] |
| `/wallet`, `/link_wallet`, `/unlink_wallet` | wallet **watch-only** (nunca llaves) + auto-seguimiento | [LIVE] |
| `/settings` | interruptores por tipo: dev_sell / compound / volume_spike / liquidity_removal / large_sell | [LIVE] |
| `/stats` | valor de señal **[PAPER]**, con **ambas caras** (mediana, CI95, % positivos, cola) | [LIVE] |
| `/positions` | posiciones con PnL | [LIVE] |
| `/pending`, `/approve`, `/cancel` | propuestas **[PAPER]** | [LIVE] |
| Menú inline (estilo Maestro) | navegación por botones | [LIVE] |
| **Idiomas EN / ES / 中文** | persistente por usuario | [LIVE] |
| Alertas **con logo** del token | imagen del token en la alerta | [LIVE] |
| **Protect** (kill-switch) | orden **armada** que se dispara sola ante dev-sell/compound | [PAPER] |

## 4. Trading no-custodial (Mini App + executor)

| Función | Qué es | Estado |
|---|---|---|
| **Executor minimal** `ArcIntelExecutor` (~218 LOC) | Permit2 + v4 PoolManager, un firmado → un fill, **sin custodia** (no hay función de retirada) | [TESTNET] |
| Seguridad del contrato | `paused`, **allowlist de pools** (fail-closed), nonce de orden (**single-use**), `deadline`, `minOut`, **cancelOrder** | [TESTNET] |
| **Compra** (4 pasos) | pegar CA → ficha → monto/slippage → **firmar** | [TESTNET] |
| **Venta por %** | 25 / 50 / 75 / 100 % sobre la posición real (`sell_quantity`) | [TESTNET] |
| **Órdenes pre-firmadas** (Opción 2) | el usuario firma **una vez**; el **keeper** ejecuta sola — sin hot keys del usuario | [TESTNET] |
| **Keeper permissionless** | envía órdenes firmadas; no puede robar ni alterar términos (la firma los liga) | [TESTNET] |
| **Relayer (gas)** | wallet dedicada que envía las órdenes; dirección generada, **pendiente de fondear** con USDC testnet | [TESTNET] |
| **Plan de salida** (TP / SL / trailing / scale-out) | motor `strategy.py`; `/plan` crea una venta condicional | [TESTNET] |
| **Cancelación** | `/cancel` (reposo del keeper) + `cancelOrder` on-chain (usuario) | [TESTNET] |
| **Posiciones + reconciliación** | coste medio, PnL no realizado, cotejo con saldo on-chain | [LIVE] |
| Firmado **WalletConnect** | el usuario firma; el backend nunca firma | [TESTNET] |
| Auth **initData** de Telegram | endpoints por usuario protegidos | [LIVE] |
| **MiniApp (TMA)** | pestañas Compra / Posiciones / Cartera / **Alertas** | [TESTNET] |
| **Gráfico de alertas** | **sparkline de precio + barras de volumen** con el punto de la alerta | [TESTNET] |

## 5. Economía y comunidad

| Elemento | Detalle | Estado |
|---|---|---|
| Fee por operación | **1%** del volumen operado | [PRONTO] |
| Reparto | 5% trader + 5% afiliado + 20% referidos + 30% infra + 40% equipo | [PRONTO] |
| **Concurso por volumen** (no lotería) | 2 rondas/día UTC (00–12, 12–00); ranking **trader** y **afiliado** | [PRONTO] |
| **Referidos** | 20% de por vida sobre la **comisión neta** | [PRONTO] |

## 6. Diferenciadores reales

1. **Seguridad anti-rug primero**: dev-sell, liquidez, large-sell, reputación del creador.
2. **Arc-nativo**: indexer propio de Uniswap v4 sobre Arc.
3. **No-custodia pura**: el usuario firma; no hay llaves que robar; el executor no guarda fondos.
4. **Honestidad**: **[PAPER]** explícito, **ambas caras**, track record público.
5. **Vigilancia personalizada**: el bot cuida **los tokens que tú tienes**, no ruido genérico.

## 7. Límites (lo que aún NO hay) — para no prometer de más

- **Mainnet**: el executor está en **testnet**; falta **auditoría + despliegue**.
- **Relayer con gas**: la ejecución real necesita `ARC_INTEL_RELAYER_KEY` (aún no configurado).
- **SL/trailing**: el **disparo es del keeper** (off-chain); no es un stop nativo on-chain.
- **Honeypot / mint / pause / blacklist**: hay un **escáner heurístico** de contrato [LIVE]
  (selectores + owner/proxy); la **prueba definitiva** (simular compra y venta) es [PRONTO].
- **Liquidez USD**: hoy es estimación, no una cifra validada.
- **Dominio de marca**: `app.basepump.dev` pendiente del registro DNS en Porkbun.

## 8. Mensajes núcleo (resumen para copy)

- "**Sabemos cuándo el creador suelta el token.**"
- "**Vigila lo que tú tienes**, no lo que no te importa."
- "**Tú firmas. Nosotros jamás tocamos tus fondos.**"
- "**Un botón: Protect.** Si el dev vende, sales."

## 9. Marketing hooks (EN, para usar en copy público)

- **"Non-custodial by design — you sign, we never hold your keys."**
- **"We watch the tokens you hold, not the noise."**
- **"Creator dump detection on Arc."**
- **"One tap: Protect. If the dev sells, you're out."**
- **"Built on Arc's Uniswap v4 — native, not a fork."**
- **"Both sides shown: potential upside *and* tail risk."**

> **Disclaimers obligatorios** (incluir en toda comunicación):
> *Not financial advice. Signals are informational, derived from on-chain data, and can be wrong.
> Simulated results are labeled [PAPER]. No custody. No guarantees of profit. Do your own research.*
