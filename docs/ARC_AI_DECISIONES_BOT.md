# Arc AI — Registro de decisiones (bot / terminal)

> **Documento vivo.** Aquí se apunta TODO lo que vamos decidiendo. **Nada se implementa** hasta que
> hagamos la **revisión final** de este documento. Cada punto lleva estado:
> **CONFIRMADO** (acordado) · **ABIERTO** (por decidir) · **PENDIENTE REVISIÓN** (para el repaso final).
>
> Última actualización: **2026-09-27**

---

## 0. Contexto
- Ya existe y está en producción el **bot de alertas** de arc-intel (avisos de peligro, beta).
- Ya existe el **executor** probado end-to-end en testnet (v1/v2/v3), listo para auditoría.
- **Modo elegido (2026-09-27): CUSTODIAL — "Modo Maestro/Banana".** El bot crea y custodia una wallet
  rápida por usuario (clave **cifrada** con `ARC_INTEL_SESSION_ENC_KEY`), con flujo **depósito → compra
  instantánea → retiro**. La custodia **sustituye** a la firma por orden como camino de velocidad.
- Este registro cubre la **nueva dirección** (terminal/sniper estilo GMGN, red Arc) y lo que decidamos.

---

## 1. Producto y enfoque
| # | Decisión | Estado |
|---|---|---|
| P1 | Construir una **Telegram Mini App (TMA)** estilo GMGN/DexScreener, no solo comandos de texto. | CONFIRMADO |
| P2 | **CUSTODIAL (Modo Maestro/Banana)**: el bot crea/custodia una **wallet por usuario** (clave cifrada, **retiro en cualquier momento**). Sustituye al no-custodial. | CONFIRMADO (2026-09-27) |
| P3 | Reutilizar el **executor** ya probado (v1/v2/v3) como capa de ejecución; en custodial, **el bot firma** con la wallet del usuario. | CONFIRMADO |
| P4 | El **detector de rug pulls** (ya construido) es el gancho de seguridad del producto. | CONFIRMADO |
| P5 | **Bridge** (Base/Solana/Arbitrum → Arc USDC). En Modo Maestro lo puede operar el bot con la wallet custodial. | CONFIRMADO |
| P6 | Banner en vivo del **pozo del concurso** (contador + FOMO) dentro de la TMA. | CONFIRMADO |

## 2. Modelo de negocio
| # | Decisión | Estado |
|---|---|---|
| N1 | Tarifa **1%** por operación. | CONFIRMADO |
| N2 | Reparto de la comisión: **5% premio trader + 5% premio afiliado + 30% referidos + 30% infra + 30% equipo = 100%**. | CONFIRMADO |
| N3 | Coste fijo de infra de referencia: **300 USD/mes** (RPC + servidores + monitoreo). | CONFIRMADO |
| N4 | **Break-even:** ~**100,000 USD/mes** de volumen (~3,300 USD/día) solo para cubrir infra. | CONFIRMADO |
| N5 | Regla dura: **pagos < ingresos** (premios 10% + referidos hasta 30% = **40%**; rebajas VIP salen del equipo, no se suman). | CONFIRMADO |
| N6 | **Infra primero**, beneficio del equipo **después**; premios = gasto **topado** (10%), nunca "lo que sobre". | CONFIRMADO |
| N7 | Descuento de bienvenida temporal por referido: **1% → 0.9%**. | ABIERTO (definir duración) |
| N8 | Rebaja VIP (para KOLs): hasta ~35%, **sale del beneficio**, nunca se suma; suelo ~0.65% neto. | ABIERTO (definir niveles) |
| N9 | Referidos: **30% de por vida sobre la comisión NETA** del referido (nunca sobre el volumen bruto). Mercado: Trojan ≤35%, BullX 30%, Maestro 25%. | CONFIRMADO |

## 3. Concurso por volumen (sustituye a la lotería)
| # | Decisión | Estado |
|---|---|---|
| C1 | **NO es lotería de azar.** Es un **concurso por mérito**: gana quien más volumen mueve en la ventana. | CONFIRMADO |
| C2 | Dos rankings **separados**: **trader** (volumen propio) y **afiliado** (volumen de sus referidos). | CONFIRMADO |
| C3 | Reparto del premio **50/50** (5% trader + 5% afiliado). | CONFIRMADO |
| C4 | Cadencia: **ambos cada 12 horas** (2 rondas/día). | CONFIRMADO |
| C5 | Ventanas **UTC**: Ronda 1 = 00:00→12:00; Ronda 2 = 12:00→00:00. Publicación **1 h después** (01:00 / 13:00). | CONFIRMADO |
| C6 | Pozo por ronda = **10% de las comisiones de ESA ronda** (5%+5%) → 10% diario, presupuesto intacto. | CONFIRMADO |
| C7 | Publicación de **ganador + cantidad** (ambas categorías) en el **canal oficial + bot** (FOMO). | CONFIRMADO |
| C8 | Al verificar el ranking: usar **datos del bot (on-chain)**, público y auditable. | CONFIRMADO |
| C9 | Si alguna vez hubiera azar (no es el caso): **VRF/commit-reveal**, nunca "hash del bloque". | CONFIRMADO |

