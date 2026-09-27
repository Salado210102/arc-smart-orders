# ARC AI — Mini App: Spec funcional completo

> Estado: **documento de diseño (Parte B)**. No hay UI construida. Parte C (construcción) empieza
> solo cuando este spec esté revisado y aprobado.
> Autor: equipo ARC AI. Fecha: 2026-09-27.

Este documento enumera **cada componente** que debe tener la Mini App (Telegram Mini App / web
móvil), describe su comportamiento, sus datos y su backend, y **mapea cada pieza a módulos que ya
existen** para no reconstruir nada. Donde algo no existe todavía, se marca **"[FALTA]"** con el
enfoque propuesto.

---

## 1. Objetivo y alcance

**Qué es.** Una interfaz no-custodial para operar tokens de Arc desde el móvil, dentro de Telegram
(TMA) y como web. Permite: comprar (firmando), ver posiciones, vender por %, configurar un plan de
salida (TP/SL/trailing) que se materializa en **pre-órdenes protectoras**, ver alertas con contexto
y ver qué billeteras sigue automáticamente.

**Qué NO es / no hace.**

- **No custodia**: la Mini App **nunca** tiene llaves del usuario. El usuario firma con su wallet
  (WalletConnect / inyectada); el backend solo **guarda la firma** y la envía on-chain.
- **No promete rentabilidad** y no es consejo financiero. Se muestran **ambas caras** (beneficio
  típico y riesgo de cola).
- No es un exchange ni un broker; no hay libro de órdenes propio. Toda ejecución va al
  `ArcIntelExecutor` (testnet hoy; **mainnet pendiente de auditoría**).

**Principio rector:** si algo puede fallar, **fail-safe** (no ejecutar) y **explicar** por qué.

---

## 2. Arquitectura

```
┌──────────────────────────────┐        ┌──────────────────────────────────────────┐
│ Mini App (TMA / web)         │        │ VPS                                       │
│  - HTML/JS en el navegador   │  HTTPS │  Caddy ──► bot/sign_server.py (:8790)      │
│  - WalletConnect (firma)     │◄──────►│    GET /order   POST /sign   GET /        │
│  - lee la cadena vía wallet  │        │  systemd: arc-intel-sign.service          │
└───────────────┬──────────────┘        │                                           │
                │                        │  arc-intel-indexer (PG)  ◄── Arc RPC      │
                │ firma (no llave)        │  arc-intel-alerts (loop 24/7)             │
                ▼                        └──────────────────┬───────────────────────┘
     wallet del usuario                                    │ keeper ejecuta (relayer)
                                                           ▼
                                            ArcIntelExecutor (Permit2 + v4 PoolManager)
```

- **Front**: `miniapp/index.html` (ya existe como esqueleto; se amplía).
- **Backend**: `bot/sign_server.py` (stdlib, ya existe) detrás de Caddy con HTTPS.
- **Datos**: PostgreSQL `arcintel` (indexer) + `bot_subs.db` SQLite (estado del bot/órdenes).
- **Cadena**: `ArcIntelExecutor` (`execution/preorders.py` construye el payload; el keeper firma nada,
  solo envía lo ya firmado).

### 2.1 Infra ya desplegada (Parte A, hecha)

- `app.basepump.dev` — **bloque de Caddy listo** (Reverse proxy → `127.0.0.1:8790`); se activa cuando
  exista el registro DNS A (Porkbun).
