# ARC Intelligence — Fase 1 (Indexer) — Informe (corregido)

Fecha: 2026-09-25. Módulo: `arc-intel/`. Estado global: **PARCIAL** (captura real funcionando + ABI Argus
desde repo oficial; Bitquery sigue bloqueado).

Etiquetas: **[MEDIDO] / [PARCIAL] / [BLOQUEADO] / [CORREGIDO]**

---

## 0. Correcciones exigidas en la auditoría

### 0.1 Contradicción del símbolo — **[CORREGIDO]**
- La verdad comprobada: en la DB **`symbol`/`name` eran `NULL`** y **ningún código llamaba a
  `symbol()/name()/decimals()`**. La palabra "cirBTC" en mi mensaje anterior fue una **anotación mía de
  memoria**, NO un dato resuelto. Error mío.
- Ahora sí hay resolución real, pero **desde el evento `TokenCreated` de Argus** (no desde `symbol()`).
  Ejemplo real recién capturado:
  ```
  address 0x1efca93316b36ccacd783f6be612ee2ea297160d
  symbol "BTS"  name "Buy The Sphere"
  creator 0x4d43c873a0f8033f0f6864e4ffe2de0f85112917
  launchpad argus  pool_id 0xf94477a1...a696  created_ts 1790348894
  ```
  Para tokens que **no** vienen de un `TokenCreated`, `symbol/name` siguen `NULL` (correcto).

### 0.2 Crash-recovery con kill forzado (no solo reconexión) — **[MEDIDO]**
Mismo rango (30 bloques), proceso `python` real matado con `Stop-Process -Force` **en mitad del
procesamiento** (con filas ya escritas):

| Momento | swaps | wallets | cursor |
|---|---:|---:|---:|
| PRE-KILL (proceso vivo, lote a medias) | 5 | 5 | 22706228 |
| POST-KILL (tras matar) | 5 | 5 | 22706228 |
| Reinicio (mismo rango) | — | — | — |
| FINAL | 30 | 18 | 22706258 |

Datos del reinicio: `processed_total=30`, `duplicates_total=5`, log
`tick blocks=22706229-22706258 events=30 lag=52 dup_total=5`.

Interpretación: **cero pérdida** (los 30 swaps del rango quedan), **cero duplicado lógico**
(los 5 ya insertados se detectan como duplicados), y el cursor **solo avanza al terminar el lote**
(reanudó desde 22706228). El kill durante la fase de fetch también se probó: cursor intacto, 0 filas.

### 0.3 ABI de Argus — origen y confianza
Orden seguido:
1. **Explorer Arc (`explorer.arc.io`, Blockscout):** API `.../api?module=contract&action=getabi` →
   **HTTP 403 (Cloudflare)**; el HTML de la página no trae ABI. **No se pudo confirmar verificación**
   desde este entorno.
2. **GitHub:** encontrado repo **oficial** `arguspad/argus-world` → `onchain/event-signatures.md` +
   `contracts/Portal.sol` con las firmas exactas.
3. **Keccak (confirmación cruzada):** calculado con viem y **coincide** con los topic0 observados.

| Evento | topic0 | Confirmado |
|---|---|---|
| `TokenCreated(address,address,string,string,bytes32,string,string,string,string)` | `0x1d891723…5ce0a` | **sí (GitHub + keccak)** |
| `PartsDeployed(address,address,address,address)` | `0xa54419a4…cd4da` | **sí (GitHub + keccak)** |
| `CurveOpened(address,bytes32,address,uint256,uint128,int24,int24)` | `0x55e45784…c3a9aa0` | **sí (GitHub + keccak)** |

**Nivel de confianza:** alto, **fuente = repo oficial de GitHub**; **NO explorer-verificado**.
`0x84d429ed…232a9` sigue **sin identificar** (no está en el doc) → se marca inferido/desconocido, **no ABI**.

**`DevBuy`:** el repo oficial **no define** ningún evento `DevBuy`. Por tanto **`dev_buys` no se puede
poblar desde Argus**; poblarlo requeriría inferir el dev-buy del `Swap` de la tx de lanzamiento (inferencia,
no evento). Reportado, no fabricado.

---

## 1. Captura real (Arc mainnet) **[MEDIDO]**
- Rango reciente: **22.706.620–22.706.659**, `events=28`, `duplicates_total=0`.
- Contadores: **tokens 1 · swaps 23 · launchpad_events 5 · wallets 14 · dev_buys 0**.
- `launchpad_events` decodificados: `PartsDeployed`, `CurveOpened` (+ 1 desconocido).
- Token real (ver §0.1): `BTS` / "Buy The Sphere".
- Fila de swap de ejemplo (captura previa): tx `0xa1987189…`, wallet `0xb6a575…5424`, pool
  `0x82916bee…`, amount_in −11973, amount_out 10051798, dex uniswap_v3.

