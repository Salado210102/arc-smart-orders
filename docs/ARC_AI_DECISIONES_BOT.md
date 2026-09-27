# Arc AI — Registro de decisiones (bot / terminal)

> **Documento vivo.** Aquí se apunta TODO lo que vamos decidiendo. **Nada se implementa** hasta que
> hagamos la **revisión final** de este documento. Cada punto lleva estado:
> **CONFIRMADO** (acordado) · **ABIERTO** (por decidir) · **PENDIENTE REVISIÓN** (para el repaso final).
>
> Última actualización: **2026-09-26**

---

## 0. Contexto
- Ya existe y está en producción el **bot de alertas** de arc-intel (avisos de peligro, no-custodial, beta).
- Ya existe el **executor no-custodial** probado end-to-end en testnet, listo para auditoría.
- Este registro cubre la **nueva dirección** (terminal/sniper estilo GMGN, red Arc) y lo que decidamos.

---

## 1. Producto y enfoque
| # | Decisión | Estado |
|---|---|---|
| P1 | Construir una **Telegram Mini App (TMA)** estilo GMGN/DexScreener, no solo comandos de texto. | CONFIRMADO |
| P2 | **No custodial**: el usuario firma con **su** wallet; el bot **nunca** guarda claves ni fondos. | CONFIRMADO |
| P3 | Reutilizar el **executor** ya probado (v4, no-custodial) como capa de ejecución. | CONFIRMADO |
| P4 | El **detector de rug pulls** (ya construido) es el gancho de seguridad del producto. | CONFIRMADO |
| P5 | **Bridge no-custodial** (el usuario firma su puente), no una billetera-depósito del bot. | CONFIRMADO |
| P6 | Banner en vivo del **pozo del concurso** (contador + FOMO) dentro de la TMA. | CONFIRMADO |

## 2. Modelo de negocio
| # | Decisión | Estado |
|---|---|---|
| N1 | Tarifa **1%** por operación. | CONFIRMADO |
| N2 | Reparto de la comisión: **5% premio trader + 5% premio afiliado + 20% referidos + 30% infra + 40% equipo = 100%**. | CONFIRMADO |
| N3 | Coste fijo de infra de referencia: **300 USD/mes** (RPC + servidores + monitoreo). | CONFIRMADO |
| N4 | **Break-even:** ~**100,000 USD/mes** de volumen (~3,300 USD/día) solo para cubrir infra. | CONFIRMADO |
| N5 | Regla dura: **pagos < ingresos** (premios + referidos + rebajas **≤ 40%** de la comisión). | CONFIRMADO |
| N6 | **Infra primero**, beneficio del equipo **después**; premios = gasto **topado** (10%), nunca "lo que sobre". | CONFIRMADO |
| N7 | Descuento de bienvenida temporal por referido: **1% → 0.9%**. | ABIERTO (definir duración) |
| N8 | Rebaja VIP (para KOLs): hasta ~35%, **sale del beneficio**, nunca se suma; suelo ~0.65% neto. | ABIERTO (definir niveles) |
| N9 | Referidos: **20% de por vida sobre la comisión NETA** del referido (nunca sobre el volumen bruto). | CONFIRMADO |

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
| X1 | Bot que **genere/guarde billeteras** (custodia). | Riesgo de seguridad + legal; contradice la marca. |
| X2 | **Lotería de azar** como motor de retención. | Riesgo regulatorio (juego). Se sustituye por concurso por volumen. |
| X3 | Repartos que suman **>100%** o rebajas que se suman al reparto. | Rompía la economía. |
| X4 | Aleatoriedad por **hash del bloque**. | Manipulable por quien produce el bloque. |
| X5 | Bridge que deje fondos **en una billetera del bot**. | Custodia encubierta. |

## 6. UX / TMA (a detallar)
| # | Punto | Estado |
|---|---|---|
| U1 | Terminal con gráficos, slippage deslizable, botones de compra rápida **con firma del usuario**. | ABIERTO (alcance) |
| U2 | Pestaña **Bridge** (Base/Solana/Arbitrum → Arc USDC) **no-custodial**. | ABIERTO |
| U3 | **PnL / historial** visual (verde/rojo) + estado "RUGGED" en trades afectados. | ABIERTO |
| U4 | Firma biométrica (FaceID/TouchID) **solo sobre wallet del usuario** (no del bot). | ABIERTO |
| U5 | Menú inline estilo Maestro (8 filas) + idiomas EN/ES/中文 + pegar-CA + positions. | HECHO (bot actual) |
| U6 | **Logos de token**: fuente = Argus `TokenCreated.image_uri` (IPFS→gateway), fallback DexScreener. | HECHO (en alertas) |
| U7 | **Connect wallet** watch-only (no-custodial) + panel; comando `/connect`. | HECHO |