## 4. Anti-abuso (concurso)
| # | Decisión | Estado |
|---|---|---|
| A1 | Rankings separados → **sin doble cómputo** (el volumen propio no cuenta en el de afiliados). | CONFIRMADO |
| A2 | **Volumen neto**, sin **round-trips** (compra-venta del mismo token en segundos). | CONFIRMADO |
| A3 | **Excluir auto-operaciones** y **tokens propios** del participante. | CONFIRMADO |
| A4 | Referidos válidos: cuentas **distintas**, con **antigüedad mínima**, sin patrón de granja. | CONFIRMADO |
| A5 | **Defensa económica:** lavar volumen paga 1% de fee > pozo del 10% → inflar volumen sale a pérdida. | CONFIRMADO |

## 5. Lo que NO se hace (descartado)
| # | Descartado | Motivo |
|---|---|---|
| X1 | ~~Bot que genere/guarde billeteras (custodia).~~ **ADOPTADO** → ver **P2 (Modo Maestro)**: ya **no** se descarta. | Riesgo asumido; mitigado con clave cifrada + retiro libre (§7 legal). |
| X2 | **Lotería de azar** como motor de retención. | Riesgo regulatorio (juego). Se sustituye por concurso por volumen. |
| X3 | Repartos que suman **>100%** o rebajas que se suman al reparto. | Rompía la economía. |
| X4 | Aleatoriedad por **hash del bloque**. | Manipulable por quien produce el bloque. |
| X5 | ~~Bridge que deje fondos en una billetera del bot.~~ Ya **no aplica**: la custodia es el modo elegido (P2). | — |

## 6. UX / TMA (a detallar)
| # | Punto | Estado |
|---|---|---|
| U1 | Terminal con gráficos, slippage deslizable, botones de compra rápida **con firma del usuario**. | ABIERTO (alcance) |
| U2 | Pestaña **Bridge** (Base/Solana/Arbitrum → Arc USDC); en Modo Maestro lo opera el bot (wallet custodial). | ABIERTO |
| U3 | **PnL / historial** visual (verde/rojo) + estado "RUGGED" en trades afectados. | ABIERTO |
| U4 | Firma biométrica (FaceID/TouchID) **solo sobre wallet del usuario** (no del bot). | ABIERTO |
| U5 | Menú inline estilo Maestro (8 filas) + idiomas EN/ES/中文 + pegar-CA + positions. | HECHO (bot actual) |
| U6 | **Logos de token**: fuente = Argus `TokenCreated.image_uri` (IPFS→gateway), fallback DexScreener. | HECHO (en alertas) |
| U7 | **Connect wallet** watch-only (no-custodial) + panel; comando `/connect`. | HECHO |

## 7. Legal (a revisar antes de implementar)
| # | Punto | Estado |
|---|---|---|
| L1 | Concurso por volumen: confirmar encaje legal (mérito, no azar). | PENDIENTE REVISIÓN |
| L2 | Custodia: **ADOPTADA** (Modo Maestro). Revisar **responsabilidad sobre fondos de terceros** y seguros/garantías. | PENDIENTE REVISIÓN |
| L3 | **Divulgación publicitaria** de KOLs (marcar patrocinado). | PENDIENTE REVISIÓN |
| L4 | KYC/AML según jurisdicción: **sí aplica** (el bot custodia fondos de terceros). Revisar **antes de mainnet**. | PENDIENTE REVISIÓN |

## 8. Pendiente de decidir (para la revisión final)
- Duración del descuento de bienvenida (N7) y niveles VIP (N8).
- Alcance exacto de la TMA (qué pestañas primero).
- Wallet del usuario: **custodial** (Modo Maestro) → sin WalletConnect por orden; retiro libre en cualquier momento.
- Venues de swap en Arc (v4 vía executor; Argus; otros).
- Qué parte del **bot de alertas actual** se reutiliza tal cual vs se integra en la TMA.
- Moneda/representación del pozo y pagos (USDC, on-chain).
- Cuándo arranca el primer concurso y cómo se comunican las reglas.
- **URL de documentación** (botón Help): hoy apunta al repo GitHub; sustituir por **web/Notion propia**
  cuando exista (configurable con `ARC_INTEL_DOCS_URL`, sin tocar código).
- **Botones "pronto"**: Signals · Copytrade · Bridge · Premium (y la **TMA / terminal**).
- **Trading real**: desplegar el executor en **mainnet** + **auditoría**. En Modo Maestro firma el bot
  con la wallet custodial (no exige firma del usuario por orden). (Hoy: solo testnet.)

## 9. Artefactos y estado
| Artefacto | Estado |
|---|---|
| Modelo económico | `docs/ARC_AI_ECONOMIC_MODEL.md` + `.csv` (sin commitear) |
| Bot de alertas (arc-intel) | En producción (beta) |
| Executor | Probado en testnet (v1/v2/v3); paquete de auditoría congelado (tag `arc-intel-executor-v1`) |
| Registro de decisiones | este documento (sin commitear) |

---

## 10. Registro cronológico (append)
- **2026-09-26** — Se define la nueva dirección (terminal/TMA no-custodial, red Arc). Se descarta custodia,
  lotería de azar y economía rota. Concurso por volumen (trader/afiliado), 50/50, cada 12 h, UTC.
  Reparto 5/5/30/30/30 (actualizado 2026-09-27; antes 5/5/20/30/40). Publicación 1 h después del cierre.
  Documento de modelo económico creado.
