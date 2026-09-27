# Arc AI — Modelo económico simple (entra vs sale)

Hoja editable: [`arc_ai_economic_model.csv`](arc_ai_economic_model.csv). Abre en Excel/Google Sheets.
Cambia **solo los supuestos** (tarifa, coste fijo, reparto) y se recalculan los 3 escenarios solos.

> **Si al abrir el .csv te sale todo en una columna (Excel en español):** usa *Datos → Desde texto/CSV*
> y elige **coma** como separador, o ábrelo en Google Sheets (Datos → Importar).

## Supuestos (editables)
| Supuesto | Valor | Nota |
|---|---:|---|
| Tarifa por operación | **1.0%** | del volumen operado |
| Coste fijo infra mensual | **300 USD** | RPC + servidores + monitoreo |
| Premio **trader** (mayor volumen propio) | 5% | concurso **cada 12 h** |
| Premio **afiliado** (mayor volumen de referidos) | 5% | concurso **cada 12 h** |
| Referidos (comisión de por vida) | 30% | sobre la comisión neta del referido (paridad **BullX**) |
| Operaciones / infra | 30% | |
| Equipo / beneficio | 30% | |
| **Total** | **100%** | nunca más del 100% |

> El premio (10%) se reparte **50/50** entre traders y afiliados, **ambos diarios**. No sube el gasto:
> solo se divide. Es **tunable**.

## Los 3 escenarios

### Vista mensual (entra vs sale)
| Concepto | BAJO ($10k/día) | MEDIO ($100k/día) | ALTO ($1M/día) |
|---|---:|---:|---:|
| Volumen mes | $300,000 | $3,000,000 | $30,000,000 |
| **ENTRA — comisión (1%)** | **$3,000** | **$30,000** | **$300,000** |
| SALE — Premio trader (5%) | $150 | $1,500 | $15,000 |
| SALE — Premio afiliado (5%) | $150 | $1,500 | $15,000 |
| SALE — Referidos (30%) | $900 | $9,000 | $90,000 |
| SALE — Operaciones/infra (30%) | $900 | $9,000 | $90,000 |
| SALE — Equipo/beneficio (30%) | $900 | $9,000 | $90,000 |
| Coste fijo infra | $300 | $300 | $300 |
| Infra asignada vs coste fijo | **+$600** | **+$8,700** | **+$89,700** |
| **Beneficio neto (tras cubrir infra)** | **$1,200** | **$12,000** | **$120,000** |
| Comprobación entra − sale | $0 | $0 | $0 |

### Vista diaria (más intuitiva)
| Concepto | BAJO | MEDIO | ALTO |
|---|---:|---:|---:|
| Comisión/día | $100 | $1,000 | $10,000 |
| Premio **trader**/día | $5 | $50 | $500 |
| Premio **afiliado**/día | $5 | $50 | $500 |
| Referidos/día | $30 | $300 | $3,000 |
| Infra/día | $30 | $300 | $3,000 |
| Equipo/día | $30 | $300 | $3,000 |

## Los dos concursos (mérito, no azar) — ambos diarios
**No es lotería.** Gana quien más volumen mueve en la ventana del día. Dos rankings:

1. **Trader** — volumen **propio**.
2. **Afiliado** — volumen **de sus referidos** (sin contar el suyo).

Un influencer puede **ganar por partida doble**: su **comisión de referido (30% de por vida)** **+** el
**premio del ranking de afiliados** (diario). Trae gente **y** compite.

### Anti-abuso (reglas mínimas)
1. **Rankings separados** → nada de doble cobro (el propio volumen no cuenta en el de afiliado).
2. **Volumen neto**, sin round-trips (compra-venta del mismo token en segundos).
3. **Excluir auto-operaciones** y tokens propios del participante.
4. **Referidos válidos**: cuentas distintas, con antigüedad mínima, sin patrón de granja.
5. **Defensa económica:** lavar volumen paga 1% de fee, pero el pozo es solo el 10% de las comisiones →
   inflar volumen **sale a pérdida**.
6. Ranking **con los datos del bot** (on-chain), público y auditable.

## Calendario del concurso (2 rondas por día)
- **Ronda 1:** 00:00 → 12:00 (UTC) · ganadores y cantidades publicados a las **13:00**.
- **Ronda 2:** 12:00 → 00:00 (UTC) · publicados a las **01:00**.
- El "**1 hora después**" es la **publicación/settlement**; la ronda siguiente ya está en marcha
  (así el horario no se desalinea).
- **Confirmado:** zona horaria **UTC** y **publicación 1 h después** de cada cierre; rondas alineadas
  (cierres a las 00:00 y 12:00).

### Regla de oro del pozo por ronda
Cada ronda reparte **el 10% de las comisiones de ESA ronda** (5% trader + 5% afiliado).
Con 2 rondas al día, el total diario sigue siendo exactamente el **10%** → **no se rompe el presupuesto**.

> ⚠️ Si en vez de esto pagas "5% en cada ronda" (2×10% = 20% por categoría al día) **te pasas del
> presupuesto**. Por eso el pozo se calcula sobre las comisiones de la ronda que se cierra.

### Publicación (FOMO)
Al cerrar cada ronda se publica en el **canal oficial + bot**: alias del ganador **y cuánto ganó**, en
las dos categorías (trader y afiliado).

## Punto de equilibrio
Con infra al 30%, hace falta **~$100,000/mes de volumen (~$3,300/día)** solo para cubrir 300 USD/mes.
Por debajo, la infra se paga primero y el beneficio es lo último.

## Reglas que NO se pueden romper
1. **Pagos < ingresos, siempre.** Premios (10%) + referidos (hasta 30%) = 40% de la comisión; las
   rebajas VIP **salen del equipo**, no se suman. Nunca más del 100%.
2. **Referidos sobre la comisión neta**, nunca sobre el volumen.
3. **Rebajas VIP salen del beneficio**; suelo ~0.65% neto por operación.
4. **Infra primero, beneficio después.**
5. **Los premios son un gasto fijo topado** (10%), nunca "todo lo que sobre".

## Qué NO incluye (a añadir más adelante)
- Impuestos y obligaciones legales (el concurso por volumen baja el riesgo, pero conviene revisarlo).
- **Divulgación publicitaria** de KOLs que cobran (marcar contenido patrocinado).
- Costes variables (soporte, marketing extra, pasarelas).

> Modelo ilustrativo para decidir, no una proyección. Los números reales dependen del volumen.