## 2. Integridad
- Idempotencia (re-poll mismo rango): `processed=36, duplicates=36`, contadores intactos.
- Kill/restart: ver §0.2.
- **7/7 tests OK** (`python -m unittest discover -s tests -t .`), incluido `test_token_created_decodes_name_symbol_creator`.
- Se corrigió un **HTTP 403** real (User-Agent de `urllib`) + corte por errores consecutivos.

## 2.1 `dev_buys_inferred` (inferido, NO evento de ingesta) — **[MEDIDO: 0 en el rango]**

Implementado como **VISTA** sobre lo ya capturado (no nueva ingesta), separada y marcada:
```sql
CREATE VIEW dev_buys_inferred AS
SELECT s.tx_hash, s.log_index, t.address AS token, s.wallet AS creator_wallet,
       s.ts AS swap_ts, t.created_ts AS token_created_ts, s.pool,
       1 AS is_inferred, 'inferred:swap_wallet_equals_token_creator_within_86400s' AS reason
FROM swaps s JOIN tokens t ON lower(t.creator) = lower(s.wallet)
WHERE t.created_ts IS NOT NULL AND s.ts IS NOT NULL
  AND s.ts >= t.created_ts AND s.ts <= t.created_ts + 86400;
```
Ventana **configurable** vía `Storage.query_dev_buys_inferred(window_seconds)` (default 86400).
Nunca se mezcla con la tabla confirmada `dev_buys` (que sigue separada).

**Resultado real (rango 22.706.600–22.706.849):** `dev_buys_inferred = 0`.
Capturamos 4 tokens reales (BTS/DOOMER/MOASS/…) y 91 swaps v3/v2, pero **ningún swap tiene
`wallet == creator` dentro de la ventana**.

**Por qué (evidencia, no excusa):** el dev-buy del lanzamiento ocurre en **Uniswap v4**. En la tx de
lanzamiento de BTS (`0xf9e865af…`) el **PoolManager v4 `0x8366a39cc670b4001a1121b8f6a443a643e40951`
aparece 3 veces** (topics `0xdd466e67…`, `0xf208f491…`, `0x40e9cecb…`) y hay 11 `Transfer` del token;
**no hay ningún Swap v3/v2**. Nuestro indexer Fase 1 solo captura topics `uniswap_v3/v2`, así que **no
indexa el swap v4** → la vista no encuentra coincidencia. **Confirmado honestamente: 0 en el rango.**

Fix propuesto (Fase 1.5): indexar el `Swap` de v4 en el PoolManager y mapear `poolId → token`; entonces
la inferencia `swap.wallet == tokens.creator` funcionará también para lanzamientos v4.

## 3. Bloqueos honestos
1. **Bitquery**: sin `BITQUERY_OAUTH`; no verificado que indexe Arc → fuente deshabilitada (RPC stopgap).
2. **v4 no indexado** → los dev-buys de lanzamiento (v4) no se capturan; `dev_buys_inferred=0` (ver §2.1).
3. **`swaps.token` no resuelto** → la inferencia es `wallet==creator` + ventana, no por token_id.
4. Swaps: `side`/`token`/`price_implied` quedan `null/unknown` (requieren orientación de pool+decimals).
5. Token `0x84d429ed…` sin identificar.

## 4. Qué NO soluciona
Fontanería de datos. **No resuelve smart money**; solo captura fiable.

## 6. Fase 1.5 — Uniswap v4 (PoolManager) — [MEDIDO]

### 6.1 ABI v4 verificado por keccak (no por orden)
Firmas del repo oficial `Uniswap/v4-core` (`src/interfaces/IPoolManager.sol`), canonicalizadas y hasheadas:
| Evento | topic0 (keccak) | ¿coincide con la tx BTS? |
|---|---|---|
| `Initialize(bytes32,address,address,uint24,int24,address,uint160,int24)` | `0xdd466e67…38` | **sí** |
| `ModifyLiquidity(bytes32,address,int24,int24,int256,bytes32)` | `0xf208f491…ec` | **sí** |
| `Swap(bytes32,address,int128,int128,uint160,uint128,int24,uint24)` | `0x40e9cecb…2f` | **sí** |
| `Donate(bytes32,address,uint256,uint256)` | `0x29ef05ca…cb` | no aparece en esa tx |
Los tres topics observados en `0x8366…0951` quedan **identificados por hash**: Initialize / ModifyLiquidity / Swap.