- **2026-09-27** — Bot: menú inline estilo Maestro (8 filas) + idiomas EN/ES/中文 (ancho igual, persistente
  por usuario); botón **Connect wallet** watch-only (no-custodial); **logos de token** desde Argus
  `image_uri` (IPFS→`gateway.pinata.cloud`, fallback DexScreener) en las alertas; `/list` con símbolo;
  envío directo por HTTP + conexión propia del hilo de comandos (latencia ~0.24 s/botón). Tests 50/50.
- **2026-09-27 (botón a botón)** — Revisados con el usuario: `/list` (nombres por tabla o RPC + dirección
  corta); `/check` ampliado (nombre, launchpad, creador, antigüedad, actividad, **precio**, **market cap**,
  **volumen 24h**, estado, explorer); `/settings` con **interruptores** (dev_sell / volume_collapse /
  compound); `/wallet` con **saldo** y botones (cambiar / desconectar / actualizar); `/help` con enlace a
  **Documentación**. Comandos registrados EN/ES/ZH (botón “/” en web y móvil) y **teclado fijo eliminado**.
  Pendiente: URL de documentación propia, botones "pronto" (Signals/Copytrade/Bridge/Premium + TMA),
  trading real (mainnet + firma + auditoría).
- **2026-09-27 (señal de volumen)** — Nueva señal **`volume_spike`** (z ≥ +2.5 sobre `lookback` **y**
  ≥ **$500** en el bucket; el suelo absoluto evita ruido). Se muestra con **doble cara** explícita (puede
  preceder un pump *o* un rug). Además, **confirmación por volumen**: un **dev-sell** con volumen reciente
  (≤6 buckets) ≥ $500 **sube de severidad** y se marca `[high volume]` (hace las alertas de riesgo más
  precisas). Integrada en `/settings` (interruptor `volume_spike`), etiquetas i18n, cooldown anti-spam y
  dispatch existentes. El **kill-switch `Protect` NO** se dispara con un spike (solo con riesgo:
  dev_sell / compound / volume_collapse). Tests: +3 nuevos (61 en módulos tocados; total 220, con 1 fallo
  **ambiental** de la Mini App en local, no regresión).
- **2026-09-27 (infra Mini App)** — DESPLEGADO: `arc-intel-sign.service` (systemd) corre
  `python -m bot.sign_server` en **`127.0.0.1:8790`** (solo local) detrás de **Caddy** con HTTPS.
  **CORS restringido** (ya no `*`; `ARC_INTEL_ALLOWED_ORIGIN=https://app.basepump.dev`). Se añadió un
  bloque de Caddy **aditivo** para `app.basepump.dev` (BasePump intacto) y un endpoint público temporal
  `arc-sign.2.29.24.106.sslip.io` (cert Let's Encrypt). **Prueba E2E real por HTTPS: PASS** (miniapp 200,
  `/order` 200, `/sign` 200 con firma guardada, desconocido 404, CORS correcto). DNS `basepump.dev` está
  en **Porkbun** (`*.basepump.dev` → parking) → queda **pendiente** el registro A `app` → `2.29.24.106`.
  Creado el **spec funcional completo** de la Mini App: `docs/ARC_AI_MINIAPP_SPEC.md` (Parte B; sin
  construir UI todavía).
- **2026-09-27 (Parte C, entregables 1–2)** — Capa de datos de solo lectura (`bot/miniapp_api.py`,
  **pura**, 11 tests) y **auth `initData`** (`bot/telegram_auth.py`, HMAC-SHA256, 6 tests) + endpoints
  en `sign_server.py`: `/health`, `/token` (público), `/positions` y `/wallet` (con
  `X-Telegram-Init-Data`). Desplegado y **verificado por HTTPS público**: `/token` con un token real
  (BCAT), `/positions` y `/wallet` con `initData` firmado con el token real del bot; `/positions` sin
  auth → **401**, token inválido → **400**. Suite Python **244 passed** (1 fallo ambiental local de
  Mini App). Pendiente: `/alerts` con gráfico, `/plan`, `/cancel`, rate-limit y UI.
- **2026-09-27 (Parte C, entregable 3 — C2 Compra, backend)** — `execution/quotes.py` (**puro**,
  7 tests): resuelve el lado estable del pool, calcula `expected_out`/`minOut` (precio + slippage) y
  arma el payload firmable reutilizando `preorders.build_sign_payload` (el contrato es **agnóstico a
  la dirección**: compra = `token_in` estable). `miniapp_data.load_pool` (PG) + endpoint
  **`GET /buy_quote`** (auth). Desplegado y **verificado por HTTPS público** con un pool v4 real
  (token *Tower*): $10 → 2,434,291 tokens, `minOut` 2,385,606 con 2%; payload con executor testnet
  (`0x89dF…35E8`, chainId 5042002), `zeroForOne:true`, `typedData` correcto. Suite **254 passed**.
  Pendiente C2: **persistir la orden** (compra) + keeper, y la **UI** de los 4 pasos.
