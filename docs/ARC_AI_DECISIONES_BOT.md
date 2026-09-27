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