- `arc-sign.2.29.24.106.sslip.io` — **endpoint público HTTPS operativo ya** (cert Let's Encrypt) para
  la prueba end-to-end; sirve la misma Mini App y API.
- `arc-intel-sign.service` — servicio systemd que corre `python -m bot.sign_server` (bind
  `127.0.0.1:8790`), con `ARC_INTEL_ALLOWED_ORIGIN=https://app.basepump.dev`.
- CORS restringido al dominio real (**ya no `*`**).

---

## 3. Inventario: qué YA existe (reutilizar, no reconstruir)

| Capacidad | Módulo / función | Reutiliza en |
|---|---|---|
| Construir payload de firma | `execution/preorders.py::build_sign_payload` | Compra, Venta, Protect |
| Args de `execute(...)` | `execution/preorders.py::executor_call_args` | Keeper |
| Envío on-chain (firmado) | `execution/preorders.py::submit_execute` | Keeper |
| Typed data EIP-712 | `execution/eip712.py::order_typed_data` | Firma |
| Posición (coste medio) | `execution/positions.py::Position`, `apply_fill` | Posiciones |
| Cantidad a vender por % | `execution/positions.py::sell_quantity` | Venta |
| Reconciliación on-chain | `execution/positions.py::reconcile` | Posiciones |
| Plan de salida | `execution/strategy.py::ExitPlan`, `evaluate_exit` | TP/SL/trailing |
| Endpoints de firma | `bot/sign_server.py` (`GET /order`, `POST /sign`) | Compra/Venta/Protect |
| Fills idempotentes + posiciones | `bot/store.py::record_fill`, `get_position`, `list_positions` | Posiciones |
| Pre-órdenes | `bot/store.py::create_preorder`, `get_preorder_by_sign_token`, `attach_signature`, `preorders_for_token` | Protect, TP/SL |
| Ficha de token (precio/mcap/vol24/thin) | `bot/telegram.py::check_token` | Compra (preview), Check |
| Símbolo/logo/supply/decimals/balance | `bot/tokenmeta.py` | Compra, Posiciones |
| Thin-market | `indexer/alerts.py::is_thin_market` | Compra (aviso) |
| Reputación del creador | `indexer/creator_rep.py::creator_report` | Compra, Alertas |
| Señales | `indexer/stream_alerts.py` (dev_sell, volume_collapse, volume_spike, compound) | Alertas |
| Wallet tracking | `bot/wallet_track.py::scan_wallets` + `store.wallet_links/auto_subs` | Wallet tracking |
| Kill-switch (Protect) | `bot/commands.py::fire_preorders` + `preorders.py` | Protect |

**Datos disponibles (PG):** `tokens` (address, symbol, name, creator, launchpad, pool_id),
`launchpad_events` (TokenCreated), `legs` (wallet, token, block, side, token_qty, stable_value,
price), `pools_v4` (currency0/1, fee, tick_spacing, hooks, sqrt_price_x96, tick), `v4_liquidity`
(deltas de liquidez), `swaps`.

---

## 4. Componentes de la interfaz

Convención: cada componente = **C#**. Cada uno con `Props`, `Datos/Backend`, `Estados` y
`Casos límite`.

### C0 — Shell, navegación y estado global

- **Qué**: contenedor con barra inferior de pestañas: **Inicio · Mercado · Operar · Cartera ·
  Ajustes**. Cabecera con: estado de conexión de wallet, red (testnet/mainnet), idioma (EN/ES/中文),
  y un **badge [PAPER]** visible cuando no hay executor/relayer configurado.
- **Estado global**: `wallet {address, chainId, connected}`, `mode {PAPER|REAL}`, `lang`, `positions`,
  `settings` (kinds activas).
- **Regla**: si el mode es **PAPER**, **todos** los botones de compra/venta muestran "[PAPER]" y la
  confirmación aclara "simulado, no se envía nada on-chain".
- **Estados**: cargando / listo / sin conexión (banner "sin red").
- **Casos límite**: wallet en red equivocada → pedir cambiar a Arc (chainId 5042002 testnet / 5042
  mainnet); RPC caído → modo lectura con datos cacheados + aviso.

### C1 — Wallet (Cartera)

- **Qué**: conectar/ver/desconectar. Dos capacidades distintas y **separadas**:
  1. **Watch-only** (`store.link_wallet`): dirección pública para leer saldos y hacer wallet tracking.
  2. **Firma** (WalletConnect): solo cuando se va a firmar una orden; el usuario aprueba en su wallet.
- **Datos**: `tokenmeta.erc20_balance_raw` (USDC y token), `native_balance_eth`; `store.wallet_links`.
- **Estados**: desconectada / watch-only / con signer disponible / firma en curso / firma cancelada.
- **Casos límite**: `erc20_balance_raw` devuelve `None` (fallo RPC) → **no** interpretar como 0;
  mostrar "—" y reintentar. Dirección inválida → validar `^0x[0-9a-fA-F]{40}$` antes de guardar.
- **Reutiliza**: el patrón actual de `/wallet` (`bot/commands.py::wallet_screen`).

### C2 — Compra (flujo de 4 pasos)

**Paso 1 — Pegar CA / buscar**
- Input: dirección del token (0x + 40 hex). Validación: formato, existe en `tokens`, **no** es USDC.
- Si no existe en el índice → aviso "token desconocido / no indexado" + opción de verlo en explorer.

**Paso 2 — Preview del token (decisión informada)** — reutiliza `telegram.check_token`.
- Muestra: **símbolo + logo** (`tokenmeta`), **precio** (último `legs.price`), **market cap**
  (`price × totalSupply`), **volumen 24h** (suma `stable_value` de `legs` en 24h), **thin-market**
  (`is_thin_market`: no_trades / single_wallet), **reputación del creador** (`creator_report`:
  creados / volcados / %), **launchpad**, **liquidez**.
- **Liquidez [FALTA métrica robusta]**: hoy no hay un número USD fiable. Enfoque propuesto:
  derivar de `pools_v4.sqrt_price_x96` + deltas de `v4_liquidity`, o estimar con
  `stable_value` de los swaps iniciales; **etiquetar como estimación** hasta validarlo.
- Banderas visuales: 🟢 actividad / ⚠️ thin market / ⚠️ creador con historial de dump.

**Paso 3 — Monto, slippage y minOut**
- Montos rápidos ($10/20/50/100) + personalizado (USDC). Estimar `amount_in` (USDC → 6 dec) y
  `token_out` (usando precio del pool / spot).
- **Slippage** selector (0.5 / 1 / 3 / custom) → `min_out = token_out × (1 − slippage)`.
- Mostrar fee (1% modelo económico) y total a firmar.

**Paso 4 — Confirmar y firmar**
- Construir payload con **`preorders.build_sign_payload(...)`** (permit2 + order + `typedData`).
- Conectar wallet → `eth_signTypedData_v4` → `POST /sign {t, signature}` (guarda la firma; **no**
  ejecuta).
- Mostrar: "Orden armada. El keeper la ejecutará al cumplirse la condición". (Compra = orden límite /
  mercado según `min_out`.)

**Estados**: validando → preview → configurando → esperando firma → firmada → (ejecutada | cancelada |
expirada).
**Casos límite**: token sin pool (`pools_v4` ausente) → compra no ejecutable; sin saldo → aviso;
firma rechazada → volver a Paso 3 sin perder datos; `deadline` vencido → reconstruir payload.

### C3 — Posiciones

- **Qué**: lista de posiciones reales con: **cantidad**, **coste medio**, **PnL no realizado**
  (usando precio actual), **realizado**, y **badge de reconciliación**.
- **Backend**: `store.list_positions(user)` → `positions.py`. PnL no realizado =
  `(precio_actual − avg_cost) / avg_cost` (usa `strategy.pnl_pct`).
- **Reconciliación**: `positions.reconcile(pos, onchain_qty)` contra `erc20_balance_raw` real;
  si difiere → ⚠️ "revisar" (no ocultar).
- **Estados**: sin posiciones / cargando / reconciliado / desajuste.
- **Casos límite**: `qty=0` → cerrar posición; RPC `None` → "reconciliación no disponible", no marcar
  error.

### C4 — Venta

- **Qué**: sobre una posición real, botones **25% / 50% / 75% / 100%** + custom. "Vender todo".
- **Cálculo**: **`positions.sell_quantity(pos, pct, has_pending)`** (rechaza si hay operación
  pendiente, sin posición, o pct fuera de (0,1]).
- **Slippage/floor**: `min_out` con la misma lógica que compra (o "salir a cualquier precio" → suelo
  muy bajo, decisión ya confirmada).
- **Firma**: idéntica a la compra (`build_sign_payload` → WalletConnect → `/sign`).
- **Estados/casos límite**: `PositionError` → mensaje claro (`pending_operation`, `no_position`,
  `invalid_pct`); nunca calcular un % sobre una posición inexistente.

### C5 — Plan de salida: TP / SL / Trailing / Scale-out

- **Qué**: el usuario define un `ExitPlan` (`execution/strategy.py::ExitPlan`):
  `take_profit_pct`, `stop_loss_pct`, `trailing_stop_pct`, `scale_out=[(múltiplo, fracción), ...]`.
- **Motor**: `strategy.evaluate_exit(pos, price, plan)` decide la acción (stop_loss → trailing →
  take_profit → scale_out → hold). **Puro**, ya testeado.
- **Conexión con pre-órdenes (punto clave de diseño):**
  - El contrato hoy firma **una venta con `minOut` (un piso)** y `deadline`, ejecutable **una vez**.
  - Por tanto:
    - **Take-profit / límite**: se codifica como **venta con `minOut = entry×(1+TP)`**; el keeper la
      envía cuando el precio ≥ ese nivel (orden límite). ✔ encaja nativo.
    - **Stop-loss / trailing** ⚠️ **[LÍMITE REAL]**: el contrato **no** tiene un disparador nativo de
      "precio ≤ X" (un floor no expresa un techo). El **disparo vive en el keeper** (off-chain): el
      keeper evalúa `evaluate_exit` con el precio actual y, al cumplirse SL/trailing, envía la orden
      **ya firmada** con un `minOut` adecuado (piso). Riesgo: si el precio cae más rápido que la
      ejecución/inclusión, el `minOut` puede no llenarse.
    - **Scale-out**: cada tramo = **una pre-orden** (N firmas) o una orden por tramo firmada por
      lotes.
  - **Cancelación/expiración**: `cancelOrder` (consume nonce) + `deadline` (30 días por defecto).
- **UI**: formulario con sliders/inputs, vista previa "qué se firmará" (nº de órdenes = TP + SL +
  tramos), y aviso explícito de que SL/trailing **depende del keeper** y no es una garantía on-chain.
- **Estados**: sin plan / configurado (armado) / parcialmente firmado / disparado / expirado.
- **Casos límite**: sin posición → no se arma; precio desconocido → no evaluar; expiración → re-firmar.

### C6 — Protect (kill-switch) [ya existe en Telegram]

- **Qué**: botón "Armar protección" → pre-orden que **se dispara sola** ante dev-sell / compound /
  volume_collapse (vía `commands.fire_preorders`, **no** con `volume_spike`).
- **Backend**: `store.create_preorder(...)` estado `armed` → al disparar, `signed` → `executed`.
- **UI**: estado de la orden (armada / firmada / ejecutada / cancelada), motivo del disparo.

### C7 — Alertas con contexto visual

- **Qué**: las MISMAS señales que ya llegan por Telegram
  (`stream_alerts`: **dev_sell**, **volume_collapse**, **volume_spike**, **compound**), pero
  visualizadas con **contexto**:
  - **Gráfico de precio** por bloque (serie `legs.price`) y **volumen por bucket**
    (`load_volume_buckets`) con el punto de la alerta marcado.
  - Ficha del token (precio/mcap/vol24/thin/creador) embebida.
  - **Z-score** de colapso/spike y **%** del dev-sell.
- **Filtros**: por tipo (sincronizado con `/settings` del bot: `ALL_KINDS`) y por token suscrito.
- **Reutiliza**: motor de señales + `apply_collapse_cooldown` (anti-spam) + `format_alert_rich`
  (se adopta a HTML de la Mini App).
- **Casos límite**: token sin historial suficiente → gráfico "datos insuficientes"; sin suscripciones
  → estado vacío con CTA a Mercado.

### C8 — Wallet tracking (ver qué sigue automáticamente)

- **Qué**: lista de **billeteras enlazadas** y de **tokens auto-seguidos** (con su **origen**:
  manual / auto), y por qué (candidate_tokens desde `legs`).
- **Backend**: `store.wallet_links`, `store.auto_subs`, `wallet_track.scan_wallets`; acciones
  `link_wallet` / `unlink_wallet` / `add_auto_sub` / `remove_auto_sub` / `promote_to_manual`.
- **UI**: tab de cada wallet con saldo (watch-only) y sus tokens; botón "dejar de seguir" / "seguir
  manual".
- **Casos límite**: wallet sin actividad → estado vacío; RPC `None` → "no disponible" (no interpretar
  como "vendió").

### C9 — Historial

- **Qué**: fills confirmados (`store` `fills`), órdenes (`preorders`) y ejecuciones (tx hash + enlace
  a explorer). Idempotencia por `fill_id = tx_hash:log_index`.
- **Estados**: vacío / con datos / fallo de carga.
- **Casos límite**: tx fallida/revrtida → mostrar estado real, no "ejecutada".

### C10 — Stats

- **Qué**: valor de señal con **ambas caras** (nº alertas, mediana de movimiento, CI, % positivos,
  `max_missed_upside`), separando **PAPER** y **REAL**. Reutiliza `paper_eval`/`/stats`.
- **Regla de honestidad**: siempre mostrar la cola de riesgo, no solo la media.

### C11 — Ajustes

- **Qué**: idioma (EN/ES/中文), red (testnet/mainnet), toggles de alertas (`ALL_KINDS`), slippage por
  defecto, `deadline` de órdenes (30 días), y `minOut` por defecto (−30% o "cualquier precio").
- **Backend**: mismas claves de estado del bot (`lang:{chat}`, kinds, settings).

### C12 — Ayuda y disclaimers

- **Qué**: docs (enlace), guía de seguridad (no-custodia, qué firma exactamente), disclaimer legal.
- **Regla**: en **cada** pantalla de firma, resumen legible de **qué autoriza** la firma (vender X%
  de TU token, `minOut`, a TU dirección, antes de `deadline`, una vez).

---

## 5. Contratos de API del backend

**Existentes (ya operativos, `sign_server.py`):**

| Método | Ruta | Entrada | Salida |
|---|---|---|---|
| GET | `/` (o `/index.html`) | — | HTML de la Mini App |
| GET | `/order?t=<sign_token>` | token de un solo uso | `{preorder:{id,token,pct,status}, payload}` o 404/409 |
| POST | `/sign` | `{t, signature}` | `{ok:true,id}` o 404/409 |

**De lectura — IMPLEMENTADOS y verificados por HTTPS** (auth del usuario con `initData`,
[`bot/telegram_auth.py`], cabecera `X-Telegram-Init-Data`):

| Método | Ruta | Auth | Devuelve | Reutiliza |
|---|---|---|---|---|
| GET | `/health` | no | `{ok:true}` | — |
| GET | `/token?address=` | no | ficha (precio/mcap/vol24/thin/creador) | `miniapp_data.load_token_card` |
| GET | `/positions` | **sí** | posiciones + PnL no realizado + resumen | `miniapp_api.position_views`, `positions.reconcile` |
| GET | `/wallet` | **sí** | wallet enlazada + auto-subs | `miniapp_api.wallet_view` |
| GET | `/buy_quote?token=&amount_usdc=&slippage=` | **sí** | quote de compra + payload firmable (preview) | `execution.quotes`, `preorders.build_sign_payload` |
| POST | `/buy_order` | **sí** | crea y **persiste** una orden de compra; devuelve `sign_token`/`sign_url` | `store.create_preorder(kind='buy')`, `execution.quotes` |
| GET | `/alerts` | **sí** | alertas recientes de **tus tokens** (persistidas en el bucle) | `store.recent_alerts` |
| GET | `/series?token=` | **sí** | precio + volumen por bucket (para el gráfico) | `miniapp_data.load_series` |
| POST | `/plan` | **sí** | crea venta condicional (protect/límite) por % y devuelve `sign_url` | `execution.quotes.build_sell_payload` |
| POST | `/cancel` | **sí** | cancela una orden (reposo del keeper) | `store.cancel_preorder` |

> `/buy_quote` devuelve `{token, pool, quote, payload}` con `preview:true, persisted:false` (vista
> previa). `POST /buy_order` persiste la orden (`kind='buy'`, estado `armed`) y devuelve un
> `sign_token`; el flujo de firma es el **mismo** (`GET /order` + `POST /sign`). Las órdenes `buy`
> **no** se disparan solas: `preorders_for_token` solo devuelve `kind='sell'` (Protect).

**Propuestos [FALTA]:**

| Método | Ruta | Devuelve | Reutiliza |
|---|---|---|---|
| GET | `/token` | liquidez USD (estimación) | `pools_v4`, `v4_liquidity` |

Regla transversal: endpoints **de lectura** no requieren firma; endpoints que **crean órdenes**
devuelven el payload a firmar y **nunca** ejecutan sin `POST /sign` posterior.

Auth: `initData` (HMAC-SHA256 con el token del bot) — probado end-to-end. **[FALTA]** rate-limit
por IP y CSP.

---

## 6. Modelo de datos usado

- **PG (indexer)**: `tokens`, `launchpad_events`, `legs`, `pools_v4`, `v4_liquidity`, `swaps`.
- **SQLite (estado)**: `positions`, `fills`, `preorders` (con `signature`, `sign_token`,
  `sig_payload`), `wallet_links`, `auto_subs`, `paper_*`, `cooldowns`, `settings/kinds`.
- **Idempotencia**: `fills.fill_id = tx_hash:log_index`; `preorders.sign_token` **de un solo uso**.

---

## 7. Seguridad

- **No-custodia total**: el backend no tiene llaves; `submit_execute` exige `preorder.signature`
  (lanza `no_signature` si falta).
- **CORS restringido** al dominio real (`ARC_INTEL_ALLOWED_ORIGIN`), ya aplicado.
- **HTTPS** vía Caddy/Let's Encrypt; `sign_server` enlaza **solo** a `127.0.0.1`.
- **`sign_token` de un solo uso** por orden; `POST /sign` rechaza `executed`.
- **[FALTA]**: rate-limit por IP en `/order` y `/sign`; rotación de `sign_token` tras uso; límite de
  tamaño de body; cabeceras CSP en el HTML; expiración del `sign_token`.

---

## 8. No-objetivos (fase 1)

- Sesiones/llaves delegadas (Opción 3 / ERC-4337) — **diferida**.
- Libro de órdenes propio, cross-chain/bridge, copytrading — botones "pronto", no ahora.
- Mainnet con fondos reales — **bloqueado por auditoría + despliegue**.

---

## 9. Orden de construcción (Parte C — por aprobar, no construir aún)

1. **Contrato de datos + endpoints de lectura** (`/token`, `/positions`, `/wallet`): ✅ hecho
   (`/alerts` pendiente).
2. **C2 Compra** (flujo de 4 pasos): ✅ **backend** (`/buy_quote`, `/buy_order` con `kind='buy'`
   persistido) + ✅ **UI** (`miniapp/index.html`: pestañas Compra/Posiciones/Cartera, firma con
   WalletConnect). ⏳ falta el **keeper** que envíe la orden de compra firmada on-chain (necesita
   relayer con gas).
3. **C3/C4 Posiciones + Venta** (`list_positions`, `sell_quantity`).
4. **C5 Plan de salida** (TP/SL/trailing) sobre `ExitPlan` + pre-órdenes; con el aviso del límite de
   SL (keeper).
5. **C6/C7 Protect + Alertas con gráfico**.
6. **C8 Wallet tracking**, **C9 Historial**, **C10 Stats**, **C11/C12 Ajustes/Ayuda**.
7. **Seguridad [FALTA]**: rate-limit, CSP, rotación.

Cada entregable: **tests primero** (Python, patrón actual), luego UI, luego prueba real (testnet).

---

## 10. Trazabilidad (resumen de reutilización)

| Componente | Reutiliza | A construir [FALTA] |
|---|---|---|
| C2 Compra | `build_sign_payload`, `check_token`, `tokenmeta`, `is_thin_market` | liquidez USD, UI |
| C3 Posiciones | `list_positions`, `reconcile`, `pnl_pct` | precio actual por token, UI |
| C4 Venta | `sell_quantity`, `build_sign_payload` | UI |
| C5 TP/SL/Trailing | `strategy.ExitPlan/evaluate_exit`, `create_preorder` | motor de disparo en keeper, UI |
| C6 Protect | `fire_preorders`, `store.preorders` | UI |
| C7 Alertas | `stream_alerts`, `load_volume_buckets`, `format_alert_rich` | gráfico, UI |
| C8 Wallet tracking | `wallet_track.scan_wallets`, `store.wallet_links/auto_subs` | UI |
| C9/C10 | `fills`, `preorders`, `paper_eval` | UI |
| C11/C12 | i18n, `ALL_KINDS` | UI |
