# Informe de auditoría — Bloque B (contratos ArcIntelExecutor V2 / V3)

**Proyecto:** ARC AI / SNIPER IA · **Fecha:** 2026-09-27
**Alcance:** revisión de seguridad de `ArcIntelExecutorV2.sol` y `ArcIntelExecutorV3.sol`.
**Restricción respetada:** **no se tocó** `ArcIntelExecutor.sol` (V1) ni el tag `arc-intel-executor-v1`.
**Estado:** B1 **corregido** (con test) · B2–B8 **recomendaciones** (pendientes de tu OK; requieren
redeploy de los contratos para surtir efecto).
**Suites:** Foundry **47 passed / 0 failed / 1 skipped**.

---

## Modelo y garantías (verificadas)

- **No custodial**: no hay `withdraw`/`rescue`; el output va directo al `recipient` en la misma tx.
- **Owner solo puede pausar y editar política**; nunca toca fondos ni altera una orden firmada.
- **Sesiones hard-scoped on-chain**: `poolId`, `tokenIn`, `maxPerOrder`, `maxTotal`, `spent`,
  `minOutFloor`, `expiry`, **revocable**; `recipient` forzado a `user`.
- **Guardas presentes**: `nonReentrant` en ambos entrypoints, `minOut` aplicado, **nonce de un solo uso**
  por usuario, `unlockCallback` solo invocable por el `PoolManager`, firma EIP-712 con dominio
  (name/version/chainId/verifyingContract) y `s`-bound + `v∈{27,28}` (sin maleabilidad).
- **Tests existentes**: reentrancy, hook malicioso, fuzz de `minOut`/nonce, invariantes, pause, expiry,
  token mismatch, dust. Se añadió el test de B1.

---

## Hallazgos

### B1 — `execute` (v1) aceptaba `recipient == address(0)` — **CORREGIDO (Low)**
- **Antes:** una orden v1 firmada con `recipient = 0x0` enviaría la salida al **dirección cero**
  (fondos perdidos). Es auto-infligido (el usuario firma), pero es un footgun de UI/orden.
- **Fix:** `if (order.recipient == address(0)) revert BadRecipient();` en `execute` de **V2 y V3**
  (antes de tocar el `Permit2`).
- **Evidencia:** `testRevertZeroRecipientV1` en `ArcIntelExecutorV2.t.sol` y `ArcIntelExecutorV3.t.sol`.

### B2 — `deadline` no está firmado en el path v1 (witness lo omite) — **Recomendación (Low)**
- El `ORDER_TYPEHASH` v1 incluye `poolId/zeroForOne/minOut/recipient/orderNonce` pero **no `deadline`**.
  El `deadline` se valida contra la calldata, así que un relayer **podría ampliarlo** (dentro de la vida
  del nonce). `minOut` y `recipient` sí van firmados ⇒ impacto limitado a **ventana temporal**.
- **Recomendación:** añadir `deadline` al typehash del witness (cambio **rompiente**: nuevo contrato +
  actualizar `execution/preorders.build_sign_payload` y la firma del cliente).

### B3 — V3 `allowAllPools` salta la política de pools **y de hooks** — **Recomendación (Medium, operacional)**
- `_checkPool` retorna antes de validar hook si `allowAllPools` está activo ⇒ se permiten **hooks
  arbitrarios** (posible hook malicioso). Es una decisión de owner.
- **Recomendación:** usar `allowAllPools` **solo en testnet**; en **mainnet** habilitar por
  `setAllowedPool` / `setAllowedHook` explícitos. Opción: `allowAllPools` gated por un `immutable
  isTestnet` y/o monitorización de hooks permitidos.

### B4 — `DOMAIN_SEPARATOR` calculado en deploy (no reconcilia `chainid`) — **Recomendación (Low)**
- Si la cadena sufriese un **fork/cambio de `chainid`**, el separador quedaría stale (riesgo de replay
  entre cadenas en ese escenario).
- **Recomendación (EIP-712 best practice):** calcular el separador dinámicamente o cachearlo y
  recalcular si `block.chainid` cambia.

### B5 — Guardas de sesión no incluidas en `nonReentrant` (informational)
- `authorizeSession` / `revokeSession` / `cancelOrder` no están en `nonReentrant`. No mueven fondos; es
  intencional. Sin acción.

### B6 — Re-`authorizeSession` resetea `spent` (informational)
- Re-autorizar una `sessionKey` re-define el scope y pone `spent = 0` (por diseño: re-scope). Sin acción.

### B7 — `unlockCallback` confía en el `recipient` decodificado (informational)
- Solo lo puede llamar el `PoolManager` y los datos los genera el propio executor ⇒ seguro.

### B8 — Protección frente a sandwich limitada por `minOut` (informational)
- Los swaps usan el límite de precio por defecto (`MIN+1`/`MAX-1`); la única protección es el `minOut`
  firmado. Recomendación: slippage ajustado en el cliente.

---

## Resumen

| # | Hallazgo | Severidad | Estado |
|---|---|---|---|
| B1 | `recipient == 0` en `execute` v1 | Low | **Corregido + test** |
| B2 | `deadline` no firmado (v1) | Low | Recomendación (rompiente) |
| B3 | `allowAllPools` salta política de hooks | Medium (operacional) | Recomendación |
| B4 | Domain separator estático ante fork | Low | Recomendación |
| B5–B8 | Observaciones | Info | Sin acción |

## Notas de despliegue

- El fix **B1 cambia el bytecode** de V2/V3 ⇒ **requiere redeploy** (nuevas direcciones) para surtir
  efecto on-chain. **No se ha redeployado**; los ejecutores de testnet siguen con el bytecode previo.
- V1 (`ArcIntelExecutor.sol`) **intacto**.

## Reproducción

```
cd arc-intel/executor && forge test      # 47 passed, 0 failed, 1 skipped
```