- **2026-09-27 (Parte C, entregable 4 — C2 completo: persistencia + UI)** — `store.preorders` ahora
  tiene columna **`kind`** (`'sell'` por defecto; migración no destructiva). Las órdenes de **compra**
  se guardan con `kind='buy'` y **no** se disparan solas (`preorders_for_token` filtra `kind='sell'`,
  así Protect sigue igual). Nuevo endpoint **`POST /buy_order`** (auth) que persiste la orden y
  devuelve `sign_token`/`sign_url`; la firma usa el **mismo** flujo `GET /order` + `POST /sign`.
  Reescrita **`miniapp/index.html`**: pestañas **Compra** (4 pasos: CA → ficha → monto/slippage →
  cotizar → armar y firmar), **Posiciones** (PnL no realizado + resumen) y **Cartera** (wallet
  watch-only + auto-seguidos), con `initData` de Telegram y firma WalletConnect. **Prueba E2E por
  HTTPS público**: `POST /buy_order` → `persisted:true`; `GET /order` → payload; `POST /sign` → ok;
  fila verificada `kind='buy', status='signed', user=<wallet>`; limpieza hecha. Suite **257 passed**
  (1 fallo ambiental local). Pendiente: **keeper** de compra (relayer con gas) y `/alerts`.
- **2026-09-27 (alertas centradas en el usuario)** — Decisión de producto: las alertas genéricas de
  mercado no aportan. Se **retira `volume_collapse` de la interfaz**: fuera de `/settings` y de
  `/stats`; `PUSH_EXCLUDED_KINDS` la excluye de **todo** envío (sigue alimentando `compound` de forma
  interna). Nuevo foco: el bot **vigila los tokens que el usuario tiene**. Al registrar un fill que
  deja **posición > 0** se **auto-suscribe** el token y al **cerrar** la posición se deja de seguir
  (`store.record_fill` → `add_auto_sub`/`remove_auto_sub`; patrón del wallet tracking). `Protect`
  dispara con **dev_sell / compound** (sin collapse). Tests: +3 (auto-watch, parcial mantiene), +1
  (dispatch no empuja collapse) y ajustes de settings → **260 passed**. Desplegado (servicios activos).
- **2026-09-27 (vigilancia robusta — hardening)** — Investigación a fondo del pipeline
  (`docs/ARC_AI_MONITORING.md`) y corrección de **fallos reales**: (G1) refresco de
  creadores/símbolos **cada ciclo** para los tokens nuevos (antes el dev-sell de tokens nuevos se
  perdía); (G2) **retirada de liquidez en vivo** (`liquidity_removal`, con `liq_cursor`); (G3)
  **venta grande** (`large_sell`, ≥$5k y ≥50% del volumen reciente, no-creator); (G8, **crítico**)
  **crash-loop** al desplegar: un `state.pkl` antiguo no tenía los campos nuevos del dataclass →
  `IncrementalState.__setstate__` retrocompatible; (G9) `scan_wallets` **movido a su propio hilo**
  (RPC serial ya no retrasa las alertas); (G10) el resumen por ciclo **no se logueaba** con ingesta
  OK → ahora se loguea **cada vuelta** con `lag`/`signals`/`watch`. Estado durable (escritura atómica
  + `.bak`), y auto-sub de tokens **tenidos** que **supera** el tope manual (`MAX_TOKENS`). Señales
  nuevas visibles en `/settings`: `liquidity_removal`, `large_sell`. Tests **265 passed** (1 fallo
  ambiental local). Desplegado y verificado: bot sano, `lag:0`, log por ciclo.
- **2026-09-27 (Parte C — pestaña Alertas con gráfico)** — **Opción A** implementada: las alertas se
  **persisten** (`store.alerts`, único por token+kind+block) en cada vuelta, y nuevos endpoints
  `GET /alerts` (auth; alertas de **tus tokens**) y `GET /series?token=` (auth; precio + volumen por
  bucket). **UI**: nueva pestaña **Alertas** con la lista (kind tipado por color de severidad) y
  **gráfico SVG** al tocar: **sparkline de precio + barras de volumen** con **línea de la alerta**.
  E2E por HTTPS público OK (`/alerts` 401 sin auth / 200 con auth; `/series` con serie real). Tests
  **269 passed** (1 fallo ambiental local).
- **2026-09-27 (keeper + plan/cancel + catálogo)** — **Keeper** `execution/keeper.py`: envía on-chain
  las órdenes **de compra firmadas** (permissionless; **dormido** hasta que exista
  `ARC_INTEL_RELAYER_KEY`); `claim_order` atómico evita doble envío; en fallo vuelve a `signed` para
  reintento. Disparo rápido tras firmar (hilo) + red de seguridad en el bucle. Endpoints **`POST /plan`**
  (crea venta condicional EIP-712 por %) y **`POST /cancel`** (reposo del keeper; la cancelación
  on-chain la firma el usuario con `cancelOrder`). `quotes`: `sell_quote` + `build_sell_payload`.
  Creado **`docs/ARC_AI_FEATURES.md`**: catálogo COMPLETO de funcionalidades + hooks de marketing (EN)
  + límites   + disclaimers. Tests **281 passed** (1 fallo ambiental local). Pendiente real: relayer con
  gas (§7) y auditoría mainnet.
- **2026-09-27 (escáner de contrato anti-rug)** — `indexer/token_risk.py`: **Keccak-256 en Python
  puro** (sin dependencias; validado contra vectores conocidos) para selectores, + escaneo del
  bytecode en busca de maquinaria de **honeypot (blacklist/trading-toggle), mint, pause, tax,
  limits**; resuelve **proxies mínimos EIP-1167** (todos los tokens de Argus son clones → se escanea
  la **implementación**) y detecta proxies **upgradeables** (EIP-1967) + **owner activo**. Se integra
  en la ficha de token: `/check`, `GET /token` y la **Mini App** (compra). Honestidad: es
  **heurística** (no prueba de venta); la simulación compra/venta queda para después. Verificado en
  token real (BCAT): `level=medium`, `owner_active`, `minimal_proxy`. Tests **296 passed** (1 fallo
  ambiental local). `ARC_AI_FEATURES.md` actualizado.
