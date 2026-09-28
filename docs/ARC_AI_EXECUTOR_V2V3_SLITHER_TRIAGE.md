# Slither Triage — ArcIntelExecutor V2 / V3

> Revisión estática de `ArcIntelExecutorV2.sol` y `ArcIntelExecutorV3.sol` (Bloque B, B1).
> **Contratos sin cambios** por Slither. Compilación vía Foundry (`via_ir`), solc 0.8.26.

## Run
- Tool: **Slither** (`/usr/local/bin/slither`), `--compile-force-framework foundry`.
- Comando: `slither src/ArcIntelExecutorV2.sol` y `slither src/ArcIntelExecutorV3.sol` (desde `arc-intel/executor/`).
- Resultado (idéntico en V2 y V3): **102 detectores**, **14 results** cada uno:
  `reentrancy-balance` (High) · `unchecked-transfer` (High) · `unused-return` (Medium) · `timestamp` (Low) ·
  `assembly` (Info) · `cyclomatic-complexity` (Info) · `naming-convention` (Info).

## Hallazgos y triage

### reentrancy-balance — High — **FALSO POSITIVO (por diseño)**
- `_swapAndSettle` (#292-305): `outBefore = balanceOf(recipient)` (#300) → `poolManager.unlock(...)` (#301)
  → `amountOut` y chequeo `amountOut < minOut` (#304).
- **No aplica:** (1) `execute` / `executeWithSession` son **`nonReentrant`**, un hook no puede reentrar;
  (2) la medición es el **delta de saldo del propio recipient** = lo que el usuario **realmente recibió**;
  una *disminución* solo **hace fallar `minOut` y revierte** (fail-safe); una *subida* (un hook hostil
  regalando tokens) solo **ayuda** y no causa pérdida; (3) pool/token sujetos a la **política del owner**.
- **Acción:** ninguna. Demostrado con `testHostileAllowedHookIsContained` (V3): reentrada bloqueada.

### unchecked-transfer — High — **NO EXPLOTABLE aquí (fail-safe); nota de best-practice**
- `execute`/`executeWithSession` (`transfer(user/leftover)`) y `_settle` (`transfer(poolManager, amount)`).
- **Por qué es seguro:** `_settle` corre justo antes de `poolManager.settle()`; si el `transfer` no pagó,
  la contabilidad v4 no se liquida y `unlock` **revierte** (fail-safe). El refund de dust, si un token
  devuelve `false` sin revertir, solo deja dust **en el executor** (sin custodia, sin pérdida).
- **Recomendación (requiere cambio de código EXCLUIDO por la regla):** usar transferencia comprobada
  (SafeERC20). **NO aplicado** — tocar V2/V3 exige parar y pedir OK. Documentado para el auditor.

### unused-return — Medium — **INFORMATIONAL**
- `poolManager.unlock(...)` (se ignora el `bytes` del callback) y `poolManager.settle()` (se ignora `paid`).
  Ninguno es necesario: la liquidación la garantiza la contabilidad del manager, no el valor devuelto.

### timestamp — Low — **ACEPTADO**
- `block.timestamp` en `order.deadline` / `s.expiry`: guardas estándar de UX/MEV; el drift del validador no
  afecta a la seguridad de fondos (`minOut`/caps son la garantía económica).

### assembly / cyclomatic-complexity / naming-convention — Info
- `assembly`: `ecrecover` con chequeo de `s`-bound y `v∈{27,28}` (patrón OZ). `executeWithSession`
  complejidad 15 (varias guardas de sesión). `DOMAIN_SEPARATOR()` / `_DOMAIN_SEPARATOR` / `_CHAIN_ID`
  no son mixedCase (constantes EIP-712 reconocidas). Sin acción.

## Confirmación empírica
- **Invariantes (5000×100)**: V2 y V3 — `spent ≤ maxTotal`, sesión revocada/expirada no llena, `recipient ==
  user`, sesión solo toca su poolId/tokenIn, nonce de un solo uso, executor sin saldo, pause absoluto.
- **Unit**: `testHostileAllowedHookIsContained`, `testHookRevokedBlocks`, `testAllowedHookOnlyCoversItsOwnHook`,
  `testAllowAllPoolsPermitsArbitraryPool` (V3). (V1 ya tenía `testUncheckedTransferRevertsWholeTx`.)

## Conclusión
Sin **High/Medium aplicables**. `reentrancy-balance` es falso positivo por diseño; `unchecked-transfer` es
fail-safe (mejora opcional = cambio de V2/V3, **requiere autorización**). Sin cambios de código por Slither.
