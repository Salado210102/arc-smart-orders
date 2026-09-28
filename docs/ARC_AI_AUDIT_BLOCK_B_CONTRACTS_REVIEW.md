# Informe de auditoría — Bloque B (contratos ArcIntelExecutor V2 / V3)

**Proyecto:** ARC AI / SNIPER IA · **Fecha:** 2026-09-27
**Alcance:** revisión de seguridad de `ArcIntelExecutorV2.sol` y `ArcIntelExecutorV3.sol`.
**Restricción respetada:** **no se tocó** `ArcIntelExecutor.sol` (V1) ni el tag `arc-intel-executor-v1`.
**Estado:** **B1–B4 corregidos** (con tests) · B5–B8 observaciones (sin acción).
**Nota:** B1/B2/B3 **cambian el bytecode** de V2/V3 ⇒ requieren **redeploy** para surtir efecto on-chain.
**Suites:** Foundry **51 passed / 0 failed / 1 skipped** · Python **415 passed** (+1 ambiental local).

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

### B2 — `deadline` ahora firmado en el path v1 — **CORREGIDO (Low)**
- El `ORDER_TYPEHASH` v1/V3 ahora incluye **`uint256 deadline`** y el `witness` lo incorpora; se
  actualizó `WITNESS_TYPE_STRING` (contrato **y** Python `execution/eip712.py`) y el typehash del witness.
  Un relayer ya **no** puede ampliar la validez sin invalidar la firma.
- **Evidencia:** `testWitnessBindsDeadline` (V2 y V3) + `tests/test_eip712.py`
  (`WITNESS_TYPE_STRING` y `witness["deadline"]`).

### B3 — V3 `allowAllPools` limitado a testnet — **CORREGIDO (Medium, operacional)**
- V3 tiene ahora `bool public immutable isTestnet` (constructor). **`setAllowAllPools(true)` revierte
  con `AllowAllNotAllowed`** si `!isTestnet` ⇒ en **mainnet** la política por pool/hook
  (`setAllowedPool`/`setAllowedHook`) es obligatoria. Los deploy scripts pasan `false` (mainnet,
  owner=Safe) y `true` (testnet, owner=relayer).
- **Evidencia:** `testMainnetCannotAllowAll` en `ArcIntelExecutorV3.t.sol`.

### B4 — `DOMAIN_SEPARATOR` dinámico (fork-safe) — **CORREGIDO (Low)**
- V2/V3 cachean `_DOMAIN_SEPARATOR` + `_CHAIN_ID` y exponen `DOMAIN_SEPARATOR()` (view) que **recalcula
  si `block.chainid` cambió**. `_sessionDigest` usa `DOMAIN_SEPARATOR()`.
- **Evidencia:** `testDomainSeparatorForkSafe` en `ArcIntelExecutorV2.t.sol`.

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
| B2 | `deadline` no firmado (v1) | Low | **Corregido + test** |
| B3 | `allowAllPools` salta política de hooks | Medium (operacional) | **Corregido + test** (`isTestnet`) |
| B4 | Domain separator estático ante fork | Low | **Corregido + test** |
| B5–B8 | Observaciones | Info | Sin acción |

## Notas de despliegue

- El fix **B1 cambia el bytecode** de V2/V3 ⇒ **requiere redeploy** (nuevas direcciones) para surtir
  efecto on-chain. **No se ha redeployado**; los ejecutores de testnet siguen con el bytecode previo.
- V1 (`ArcIntelExecutor.sol`) **intacto**.

## Reproducción

```
cd arc-intel/executor && forge test      # 51 passed, 0 failed, 1 skipped
```