- **2026-09-27 (simulación de transferencia)** — Complemento anti-honeypot: `eth_call` de un
  `transfer` **desde un holder con saldo** (creator + compradores recientes de `legs`) hacia el
  PoolManager; un **revert** → `transfer_reverts` (nivel **high**, `honeypot_hint`). Si **ningún**
  holder tiene saldo, `transfer_sim=null` (honesto: no se finge). Cacheado 1 h; acotado a 3 holders.
  Verificado: la simulación ejecuta; en BCAT devolvió `null` (holders sin saldo). Tests **299 passed**.
- **2026-09-27 (punto 2 — relayer)** — Generado el wallet de **relayer** en el VPS:
  **`0x5ce3F78E69Fe6bdBF5745cb4E18B4B9C2F37A98f`** (clave en `/root/arc-intel/relayer.env`, modo 600,
  **no mostrada**). Activación = añadir `EnvironmentFile=/root/arc-intel/relayer.env` a los servicios
  `arc-intel-*` **tras fondear** la dirección con **USDC testnet** (gas; `https://faucet.circle.com`).
  **Incidencia de seguridad:** el primer `cast wallet new` **imprimió la clave privada** en el log; el
  wallet estaba **sin fondos** (sin pérdida) → se **descartó** y se regeneró **sin imprimir**. **Nunca
  fondear** la dirección descartada `0xe31A75…507D`.
- **2026-09-27 (relayer ACTIVADO + allowlist)** — Relayer `0x5ce3F7…A98f` **fondeado** (60 USDC de
  gas en Arc testnet); añadido `EnvironmentFile=-/root/arc-intel/relayer.env` a los dos servicios;
  `ARC_INTEL_RELAYER_KEY` **cargado**. **Bloqueo detectado:** el executor tiene **allowlist por pool**
  (fail-closed) y el pool de prueba **no** está permitido → `execute` revertiría (`PoolNotAllowed`).
  Acción de owner (Safe `0xe911D6F5…86b7`): `setAllowedPool(poolId, true)` para cada pool que se vaya
  a operar. Sin allowlist, la ejecución real no funciona aunque el relayer tenga gas.
- **2026-09-27 (dominio ACTIVO)** — Registro **A `app` → 2.29.24.106** creado en **Porkbun**;
  `systemctl reload caddy` forzó la emisión → **cert Let's Encrypt** (`CN=app.basepump.dev`).
  Verificado: `/health` 200, Mini App servida, `api.basepump.dev` intacto. URL de la TMA:
  `https://app.basepump.dev/` (pendiente: añadir a Reown allowed domains y al menú del bot).

---

## 11. Velocidad de ejecución — Opción 2 (órdenes pre-firmadas)
> **⚠️ Superado en parte (2026-09-27):** el **Modo Maestro (custodial)** pasa a ser el camino de
> velocidad por defecto (el bot firma con la wallet del usuario). Esta sección se mantiene como **diseño
> de respaldo no-custodial** (por si se ofrece también ese modo).

**Decisión (histórica):** para ejecución rápida **no-custodial** se elige la **Opción 2 (órdenes pre-firmadas)**.
La **Opción 3 (session keys / ERC-4337)** queda **diferida** (smart account + módulo de sesión +
auditoría + hot key acotada; no es lo primero).

- Usa el **contrato ya existente** (`ArcIntelExecutor`): el usuario firma **una vez por orden**; el
  **keeper la ejecuta sola** cuando se cumple la condición.
- Productos: **🛡️ Auto-protección (salir en dev-sell)** y **📉 órdenes límite / stop**.
- **No-custodial puro:** la orden firmada solo puede vender TU token, con TU `minOut`, a TU dirección,
  antes del `deadline`, una sola vez. No hay llave que robar.
- **Ya existe:** contrato, detección de señales 24/7, tracking de posiciones + reconciliación,
  keeper/loop, bot.
- **Falta construir:** (1) **UX de firma** (deep link / WalletConnect) — lo principal; (2) almacén de
  órdenes firmadas; (3) motor de disparo en el loop; (4) precio para `minOut`/triggers; (5) cancelación
  (`cancelOrder` / `deadline`); (6) mainnet + auditoría; (7) infra de velocidad (RPC dedicado + keeper
  caliente).
- **Velocidad real = infra** (RPC / keeper / inclusión), no la firma.

### 4 decisiones — ✅ CONFIRMADAS (2026-09-28)
1. **Duración:** **30 días** por defecto (configurable; expira sola).
2. **`minOut` en standby:** **configurable**; por defecto **−30%** del precio al firmar, con opción
   **"salir a cualquier precio"** (suelo muy bajo) para rug.
3. **Cancelación:** **botón cancelar on-chain** (`cancelOrder` consume el nonce) **+ expiración**.
4. **Alcance:** **solo venta/proteger** el día 1; **compras límite** en fase 2.

**Próximo paso (mañana):** empezar por la **UX de firma**, que desbloquea el resto.

---

## 12. Ideas diferenciales (atraer público — que la competencia no tiene)
> Los bots grandes (Maestro, Banana Gun, Trojan, Photon) son **custodiales, genéricos y "casino"**.
> Nuestro foso: **capa de SEGURIDAD para memecoins de Arc, honesta y con custodia declarada (Modo Maestro)**.