## 7. Legal (a revisar antes de implementar)
| # | Punto | Estado |
|---|---|---|
| L1 | Concurso por volumen: confirmar encaje legal (mérito, no azar). | PENDIENTE REVISIÓN |
| L2 | Custodia: descartada (no aplica). | CONFIRMADO (fuera) |
| L3 | **Divulgación publicitaria** de KOLs (marcar patrocinado). | PENDIENTE REVISIÓN |
| L4 | KYC/AML según jurisdicción (si se maneja dinero de terceros… no aplica al ser no-custodial, revisar igual). | PENDIENTE REVISIÓN |

## 8. Pendiente de decidir (para la revisión final)
- Duración del descuento de bienvenida (N7) y niveles VIP (N8).
- Alcance exacto de la TMA (qué pestañas primero).
- Método de firma/wallet (WalletConnect vs deep-link vs embebida-no-custodial).
- Venues de swap en Arc (v4 vía executor; Argus; otros).
- Qué parte del **bot de alertas actual** se reutiliza tal cual vs se integra en la TMA.
- Moneda/representación del pozo y pagos (USDC, on-chain).
- Cuándo arranca el primer concurso y cómo se comunican las reglas.
- **URL de documentación** (botón Help): hoy apunta al repo GitHub; sustituir por **web/Notion propia**
  cuando exista (configurable con `ARC_INTEL_DOCS_URL`, sin tocar código).
- **Botones "pronto"**: Signals · Copytrade · Bridge · Premium (y la **TMA / terminal**).
- **Trading real**: desplegar el executor en **mainnet** + **firma con la wallet del usuario** +
  **auditoría**. (Hoy: solo testnet, y conectar wallet es solo informativo.)

## 9. Artefactos y estado
| Artefacto | Estado |
|---|---|
| Modelo económico | `docs/ARC_AI_ECONOMIC_MODEL.md` + `.csv` (sin commitear) |
| Bot de alertas (arc-intel) | En producción (beta) |
| Executor no-custodial | Probado en testnet; paquete de auditoría congelado (tag `arc-intel-executor-v1`) |
| Registro de decisiones | este documento (sin commitear) |

---

## 10. Registro cronológico (append)
- **2026-09-26** — Se define la nueva dirección (terminal/TMA no-custodial, red Arc). Se descarta custodia,
  lotería de azar y economía rota. Concurso por volumen (trader/afiliado), 50/50, cada 12 h, UTC.
  Reparto 5/5/20/30/40. Publicación 1 h después del cierre. Documento de modelo económico creado.
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

---

## 11. Velocidad de ejecución — Opción 2 (órdenes pre-firmadas)
**Decisión:** para ejecución rápida **no-custodial** se elige la **Opción 2 (órdenes pre-firmadas)**.
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

### 4 decisiones (recomendación para cerrar mañana)
1. **Duración:** **30 días** por defecto (configurable; expira sola). Es una red de seguridad → interesa
   que dure y no re-firmar a diario.
2. **`minOut` en standby:** **configurable**; por defecto **−30%** del precio al firmar, con opción
   **"salir a cualquier precio"** (suelo muy bajo) para rug. Un suelo muy ajustado no entra en un desplome.
3. **Cancelación:** **botón cancelar on-chain** (`cancelOrder` consume el nonce → la orden **nunca** puede
   ejecutarse aunque hackeen el keeper) **+ expiración**. Recomendado.
4. **Alcance:** **solo venta/proteger** el día 1; **compras límite** en fase 2.

**Próximo paso (mañana):** empezar por la **UX de firma**, que desbloquea el resto.

---

## 12. Ideas diferenciales (atraer público — que la competencia no tiene)
> Los bots grandes (Maestro, Banana Gun, Trojan, Photon) son **custodiales, genéricos y "casino"**.
> Nuestro foso: **capa de SEGURIDAD para memecoins de Arc, sin custodia y honesta**.

### A. Seguridad (ventaja #1 — nadie la da)
1. **🛡️ Kill-switch no-custodial** (auto-salida en dev-sell) — producto estrella (Opción 2).
2. **Reputación on-chain del creador** — si el dev ya rugueó, avisar **antes** de comprar (historial de carteras).
3. **Detección de bundle/insider** — snipers/bundles que entran en el mismo bloque al lanzar (ya tenemos `coordinated_clusters`).
4. **Badge de LP bloqueada y verificable** — sello de confianza (Argus ya la bloquea por construcción).
5. **Chequeo anti-impostor** — tokens que imitan símbolo/nombre de otro (phishing).
6. **"Rug risk score"** por token (dev%, snipers, liquidez, actividad), calculado on-chain y **verificable**.

### B. Arc-nativo (nadie sirve Arc de verdad)
7. **Primer bot hecho PARA Arc** (USDC gas, bloques sub-segundo).
8. **Terminal (TMA)** con precio y **PnL en vivo por websocket** — UX estilo GMGN.
9. **Bridge no-custodial** (Base/Solana → Arc USDC) + aviso al llegar.
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
1. **Kill-switch no-custodial** (Opción 2) — diferenciador nº1.
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
