# Informe de auditoría — Bloque A (Custodia y Mini App)

**Proyecto:** ARC AI / SNIPER IA (`arc-intel`) · **Fecha:** 2026-09-27
**Alcance:** correcciones del **Bloque A** (A1–A5) sobre custodia y Mini App.
**Estado:** implementado en el árbol de trabajo · **no commit** · **no desplegado** (producción con la
versión previa hasta autorización).
**Contratos:** **no se modificó** `ArcIntelExecutor.sol` (V1) ni el tag `arc-intel-executor-v1`; no se
tocó ningún contrato (V2/V3 incluidos).

---

## Resumen ejecutivo

| # | Hallazgo | Estado |
|---|---|---|
| A1 | Retiros sin frenos (initData 24 h, destino arbitrario, sin 2FA/topes/aviso/kill-switch) | **Corregido** |
| A2 | `/custody/create` aceptaba `private_key` (import de clave) | **Corregido** |
| A3 | XSS en Mini App (links/logo/imágenes controlados por el creador) + sin CSP | **Corregido** |
| A4 | Descifrado de claves disperso (≥5 módulos) + sin auditoría/rotación de clave | **Corregido** |
| A5 | CORS con default de otro proyecto + RPC/chain con defaults inseguros | **Corregido** |

**Evidencia de tests:** Python **415 passed** (+1 fallo **ambiental** local de la Mini App, sin relación
con estos cambios) · Foundry **45 passed / 0 failed / 1 skipped** (contratos intactos).

---

## A1 — Retiros con frenos

**Reglas aplicadas**
- **Frescura de `initData` = 300 s** en endpoints sensibles: `/custody/create|withdraw|buy|sell|address|totp`
  y `/session/authorize`. La lectura (`/positions`, `/portfolio`, `/token`, …) mantiene 24 h.
- **Rate limit** por usuario en `/custody/*`: **20 llamadas / 60 s**.
- **2FA con TOTP** (implementación propia RFC 6238, sin dependencias) para **registrar dirección** y
  **retirar**. Secreto guardado **cifrado** (vía el módulo firmante).
- **Retiro solo a direcciones pre-registradas**; una dirección nueva queda **pendiente 24 h** antes de
  poder usarse. El alta **avisa por Telegram**.
- **Tope diario de retiro** por usuario (default **50 USDC**; `ARC_INTEL_WITHDRAW_DAILY_USDC`).
- **Aviso por Telegram** en cada retiro y alta de dirección, con botón **"🛑 No fui yo"** que **congela**
  la cuenta (deshabilita retiros y trading). Se desbloquea con **`/unfreeze <código>`** (TOTP).
- **Kill-switch global** para admin: **`/pause_custody`** / **`/resume_custody`** (detiene trading y
  retiros custodiales). El bot y los keepers comprueban el estado pausado/congelado.
- Nuevos endpoints: `GET /custody/totp`, `POST /custody/totp`, `GET /custody/addresses`,
  `POST /custody/address`.

**UI (paridad bot ↔ Mini App)**
- **Mini App** (Cartera): tarjeta **🔐 Seguridad** (activar 2FA, alta de dirección con código) y campo
  **2FA** en la fila de retirar.
- **Bot**: **`/security`** (genera secreto 2FA o lista direcciones), **`/addaddr <dir> <código>`**,
  botón **🛑 No fui yo**, **`/unfreeze`**, **`/pause_custody`**, **`/resume_custody`**.

**Archivos:** `bot/totp.py` (nuevo), `bot/store.py`, `bot/sign_server.py`, `bot/commands.py`,
`bot/i18n.py`, `miniapp/index.html`.

**Tests (evidencia)**
- `tests/test_sign_server.py`: `…private_key…`, `…no_key_leak`, **`test_custody_stale_initdata_rejected`**
  (initData de >5 min ⇒ **401**), `test_custody_not_allowlisted` (403), `test_custody_paused_blocks` (423).
- `tests/test_totp.py`: vectores **RFC 6238** + ventana ±1 + URI.
- `tests/test_custody_security.py`: retardo 24 h, contador diario, freeze/TOTP/pausa, auditoría.
- `tests/test_commands.py::test_security_enroll_and_addaddr`.

---

## A2 — Eliminación de la importación de clave privada

- `/custody/create` **rechaza** el campo `private_key` (**400 `private_key_not_allowed`**); solo crea
  wallets generadas por el bot (`execution.custody.new_wallet`).
- Confirmado por test HTTP: la respuesta de creación **no contiene** `private_key`.

**Archivos:** `bot/sign_server.py`.
**Tests:** `tests/test_sign_server.py::test_custody_create_rejects_private_key`,
`::test_custody_create_wallet_no_key_leak`.

---

## A3 — XSS en la Mini App

- **Saneador de URLs** `security/urls.py` (`safe_url`, `sanitize_dex`): solo URLs absolutas **`https://`**;
  se rechazan `javascript:`, `data:`, `http:` y payloads malformados (`"><img onerror=…>`).
- Aplicado en **servidor** (`bot/miniapp_data.py` → enlaces/webs/logo/embed de DexScreener) y en
  **cliente** (`httpsUrl()` en `miniapp/index.html` para `href`, `src` de logo e `iframe`).
