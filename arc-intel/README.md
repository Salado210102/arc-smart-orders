# ARC AI — `arc-intel`

Indexer on-chain de Arc + **bot de alertas de riesgo 24/7** + **executor no-custodial** (testnet).
Read-only por diseño: **no** firma, **no** custodia, **no** mueve fondos de usuarios.

## Qué hace (estado real, no Fase 1)

- **Indexer v2/v3/v4 complete**: blocks `21,068,653 → 22,721,550` (~1.56M bloques), **~6.7M swaps**,
  gaps = 0. Argus `TokenCreated` → `tokens` (nombre/símbolo/creator/pool_id). Uniswap **v4** PoolManager
  `0x8366…0951` (Initialize/ModifyLiquidity/Swap/Donate). v3/v2 también capturados.
- **Detección de riesgo (validada, NO predictiva)**: **dev-sell** (FP ~1%), **alerta compuesta**
  (dev-sell + colapso de volumen, *interno*) y **señal de volumen** (spike z≥+2.5 con suelo de $500
  por bucket; "dos caras": puede preceder un pump *o* un rug), con **confirmación por volumen** (un
  dev-sell con volumen reciente alto sube de severidad). El **colapso de volumen** ya **no se muestra**
  al usuario (alimenta `compound` internamente). El **score de wallets se INVALIDÓ** en el walk-forward
  (Fase 2.2, no le ganó al azar) → **descartado y eliminado del código**.
- **Alertas centradas en el usuario**: el bot **vigila automáticamente los tokens que el usuario
  tiene** (posición > 0 → auto-seguir ese token; al cerrar la posición → dejar de seguir) y le avisa
  de anomalías (dev-sell / compuesta / spike).
- **Bot de Telegram 24/7** (beta cerrada, allowlist): `/check`, `/list`, `/subscribe*`, `/settings`,
  `/wallet`, `/pending`, `/positions`, `/stats`, `/help`; menú inline estilo Maestro; **i18n EN/ES/中文**.
  - `/check`: nombre, launchpad, **reputación del creador** (tokens creados / cuántos volcó), antigüedad,
    actividad, **precio**, **market cap**, **volumen 24h**, estado y enlace al explorer.
  - Operación **en papel [PAPER]**: **Buy** (importe), **vender 25/50/75/100 %**, **PnL** con refresco.
  - **Kill-switch [PAPER]**: `Protect` → orden **armada** que **se dispara sola** ante un dev-sell.
- **Executor no-custodial** (`executor/`, Solidity ≈218 LOC): `Permit2` + v4 PoolManager, `minOut`/`deadline`/
  `nonce`, **sin custodia**. Probado **end-to-end en testnet**; **paquete de auditoría congelado**
  (tag `arc-intel-executor-v1`) + invariantes y triage de Slither. **No desplegado en mainnet**.

## Módulos que EXISTEN pero **NO están conectados a producción**
> Importante para no perderlo de vista. No se han "dado de alta" en el servicio.

- `execution/strategy.py` — lógica de salida (TP/SL/trailing/scale-out). **Pura**, sin firma ni ejecución.
- `execution/preorders.py` — construye el **payload EIP-712** y, solo con la **firma del usuario**,
  `submit_execute(...)`. **Nunca** ejecuta sin firma (lanza `no_signature`).
- `bot/sign_server.py` — endpoints `/order` y `/sign` (guarda la firma; **no** firma ni ejecuta) + sirve
  la Mini App `miniapp/index.html` (WalletConnect). **Desplegado** como `arc-intel-sign.service`
  detrás de Caddy (HTTPS), con **CORS restringido** al dominio real.
- `bot/sim.py` — simulador local (demo), no forma parte del servicio.

**Infra de firma (testnet):** **`https://app.basepump.dev` ACTIVO** (DNS A + cert Let's Encrypt de
Caddy, verificado; la Mini App se sirve ahí) además del endpoint temporal `sslip.io`. **Relayer
fondeado** y cargado en los servicios. Pendiente para ejecución real: **allowlist de pools** en el
owner del executor (`setAllowedPool(poolId,true)`).
Spec de la Mini App: `../docs/ARC_AI_MINIAPP_SPEC.md`.

## Mapa del código
```
indexer/   backfill, ingest, stream_alerts, alerts, creator_rep, pg_storage, pnl, scoring(histórico), …
bot/       telegram (servicio 24/7), commands, i18n, messages, store, sender, tokenmeta, sign_server, sim
execution/ intents, strategy, eip712, preorders        (los 3 últimos: NO conectados)
security/  permissions        monetization/ fees
executor/  ArcIntelExecutor.sol + tests + audit docs   (tag arc-intel-executor-v1)
miniapp/   index.html (firma WalletConnect)
```

## Tests
```
cd arc-intel
python3 -m unittest discover -s tests        # suite de Python
cd executor && forge test                    # 27 tests + invariantes (Solidity)
```

## Documentación
- `../docs/ARC_AI_DECISIONES_BOT.md` — registro de decisiones (producto, economía, Opción 2, ideas).
- `../docs/ARC_AI_PHASE5_*` — executor: design, options, audit package, Slither triage, invariantes.
- `README` histórico de Fase 1: `../docs/ARC_AI_DATA_ENGINE_M02.md` (y `M02B…M08`).

## Honestidad
- Las señales son **informativas** (no consejo financiero). Se muestran **ambas caras** (beneficio típico
  **y** cola de riesgo).
- El **score de wallets no predice** (Fase 2.2); cualquier resto de esa idea fue **eliminado**.
- Todo lo de "operar" hoy es **[PAPER]**; la ejecución real (no-custodial, firmada) está en testnet y no
  conectada al servicio.