### A. Seguridad (ventaja #1 — nadie la da)
1. **🛡️ Kill-switch** (auto-salida en dev-sell) — producto estrella (Modo Maestro; Opción 2 como respaldo).
2. **Reputación on-chain del creador** — si el dev ya rugueó, avisar **antes** de comprar (historial de carteras).
3. **Detección de bundle/insider** — snipers/bundles que entran en el mismo bloque al lanzar (ya tenemos `coordinated_clusters`).
4. **Badge de LP bloqueada y verificable** — sello de confianza (Argus ya la bloquea por construcción).
5. **Chequeo anti-impostor** — tokens que imitan símbolo/nombre de otro (phishing).
6. **"Rug risk score"** por token (dev%, snipers, liquidez, actividad), calculado on-chain y **verificable**.

### B. Arc-nativo (nadie sirve Arc de verdad)
7. **Primer bot hecho PARA Arc** (USDC gas, bloques sub-segundo).
8. **Terminal (TMA)** con precio y **PnL en vivo por websocket** — UX estilo GMGN.
9. **Bridge** (Base/Solana/Arbitrum → Arc USDC) + aviso al llegar.
10. **Whale watch de Arc** — compras/ventas grandes en tiempo real.

### C. Honestidad (imposible de copiar sin cambiar su modelo)
11. **Track record público y verificable** (con las **dos caras**).
12. **Modo práctica [PAPER]** (ya lo tenemos): "aprende antes de arriesgar".
13. **PnL honesto** de tu wallet (solo lectura), sin ocultar pérdidas.

### D. Economía / growth (ya diseñado)
14. **Concurso por volumen** trader + afiliado (50/50, cada 12 h).
15. **Referidos de por vida** con números que cierran.
16. **Insignias/rangos** por uso (retención).

### E. Descubrimiento (arriba del embudo)
17. **Feed de lanzamientos de Arc** (Argus) con filtro de seguridad.
18. **Ranking semanal de launchpads** por seguridad/actividad (ya hicimos clustering de hooks).
19. **"Antes de comprar"**: pegas la CA y te dice **riesgo** (no solo el precio).

### Prioridad recomendada
1. **Kill-switch** (auto-salida en dev-sell) — diferenciador nº1.
2. **Reputación on-chain del creador** (usa datos que ya indexamos; rápido y único).
3. **Badge LP bloqueada + rug risk score**.
4. **Terminal TMA con PnL en vivo (websocket)**.

**Foso real:** A (seguridad) + B (Arc-nativo) no los puede copiar fácil un custodial genérico.

---

## 13. Infra y Mini App (empezar mañana)
- **Mini App (TMA):** Telegram **exige HTTPS** para Mini Apps → hay que **comprar un dominio** (p. ej. `.com`/`.io`)
  + certificado. Empezamos mañana.
- **VPS actual (medido 2026-09-27):** **2 vCPU · 4 GB RAM** (≈1.3 GB libres) · **disco 96% (solo 1.8 GB libres)**.
  Corre: `arcai-pg`, contenedores BasePump (api/orders-keeper/telegram/keeper/autoheal), y `pm2`
  (arc-alerts, arc-keeper mainnet+testnet, arc-metrics, 5× mev, logrotate).
  - **Para la Mini App (frontend estático + API ligera): el VPS actual VALE**, pero **hay que liberar disco
    primero** (96% es riesgo real: BD/postgres + datos del indexer).
  - **Para trading real / velocidad:** mejor un **VPS aparte** (aislar API/keeper del indexer, para que un
    ciclo pesado no afecte al camino de trading) + **RPC dedicado** (la latencia la da el RPC, no el tamaño).
    Considerar **8 GB RAM + más disco**.
  - **Acción inmediata:** vigilar/limpiar disco (logs, cache, dumps) o ampliarlo **antes** de la Mini App.
- **2026-09-27 (madrugada)** — Se elige la **Opción 2 (órdenes pre-firmadas)** para velocidad; Opción 3
  (session keys) diferida. 4 decisiones pendientes (duración, `minOut` standby, cancelación, alcance).
- **2026-09-27 (tarde)** — Bot: `/check` con **Buy** (importes $10/$20/$50/$100 u "Other"), **PnL** y
  **venta 25/50/75/100%** con 1 clic ([PAPER], botón 🔄 para refrescar precio). Añadida sección
  **12 · Ideas diferenciales** (seguridad on-chain, Arc-nativo, honestidad) y **recomendaciones** para
  las 4 decisiones de la Opción 2.
- **2026-09-27 (alerts: por qué no llegaban)** — El bot **sí** generaba señales
  (`large_sell`/`volume_spike`/`volume_collapse`, `lag:0`) pero los suscriptores con **kinds antiguos**
  (`dev_sell,compound,volume_collapse`) **no recibían** los tipos nuevos
  (`volume_spike`/`large_sell`/`liquidity_removal`). **Fix**: kinds vacío = **todos** los tipos
  actuales (`_enabled_kinds` default). Verificado con `dispatch` real → **2 entregadas**. **Al comprar**
  (wallet del bot) → `record_fill` → `add_auto_sub` → el token queda **auto-vigilado** y el usuario
  recibe sus anomalías.