### 6.2 `pools_v4` (poolId → tokens) + `swaps.token`
`Initialize` decodificado → tabla `pools_v4(pool_id, currency0, currency1, fee, tick_spacing, hooks, sqrt, tick)`.
Ejemplo real: `0xf94477a1…a696` → currency0 `0x1efca933…` (BTS), currency1 `0x3600…0000` (USDC), fee 10000,
tick_spacing 200. Los `Swap` de v4 ahora rellenan `swaps.token` (currency0) y `swaps.pool = poolId`.

### 6.3 Cuantificación (rango 22.706.600–22.706.849)
| dex | swaps |
|---|---:|
| **uniswap_v4** | **472 (83,8%)** |
| uniswap_v3 | 88 |
| uniswap_v2 | 3 |
| **total** | **563** |
→ **Se estaban perdiendo ~84% de los swaps.** El v3/v2 "91" era solo el 16% de la actividad real.

### 6.4 `dev_buys_inferred` con BTS → sigue **0** (causa exacta)
El `Swap` de lanzamiento de BTS en el PoolManager tiene `sender = 0xb021be536808f551b31789422fd28a6c9c6e97da`
= **el Portal de Argus**, no el creator `0x4d43c873…`. El único wallet en el pool BTS es el Portal.
Por tanto la regla `swap.wallet == tokens.creator` **no aplica a lanzamientos v4**: el dev-buy se ejecuta
desde el Portal y los tokens llegan al creator por **ERC-20 `Transfer`** (que aún no indexamos).
**Inferencia correcta** (Fase 1.6): indexar `Transfer` y marcar dev buy cuando `to == creator` del token
lanzado, dentro de la ventana.

### 6.5 Backfill genesis→head — **[BLOQUEADO por escala, y premisa a corregir]**
La premisa "Arc lleva <2 semanas" **no coincide con lo medido**: génesis block 0 en
`2026-05-12T00:00:00Z` (ts 1778544000), head ~`22.7M` bloques ⇒ **~135 días**, no 2 semanas.
Un backfill genesis→head son ~22.7M bloques: **[EXTRAPOLADO]** ~251 h monohilo (≈10 días) o ~50 h con
5× paralelismo; no es viable en esta sesión. Propuesta: **backfill v4 acotado** (p. ej. desde el primer
lanzamiento de Argus / últimos N bloques) y decidir el rango contigo.

## 7. Fase 1.6 — Transfer + backfill acotado v4 — [MEDIDO/PARCIAL]

### 7.1 Bloque del lanzamiento (2026-09-16 00:00 UTC)
Búsqueda **binaria de timestamp** sobre bloques (no extrapolación): **bloque 21.068.653**, ts exacto
`1789516800` = `2026-09-16T00:00:00Z` (bloque previo 1 s antes). Cadencia alrededor de la fecha (10k-bloque):
`0.537 / 0.532 / 0.507 / 0.506 / 0.507` s/bloque → **estable**.

### 7.2 Transfer + nueva regla `dev_buys_inferred`
- Tabla `token_transfers`; evento `Transfer` (`0xddf252ad…`) indexado para los tokens de `tokens`.
- Regla nueva (reemplaza `swap.wallet==creator`): **`Transfer.to == creator` AND `Transfer.token == token
  lanzado`, dentro de la ventana (default 86400 s)**; `is_inferred=1`; vista separada de `dev_buys`.

### 7.3 Dev buy real BTS — **[CONFIRMADO]**
Indexando Transfers de BTS alrededor del lanzamiento (6 transfers, 1,3 s), aparece la fila inferida que
corresponde **exactamente** a la tx identificada `0xf9e865af…`:
```
tx_hash     0xf9e865af346be467d69dde1f2135927ecd06f86aafb7307fc340d9256a18b32a
log_index   29
token       0x1efca93316b36ccacd783f6be612ee2ea297160d   (BTS)
creator     0x4d43c873a0f8033f0f6864e4ffe2de0f85112917
amount      199736069605045847876
transfer_ts 1790348894   token_created_ts 1790348894   is_inferred 1
reason      inferred:transfer_to_creator_within_86400s
```

### 7.4 v4 en el loop principal
`RpcEventSource.poll()` (usado por `IndexerService`) incluye **Initialize + Swap** de v4 desde Fase 1.5, y
**Donate** ahora también (`v4_donate`). La captura en tiempo real incluye v4 por defecto. ✔

