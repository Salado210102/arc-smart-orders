# ARC AI — Opción 3: Session keys (trading de un toque)

> Objetivo: **quitar la firma por operación** para que comprar/vender sea **1 toque** (latencia = red).
> Estado: **diseño**. Implica un **contrato nuevo** que se auditará junto con el punto 3 (auditoría).
> Fecha: 2026-09-27.

---

## 1. El problema (real, medido en uso)

- **Vincular** la wallet en el bot (`/link_wallet`) es **watch-only** (solo la dirección): **no puede
  firmar**. Para firmar hace falta una wallet con llaves.
- El flujo actual (**Opción 2**, órdenes pre-firmadas) exige **una firma por orden**
  (WalletConnect → QR/deep-link, o popup). Para meme-tokens eso es **demasiado lento**: "cuando
  firmas, el token ya voló".
- Mejoras ya hechas (sin contrato): preferir **wallet inyectada** (abrir la Mini App dentro del
  navegador de la wallet → firma instantánea) y **reusar la sesión de WalletConnect** (firmar una
  vez, luego silencioso). Ayudan, pero **siguen requiriendo una firma**.

**Conclusión:** para sniper de verdad hace falta **autorización de sesión previa** (Opción 3).

---

## 2. Objetivo

El usuario autoriza **una sola vez** una **llave de sesión acotada**; después el **keeper firma y
envía** cada orden **sin intervención del usuario** (1 toque). El usuario puede **revocar** cuando
quiera.

---

## 3. Arquitecturas posibles

### A) ERC-4337 (smart account + módulo de session keys)
- Smart account (Safe / Kernel / ZeroDev / Biconomy) + módulo de sesión; el usuario firma una "userOp"
  de autorización; el keeper usa la session key para firmar userOps.
- **Pros:** estándar, revocable, gas abstracción (paymaster).
- **Cons:** dependencia de **bundler/paymaster**, más superficie, **auditoría** del stack, más infra.

### B) **Extender `ArcIntelExecutor` con sesiones** (RECOMENDADA)
Reusa lo que ya tenemos (Permit2 + v4, no-custodia) y añade sesiones:
- **Setup (una vez, por token):** el usuario firma **una tx**:
  - `token.approve(Permit2, cap)` + `Permit2.approve(token, executor, cap, expiry)` (allowance, **sin
    firma por orden**), y
  - `authorizeSession(sessionKey, scope)`.
- **Operar:** el keeper llama `executeWithSession(order, sessionSig)`; el contrato:
  1. verifica que `sessionKey` está **autorizada** y **vigente**;
  2. valida el **scope** (tokenIn/Out, side, `maxAmount`, `minOut` floor, pool en allowlist);
  3. **tira de los fondos vía `Permit2.transferFrom`** (allowance, sin firma del usuario);
  4. hace el swap v4 y envía la salida al **recipient** (fijo = usuario).
- **Pros:** mínimo, self-contained, **reusa la auditoría** de la base; sin bundler.
- **Cons:** cambio de contrato → **nueva auditoría**; el usuario hace **una tx de setup** por token.

### C) Híbrido
- Implementar **B** ahora; migrar a **A** (4337) si queremos gas abstracción/bundler más adelante.

**Decisión propuesta: B.**

---

## 4. Scope de la sesión (límites duros)

| Campo | Ejemplo | Para qué |
|---|---|---|
| `sessionKey` | addr | la clave que firma las órdenes |
| `token` | 0x… | token permitido |
| `side` | buy \| sell | dirección permitida |
| `maxAmountPerOrder` | 50 USDC | tope por operación |
| `maxTotal` | 200 USDC | tope acumulado |
| `minOutFloorBps` | 7000 (−30%) | nunca peor que este suelo |
| `expiry` | +24 h | caducidad |
| `revoked` | bool | revocación |

**El contrato impone los límites**, no la confianza en el keeper.

---

## 5. Seguridad (análisis honesto)

- **Qué PUEDE** la session key: operar **solo** dentro del scope (token/side/topes/suelo/expiry).
- **Qué NO PUEDE**: retirar fondos, cambiar el `recipient`, exceder topes, operar otros tokens/pools,
  actuar tras `expiry` o tras `revoke`.
- **Naturaleza**: sigue siendo una **hot key acotada**. Se mitiga con: topes bajos, expiración corta,
  allowlist de pools, y **revocación** on-chain.
- **Almacenamiento**: la session key se guarda **cifrada** en el bot (nunca en claro en logs/repo).
- **Auditoría obligatoria** antes de mainnet.

---

## 6. Flujo de usuario