- **2026-09-27 (alertas no despachaban: causa raíz)** — El bucle quedaba **bloqueado en la ingesta
  (RPC 429)** dentro del ciclo → nunca llegaba a `dispatch`. **Fix de infra:** ingesta **desacoplada**
  en un **timer systemd cada 60 s** (`arc-intel-ingest.timer` → `indexer.ingest`) y el bot con
  **`--no-ingest --interval 60`** (ciclos rápidos). Además, `dispatch` **blinda el envío** (un chat
  inválido ya no rompe el bucle) y se eliminaron suscriptores de prueba. Verificado: `dispatched: 20`.
  Se activó el **feed público** de descubrimiento (volume spike / price surge / whale buy) a todos.
- **2026-09-27 (referidos: 30%)** — Investigación de la competencia y decisión: **referidos = 30% de por
  vida** sobre la comisión neta. Mercado medido: **Trojan ≤35%** (multinivel 5, L1 15%), **BullX 30%**
  (flat), **Maestro 25%** (sticky), **Banana Gun** revenue-share ligado a `$BANANA`, **GMGN** tiers por
  volumen, **Photon** 0.9% (descuento, no paga), **Axiom** multinivel 3. Reparto recomputado a
  **5% trader + 5% afiliado + 30% referidos + 30% infra + 30% equipo = 100%** (`ARC_AI_ECONOMIC_MODEL.md`
  y `.csv` actualizados). Regla de pagos: premios (10%) + referidos (30%) = 40%; rebajas VIP salen del
  equipo. Pendiente de decidir: multinivel (L2) más adelante.
- **2026-09-27 (CUSTODIA adoptada)** — Se **alinea el registro con el código**: existe
  `execution/custody.py` (**Modo Maestro/Banana**, wallet custodial cifrada) y el usuario **confirma
  custodial como modo**. Se actualizan P2 (no-custodial → **CUSTODIAL**), P3/P5, **X1** (custodia ya
  **no** se descarta) y **X5** (bridge a wallet del bot ya no aplica); **L2/L4** pasan a **PENDIENTE
  REVISIÓN** (KYC/AML + responsabilidad sobre fondos de terceros, revisar **antes de mainnet**). La
  custodia **sustituye a las session keys / firma por orden** (Opción 2/3) como camino de **velocidad**:
  el bot firma con la wallet del usuario (clave cifrada con `ARC_INTEL_SESSION_ENC_KEY`, retiro libre).
  Riesgo asumido y declarado: quien tenga la clave controla los fondos. Auditoría de mainnet **obligatoria**.
- **2026-09-27 (referidos: implementación)** — Programa de referidos **funcional**:
  `monetization/referrals.py` (puro: `make_code`, `parse_ref_param`, `referral_link`, comisión 1%→30%);
  `bot/store.py` (tablas `referral_codes`/`referral_bindings`/`referral_credits`; `ensure_referral_code`,
  `bind_referral` (sin auto-referido, primer vínculo gana), `accrue_referral` **idempotente por `fill_id`**
  — los fills `[PAPER]` **no** pagan, y se engancha en `record_fill`); captura de `/start ref_CODE` en el
  poller (`capture_referral`, incluso antes de la allowlist) + `_ensure_bot_username` (getMe→state);
  comando **`/referral`** (código, enlace, invitados, acumulado/pendiente) + botón en el menú + alta en
  `setMyCommands` (EN/ES/ZH); endpoint **`GET /referral`** (auth) y tarjeta en **Cartera** de la Mini App.
  Tests: **63** en los módulos tocados (13 + 1 de pantalla + 1 de integración nuevos); suite total
  **348 passed** (1 fallo **ambiental** local de la Mini App). Nota: las comisiones quedan **acumuladas**
  (`status='accrued'`); el **pago en USDC** se hará cuando el cobro del fee esté activo en mainnet.
- **2026-09-27 (referidos: estadísticas)** — Botón **"📊 Estadísticas"** en la pantalla `/referral`
  (callback `ref:stats` / volver `ref:home`) con **desglose por usuario referido** (ops · fee · comisión),
  vía `store.referral_breakdown`; mismo desglose en la **tarjeta de la Mini App** (`GET /referral`
  devuelve `breakdown`). Además se **corrige el copy de `/wallet`** (decía "non-custodial"): ahora
  describe la **cartera enlazada solo-lectura** y remite al **wallet del bot (custodia)** en la Mini App.
  Suite total **351 passed** (1 fallo ambiental local).
- **2026-09-27 (copytrading v1)** — **Copytrading funcional** con la wallet **custodial**. Núcleo puro
  `execution/copy.py` (`CopyConfig`, `plan_buy`, `decide`: copia **compras** por
  `min(notional, max_por_op, presupuesto_restante)`, ignora polvo <$5, y **vende** cerrando el 100% de
  la posición). Motor `execution/copy_keeper.py` (`run_copy_engine`): por cada seguidor lee las
  operaciones **nuevas** del líder (`indexer.pg_storage.recent_wallet_legs` sobre `legs`) y las replica
  best-effort con la wallet del bot; **self-advancing** de `last_block`, **idempotente** por bloque,
  con **dry-run**   (`ARC_INTEL_COPY_DRY_RUN=1`) y callback de aviso. Store `bot/store.py`: tabla
  `copy_subs` + `add/get/list/remove/set_enabled/bump_spent/set_last_block`. **UI Mini App**: pestaña
  **Copy** (seguir líder, `max/op`, presupuesto, gastado/restante, pausar/parar) + endpoints
  **`GET /copy`**, **`POST /copy`**, **`POST /copy/off`**, **`POST /copy/toggle`** (`copy_view` puro).
  Tests **+1** de `copy_view` + auth. Commit `bd7bd04`.