### 7.5 Backfill v4 launch→head — **[PARCIAL, no completado]**
Rango total launch→head = **21.068.653 → 22.710.028 ≈ 1.64M bloques**. Se añadió **chunking adaptativo**
(el RPC corta a 20.000 resultados y sugiere rangos). Ejecución acotada medida (100k bloques, `backfill_v4.db`),
timeout a 40 min registrando:
- `pools_v4`: **46.979** (pass Initialize sobre los 100k).
- `swaps` v4: **235.451** (pass Swap en curso hasta el bloque 21.094.150; ~9,2 swaps/bloque).
- `v4_events` (Donate): 0 (no llegó).

**[EXTRAPOLADO]** el rango completo es de **horas a días** y multi-GB; **no** completado en esta sesión.
Cuellos de botella medidos: chunking adaptativo (más requests), densidad de swaps, `commit` por fila en
SQLite, y falta de paralelismo/batching. Recomendación: ejecutarlo como job nocturno en VPS con batching +
timestamps por bloque en batch, y decidir el rango.

### 7.6 Suite
`python -m unittest discover -s tests -t .` → **Ran 10 tests — OK (0 fallos)**.

## 8. Fase 1.7 — Migración a PostgreSQL + batching + backfill resumible — [MEDIDO]

### 8.1 Storage PostgreSQL (`indexer/pg_storage.py`)
- `PostgresStorage` con **pool de conexiones** (`psycopg2.ThreadedConnectionPool`, 1–8) para escritura
  concurrente (indexer en vivo + backfill).
- **Inserción por lotes** con `psycopg2.extras.execute_values` (`page_size=1000`), `ON CONFLICT DO NOTHING`
  (adiós al commit por fila). Métodos batch: `insert_swaps / insert_pool_v4_rows / insert_transfers /
  insert_v4_events`.
- Mismo esquema lógico (tablas + **vista `dev_buys_inferred`**), `BIGINT`, y `meta` como **checkpoint**.
- SQLite sigue disponible (fallback) con los mismos métodos batch.

### 8.2 Backfill resumible (`indexer/backfill.py`)
- Checkpoint explícito por chunk en `meta[<job>_cursor]`: si se cae, **retoma desde el último chunk
  confirmado**, no desde cero. Selección de backend `--storage sqlite|pg --dsn ...`.
- Chunking **adaptativo** ante el límite de 20.000 resultados del RPC.

### 8.3 Prueba de throughput (200.000 bloques, rango 21.068.653–21.268.652) [MEDIDO]
| métrica | valor |
|---|---:|
| bloques | 200.000 |
| pools_v4 | 32.862 |
| swaps v4 | 35.807 |
| donates | 367 |
| filas | 69.036 |
| tiempo | **1.763 s (29,4 min)** |
| **filas/s** | **39,1** |
| **bloques/s** | **113,4** |
| splits / **failed_ranges** | 16.993 / **8.392** |

**Estimación honesta del rango completo** (21.068.653 → head 22.710.028 ≈ 1,64M bloques):
a 113 blk/s ≈ **4,0 h** de forma plana; **pero** (a) la densidad de swaps crece hacia el head
(~1,9/bloque reciente vs ~0,18 aquí) y (b) hay rate-limiting → **realista 5–8 h** con riesgo de reintentos.
**No es una extrapolación optimista; es un rango.** [DERIVADO]

### 8.4 ⚠ Blocker encontrado (integrity) — **[corregir antes del run completo]**
`failed_ranges = 8.392` (el adaptativo marca un rango como fallido a ≤50 bloques). A esa densidad (≤ ~10
logs/50 bloques) no es límite de tamaño: es **rate-limit (HTTP 403 / "rate limit exceeded")** que el código
trata como error de tamaño, hace split y **acaba descartando el rango en silencio** → **huecos de datos**.
**Fix requerido antes de lanzar el backfill completo:** distinguir `rate_limit` (reintentar con backoff) de
`result_limit` (hacer split), y **registrar los rangos no capturados** explícitamente (tabla
`data_gaps`) en vez de descartarlos. Sin esto, el backfill completo sería **incompleto y no auditable**.

### 8.5 Suite contra PostgreSQL [OK]
En VPS (PostgreSQL 16, contenedor temporal aislado): `INDEXER_TEST_DATABASE_URL=... python3 -m unittest
discover -s tests -t .` → **Ran 10 tests — OK (0 fallos)**. También **10/10** con SQLite en local.