1. **Setup (una vez)**: vincular wallet (watch-only) + firmar la **autorización de sesión** + la
   **allowance** de Permit2 (una firma / una tx). El bot guarda la session key (cifrada).
2. **Operar**: **1 toque** → el keeper firma y envía. Sin wallet, sin QR.
3. **Revocar**: botón (on-chain `revokeSession` + local).

---

## 7. Fases de implementación

1. **Diseño** (este doc) + decisión de arquitectura. ✅ hecho (arquitectura **B**).
2. **Contrato** `ArcIntelExecutorV2` con sesiones + **tests Foundry**. ✅ hecho
   (`src/ArcIntelExecutorV2.sol`; **13/13 tests** de la v2; suite Foundry **41 passed**, v1 intacta).
   - `authorizeSession`/`revokeSession`; `executeWithSession(order, sig)`.
   - Scope on-chain: pool + tokenIn + `maxPerOrder` + `maxTotal` + `minOutFloor` + `expiry` +
     `recipient == user` + nonce single-use; pull vía **Permit2 `transferFrom`** (allowance, sin firma).
   - EIP-712 propio (`DOMAIN_SEPARATOR`), baja-s, recover.
3. **Backend**: generación + **cifrado** (Fernet) + scope + endpoints
   (`/session/authorize`, `/session/revoke`, `/sessions`) ✅; firma EIP-712 de la `SessionOrder` ✅
   (recupera la session key). **Pendiente:** el `keeper` que envíe `executeWithSession`
   (requiere la **v2 desplegada** por el Safe).
4. **UI**: onboarding "activar trading 1-toque" (envía las txs de setup), estado de sesión, revocar. ✅
   (`miniapp/index.html`: pestaña Cartera → "⚡ Trading 1-toque"; el firmante ahora envía txs).
   - **Una activación = 2 sesiones** (compra `tokenIn=USDC` + venta `tokenIn=token`) → **6 txs una vez**.
   - **Vender** por sesión: botones 25/50/75/100% en Posiciones → `POST /sell_order` (1 toque).
   - Si no hay sesión, "Comprar" ofrece **"⚡ Activar 1-toque y comprar"** (no manda a firmar).
5. **Keeper de sesión**: `execution/session_keeper.py` firma `SessionOrder` con la session key y envía
   `executeWithSession` (sin firma del usuario). ✅ (dormido hasta el allowlist del pool).
5. **Auditoría** (punto 3) del contrato v2.
6. **E2E testnet** → mainnet ✅ (v2 desplegada).

### Política de pools (v3) — sin allowlist por token
`ArcIntelExecutorV3` añade **`setAllowedHook(hook, bool)`** y **`setAllowAllPools(bool)`**: el owner
habilita **toda una launchpad** (por hook) o **todo** de una vez → **no hay que allowlistear token a
token** (era inviable para sniper). `_checkPool` permite si `allowAllPools || allowedPools[poolId]
|| allowedHooks[hook]`.
- **`ArcIntelExecutorV3` = `0xC9E5d10086591b562061890515F140D256b9Afd2`** (desplegada; owner = Safe).

### Despliegue testnet (2026-09-27)
- **`ArcIntelExecutorV2` = `0xb6393A1b2d98A2851236E31E4a67cE8d56653B56`** (chainId 5042002)
- `owner` = Safe `0xe911D6F5f3a7D2f06dcD32006318ED5EF95986b7` · `paused` = false
- `poolManager` = `0x8366a39CC670B4001A1121B8F6A443A643e40951`
- Sin pools pre-permitidos: el Safe allowlistea con `setAllowedPool(poolId, true)`.
- Los servicios (`arc-intel-sign`, `arc-intel-alerts`) apuntan a la v2.
- v1 (`0x89dF…35E8`) sigue desplegada pero en desuso.

> ⚠️ **Requisito para ejecutar de verdad:** el Safe debe **allowlistear el pool** con
> `setAllowedPool(poolId, true)` (la v2 se desplegó con allowlist vacía). Sin eso, `executeWithSession`
> revierte (`PoolNotAllowed`) y la orden queda `armed`.

---

## 8. Relación con el punto 3 (auditoría)

El contrato v2 (con sesiones) **es** lo que hay que auditar. **Punto 3 = auditoría de la v2.** No
tiene sentido auditar la v1 y luego rehacer: se audita la versión final.

---

## 9. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Hot key comprometida | Scope + topes + expiry corto + revocación |
| Keeper hace algo fuera de scope | Los límites son **on-chain** |
| Fuga de la session key | Cifrado en reposo; nunca en logs |
| Contract bug | Tests exhaustivos + **auditoría** |
| Dependencia de infra | B no usa bundler (menos superficie) |