- **2026-09-27 (concurso + banner del pozo v1)** — Núcleo puro `monetization/contest.py`
  (`round_window` 2 rondas/día UTC, `pozo` = 10% de las comisiones de la ronda, `split_prize` 50/50
  trader/afiliado, `leaderboard`, `standings`, `rank_of`, `mask_user`). Store:
  `volume_by_user_since` y `referred_volume_by_user_since` (**solo fills reales**, `[PAPER]` excluido;
  se añadió `ts` a los `record_fill` de custodia y copytrading). Endpoint **`GET /contest`** (auth):
  ronda actual, pozo, premio, total y **rankings** (trader/afiliado, usuarios enmascarados) + tu
  puesto. **Banner del pozo** en la Mini App (arriba, siempre visible) con **contador** y ranking
  desplegable (refresco 30 s). Tests **+7** (`tests/test_contest.py`) + auth. Suite **371 passed**
  (1 fallo ambiental local). **Pendiente**: publicación automática del ganador (canal oficial) 1 h
  tras el cierre y liquidación; el pozo es informativo hasta que el cobro del fee esté activo.
- **2026-09-27 (pozo también en Telegram)** — El banner del pozo llega al **bot**: comando
  **`/pozo`** (`contest_screen`: pozo, volumen de la ronda, rankings trader/afiliado enmascarados y tu
  puesto) y **botón dinámico "🏆 Pozo $X"** en el menú de `/start` (que abre `/pozo`), además de una
  **línea de pozo + contador** encabezando el mensaje de bienvenida. Registrado EN/ES/ZH. Suite
  **372 passed** (1 fallo ambiental local).
- **2026-09-27 (publicación del ganador al canal)** — **Settlement automático**: `monetization/contest.py`
  añade `previous_round`, `winner` y `settle` (ganador + premio por categoría). `bot/contest_publish.py`
  (`publish_round`) calcula la ronda cerrada, y **1 h después** del cierre publica en el **canal oficial**
  (`ARC_INTEL_CHANNEL`) el pozo y los campeones **trader** y **afiliado** con su premio; idempotente por
  ronda (marca en `contest_rounds`, histórico en `contest_winners`), reintenta si el envío falla. Se
  **captura el `@username`** del remitente (`name:{chat}`) para anunciar el alias (si no, se enmascara).
  Enganchado al loop (tras `dispatch`). Store: `volume_by_user_between`, `referred_volume_between`,
  `contest_round_published`/`mark_contest_round`/`record_contest_winner`/`list_contest_winners`. Tests
  **+4**. Suite **375 passed** (1 fallo ambiental local). **Nota:** el canal debe configurarse
  (`ARC_INTEL_CHANNEL=-100…`); hoy **dormido** hasta entonces.
- **2026-09-27 (copytrade v2 — multi-wallet + filtros, estilo Maestro/Banana)** — Rediseño según la
  referencia visual: **varias wallets** seguidas por usuario (`copy_wallets`) + **filtros globales**
  (`copy_settings`): `min_buy_usdc` (solo compras ≥ $X; 0 = todas), `max_open` (máx. posiciones
  abiertas; 0 = ilimitado), `sizing` (**flat** o **proportional**), `mirror_sells`, y **protección por
  defecto** (`tp_pct`/`sl_pct`/`trailing_pct`/`dump_guard`) **adjunta a cada fill copiado** (usa
  `exit_plans` + Auto-Protect). Núcleo puro `execution/copy.py` (`CopySettings`, `plan_size`, `decide`
  con `below_min`/`max_open`/`mirror_off`/`no_position`); motor `execution/copy_keeper.py` itera
  **todas** las wallets con su override `flat_usdc`. **Bot**: pantalla **Copy-trade** con `➕ Añadir
  wallet` (pegar dirección) y `🎛️ Filtros` (min buy / max open / tamaño flat-proporcional / mirror
  sells / protección) + lista de wallets con pausar/borrar; entradas por estado `awaiting_copy`. **Mini
  App**: pestaña **Copy** con wallets (pausar/borrar), formulario de añadir y panel de filtros; cabecera
  **`Cache-Control: no-store`** para evitar que Telegram sirva una versión antigua. Endpoints: `GET
  /copy`, `POST /copy/wallet`, `/copy/wallet/remove`, `/copy/wallet/toggle`, `/copy/settings`. Tests
  reescritos/adjustados. Suite **377 passed** (1 fallo ambiental local). Sigue **dry-run** hasta mainnet.
  `copy_subs` + `add/get/list/remove/set_enabled/bump_spent/set_last_block`. Bot: comandos
  **`/copytrade <addr> [max_por_op] [presupuesto]`** y **`/copyoff`**; botón del menú **Copytrade**
  ahora **funcional** (`cmd:/copytrade`); comando registrado EN/ES/ZH. Thread propio en el loop
  (`telegram.run_incremental`, cada 30 s) → no frena alertas. Tests **+10** (`tests/test_copy.py`) +
  1 de comando. Suite **361 passed** (1 fallo ambiental local). **Dormido** sin wallet custodial /
  `ARC_INTEL_SESSION_ENC_KEY` / pool permitido; el **pago real** espera a mainnet.
