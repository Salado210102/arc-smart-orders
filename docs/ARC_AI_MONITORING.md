# ARC AI — Vigilancia (monitoring) robusta: diseño

> Objetivo: que el bot **vigile todo lo necesario** sobre los tokens que le importan al usuario
> (los que **tiene** y los que sigue) y avise de **anomalías** de forma fiable, sin perder señales.
> Fecha: 2026-09-27. Estado: diseño + hardening implementado (ver §4).

---

## 1. Pipeline real (medido)

```
Arc RPC
  └─ ingest_new()                     [indexer/ingest.py]
       1. backfill_v4_run()          → swaps (v4)          (+ v3/v2 en indexer)
       2. resolve_senders.run_blocks → tx.from (materializa trader)
       3. materialize_traders_batched
       4. append_legs_pg()           → legs (wallet,token,pool,block,log_index,side,
                                             token_qty,stable_value,price)  cursor=legs_cursor
  └─ bot/telegram.py (loop, --interval 300 s)
       fetch_new_legs(cursor, head) ─► IncrementalState.apply_legs(legs, creators)
                                          ├─ volume buckets por token
                                          ├─ posiciones (wallet,token) del creator
                                          ├─ dev_sell / volume_collapse(interno) / volume_spike / compound
       apply_collapse_cooldown(.)   ─► anti-spam
       store.enqueue_alert_many()   ─► aqueue (SQLite)
       fire_preorders()             ─► Protect (dev_sell/compound)
       scan_wallets()               ─► auto-sub de tokens que la wallet enlazada tiene
       dispatch()                   ─► envía a suscriptores (matches por token+kind, dedup persistente)
       save_state(state.pkl)        ─► cursor + estado
```

Universo de señales hoy: **dev_sell**, **volume_spike**, **compound** (dev_sell+colapso) y
`volume_collapse` (solo interno). Detecciones que **existen pero NO se usaban en vivo**:
`liquidity_removal_alerts` (retirada de liquidez).

---

## 2. Fallos de robustez encontrados (con impacto)

| # | Fallo | Impacto | Gravedad |
|---|-------|---------|----------|
| G1 | `creators`/`symbols` se cargan **una sola vez** al arrancar | Un token creado después del arranque **no se reconoce su creator** → **dev-sell no detectado** justo en los tokens más nuevos (los más propensos a rug) | **Alta** |
| G2 | `liquidity_removal` **no** está en el bucle en vivo (solo batch) | Se **pierde la retirada de liquidez** = señal de rug de primer orden | **Alta** |
| G3 | Solo se vigila al **creator**; un dump de **equipo/ballena** no marcado como creator **no** se ve | Se pierden salidas grandes que no vienen del creator | Media-Alta |
| G4 | `save_state` usa `pickle.dump` **no atómico** (sin temporal+rename) | Un corte a mitad corrompe `state.pkl` | Media |
| G5 | `MAX_TOKENS=30`: los auto-subs de tokens **tenidos** compiten con el tope manual | Un holding podría **no** quedar vigilado | Media |
| G6 | Sin métrica de **lag** (head−cursor) ni conteo de señales por ciclo | No se ve si la vigilancia se atrasa | Baja-Media |
| G7 | Tokens sin pool en `pools_v4` no generan legs | No hay vigilancia posible para ellos | Informativo |
| G8 | Al **añadir un campo** al dataclass `IncrementalState`, un `state.pkl` **antiguo** no tiene ese atributo → `AttributeError` → **crash-loop** | La vigilancia **se cae por completo** al desplegar | **Crítica** |
| G9 | `scan_wallets` corría **en el hilo principal** (RPC serial) | Las alertas se **retrasaban** minutos en RPC lento | **Alta** |
| G10 | El resumen por ciclo solo se logueaba si `ingest_note=="ok"` (nunca con ingesta OK) | **Ceguera total** de observabilidad en producción | Media |

---

## 3. Principios de la vigilancia robusta