- **`rel="noopener noreferrer"`** en los enlaces externos; se retiraron los `onerror` inline.
- **CSP estricta** en la respuesta de la página: `default-src 'self'`; `script-src` solo `'self'`,
  `https://telegram.org`, `https://esm.sh` y el **hash SHA-256 del script inline**; `frame-ancestors`
  limitado a `web.telegram.org` / `*.telegram.org`; `object-src 'none'`; `base-uri 'self'`.
  Cabeceras añadidas: `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`.
- Revisión de los usos de `innerHTML`: las interpolaciones de datos de cadena/chain pasan por `esc()`
  o `httpsUrl()`.

**Archivos:** `security/urls.py` (nuevo), `bot/miniapp_data.py`, `bot/sign_server.py`, `miniapp/index.html`.
**Tests:** `tests/test_urls.py` (`javascript:alert(1)`, `data:text/html`, `"><img onerror=…>`,
`sanitize_dex`, `_csp` con hash y `frame-ancestors`).

---

## A4 — Manejo de claves centralizado

- **`execution/signer.py`** (nuevo): **único módulo que descifra**. Ofrece operaciones
  (`withdraw`, `ensure_approval`, `swap`, `sign_session_order`) y `encrypt_secret`. Todos los call sites
  migrados (`bot/sign_server.py`, `bot/telegram.py`, `execution/autoprotect.py`,
  `execution/copy_keeper.py`, `execution/session_keeper.py`).
- **Cifrado con `MultiFernet`**: claves desde `ARC_INTEL_SESSION_ENC_KEYS` (primera = cifra; resto
  descifra) o `ARC_INTEL_ENC_KEY_FILE` (600, fuera del repo y de la carpeta de la BD); back-compat
  `ARC_INTEL_SESSION_ENC_KEY`. Procedimiento de **rotación** documentado en el docstring del módulo.
- **Tabla de auditoría append-only** `key_audit` (uid, motivo, llamador, ts) — **sin material de clave**.
- **Topes por wallet custodial** (defaults bajos): saldo máximo `ARC_INTEL_MAX_CUSTODY_BALANCE_USDC=200`,
  notional por trade `ARC_INTEL_MAX_TRADE_USDC=50`, por día `ARC_INTEL_MAX_DAILY_TRADE_USDC=200`.
- **Creación de custodia solo para `chat_id` del allowlist** de la beta (o admin).
- Un test verifica que **ningún log/excepción** filtra la clave ni el texto cifrado.

**Archivos:** `execution/signer.py` (nuevo), `bot/store.py`, `bot/sign_server.py`, `bot/telegram.py`,
`execution/{autoprotect,copy_keeper,session_keeper}.py`.
**Tests:** `tests/test_signer_only.py` (**falla si otro módulo referencia `decrypt_secret`**),
`tests/test_custody_security.py::SignerTests` (auditoría + rotación MultiFernet + error sin material).

---

## A5 — Red y origen correctos

- **CORS sin default**: `ALLOWED_ORIGIN = os.environ.get("ARC_INTEL_ALLOWED_ORIGIN", "")`; sin variable,
  **no se emite cabecera CORS**.
- **`execution/custody.py`** **exige** `ARC_RPC` y `ARC_INTEL_CHAIN_ID` (sin defaults) y añade
  **`verify_chain()`** (compara `eth_chainId` del RPC con la config). Se invoca **antes de firmar** cada
  transacción; si no coincide, **no firma**. Aplicado también a `session_keeper` (sin defaults de red).

**Archivos:** `bot/sign_server.py`, `execution/custody.py`, `execution/session_keeper.py`.

---

## Reconocimiento en producción (solo lectura, sin claves)

- **Red del servicio: testnet** (`ARC_RPC=https://rpc.testnet.arc.io`, `ARC_INTEL_CHAIN_ID=5042002`).
- **Custodias activas: 1** · **con saldo USDC > 0: 1** · **saldo total ≈ 39.994935 USDC**.

---

## Riesgos residuales / no cubierto

- La **rotación** de claves está soportada por código pero **no ejecutada** en producción.
- La clave de cifrado sigue leyéndose del **entorno del proceso** (se recomienda `ARC_INTEL_ENC_KEY_FILE`
  con permisos 600 vía **systemd credentials**, fuera del repo y de la carpeta de la BD).
- La **liquidez/ejecución real** sigue en **dry-run** (mainnet pendiente); los controles se han probado
  con tests y no contra mainnet.
- **Avisos por Telegram** (retiro/alta): dependen de red; van envueltos en try/except (no bloquean).
- Bloque de **contratos V2/V3** (si existe) **no incluido** aquí.

## Atestación

- No se imprimieron en la sesión **claves privadas**, `ARC_INTEL_SESSION_ENC_KEY` ni **tokens**.
- **No** se modificó `ArcIntelExecutor.sol` (V1) ni el tag `arc-intel-executor-v1`.
- **No** se hicieron **commits** ni **despliegues** durante el Bloque A.

## Reproducción

```
# Python
cd arc-intel && python -m pytest -q        # 415 passed (+1 ambiental local de la Mini App)
# Foundry (los contratos no se tocaron)
cd arc-intel/executor && forge test        # 45 passed, 0 failed, 1 skipped
```