1. **No perder señales** por estado obsoleto → refrescar metadatos **cada ciclo**.
2. **Multiseñal** (defensa en profundidad): dev-sell, compuesta, spike, **retirada de liquidez**,
   **venta grande (ballena/equipo)**.
3. **Fail-safe**: si el RPC falla, **no** avanzar cursor ni interpretar fallo como "cero".
4. **Estado durable** (escritura atómica + copia) y **reconstruible** desde histórico.
5. **Idempotencia** y anti-spam (cooldowns por token+kind).
6. **Observabilidad**: lag, tokens vigilados, señales por tipo, errores de ingesta.

---

## 4. Hardening implementado

### R1 — Refresco de creadores/símbolos cada ciclo
Cada ciclo se refrescan `creators` (y `symbols`) **solo para los tokens presentes en los nuevos
legs** (`load_creators_for`). Coste mínimo, elimina G1.

### R2 — Retirada de liquidez en vivo
`load_liquidity_removals(since_block=…)` + emisión de **`liquidity_removal`** con su propio cursor
(`liq_cursor`). Severidad por ratio retirado y rol (creator). Señal nueva en la UI.

### R3 — Venta grande (ballena/equipo)
En `apply_leg`: si una **venta** (no del creator) supera un umbral absoluto
(`large_sell_usd`, por defecto **$5 000**) y es comparable al volumen reciente, se emite
**`large_sell`** (severidad por USD). Cubre G3 sin necesitar atribución de holders.

### R4 — Estado durable
`save_state` escribe a `*.tmp` y hace `os.replace` (atómico); `load_state` cae a `*.bak` si el
principal está corrupto.

### R5 — Token tenido nunca se queda sin vigilar
`add_auto_sub` puede **exceder** `MAX_TOKENS` (`allow_over_cap=True`): un holding siempre queda
vigilado (los subs manuales mantienen su tope).

### R6 — Observabilidad
El log por ciclo incluye `lag = head − cursor`, `watch` (suscriptores), `signals` por tipo y
`queue`/`dispatched`. **Corregido** el condicional que impedía loguear (G10): ahora se loguea
**cada** vuelta, con `ingest` incluido.

### R7 — Estado retrocompatible (pickle)
`IncrementalState.__setstate__` rellena con su **default** cualquier campo ausente al deserializar.
Un `state.pkl` de una versión anterior **nunca** vuelve a tumbar el bucle (G8). Probado.

### R8 — Escaneo de wallets fuera del camino crítico
`scan_wallets` corre en un **hilo dedicado** con su **propia conexión** SQLite y cadencia (~180 s).
El RPC de saldos **nunca** retrasa la detección/entrega de alertas (G9).

### Nota operativa — ingesta por RPC
`run_service.sh` arranca con ingesta **activa** (`--no-ingest` para desactivarla): cada vuelta hace
`ingest_new` (RPC) **antes** de procesar alertas. Si el RPC va lento, la vuelta entera se alarga.
La métrica `lag` y el `ingest` del log lo hacen visible. Alternativa futura: desacoplar la ingesta
en su propio servicio de forma definitiva.

---

## 5. Qué NO entra (y por qué)

- **Honeypot / mint / pause / blacklist**: requieren decodificar eventos del contrato del token
  (no están en el índice). **[FALTA]**, fase futura con un decodificador de token.
- **Concentración de holders / top-10**: necesita snapshots de `token_transfers` agregados.
  **[FALTA]** (aproximable con `legs` más adelante).
- **Cadencia sub-minuto para tenidos**: subirla multiplica coste de RPC; se deja configurable
  (`--interval`).

---

## 6. Cómo se prueba

- Unit: refresco de creators, `large_sell`, `liquidity_removal` (severidad), escritura/bajada
  atómica del estado, cap-bypass de auto-sub.
- Integración: el bucle aplica legs sintéticos y verifica señales + dispatch.
- Producción: verificar en VPS `lag`, `signals` y que no hay errores de ingesta.
