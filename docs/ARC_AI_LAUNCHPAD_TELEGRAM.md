# Arc AI — Launchpad desde Telegram (IDEA / PENDIENTE)

> **Estado: idea registrada, NO implementada.** Apuntada el 2026-09-28 para no perderla.
> Depende de cerrar la auditoría (Bloques A/B/C) y de repriorización con el usuario.

## Objetivo
Un **launchpad** que permita **crear un token directamente desde Telegram** (Mini App) con **curva de
vinculación (bonding curve)** en **Arc**, y que, al lanzarse, se **publique AUTOMÁTICAMENTE** en un
**canal de lanzamientos dedicado** — **paralelo al canal de alertas** (NO el canal público de alertas;
uno nuevo) — con un **enlace directo a la Mini App para comprar ese token**.

Valor: elimina el copia-pega manual del CA en canales, y (según el usuario) **no existe hoy un launchpad
Telegram-native en Arc** → posible *wedge* / primicia.

## Alcance propuesto (borrador a reformular, NO copiar tal cual)
- **Bloque 1 (contrato):** `ArcLaunchpad.sol` — curva de vinculación, USDC como pago, Factory de tokens
  ERC-20, migración a DEX al alcanzar meta (ej. 5,000 USDC), evento
  `TokenLaunched(address token, string name, string symbol, address creator, uint256 timestamp)`.
- **Bloque 2 (backend):** listener del evento `TokenLaunched` → post formateado al **canal dedicado**
  (`env TELEGRAM_CHANNEL_ID`) con botón a la Mini App.
- **Bloque 3 (frontend):** pestaña **Launchpad** en la Mini App: Nombre, Símbolo, Descripción, botón
  `createToken` (conexión de wallet) + mensaje de éxito.

## Correcciones obligatorias antes de implementar (revisión senior)
1. **USDC**: definir si la curva cobra **nativo (18 dec)** o **ERC-20 `0x3600…0000` (6 dec)**; la spec
   los mezcla (fuente clásica de bugs de escala).
2. **DEX = Uniswap v4** (PoolManager `0x8366a39CC670B4001A1121B8F6A443A643e40951`), **no v3**. La
   graduación inicializa pool v4 con **hook** y **bloquea la posición (NFT del PositionManager)** —
   NO "quemar LP tokens" (eso es v2/v3).
3. **Telegram**: en **canales** NO funcionan los botones `web_app`; usar botón **`url`** con deep link
   `https://t.me/<bot>/<app>?startapp=<payload>` (o `https://t.me/<bot>?startapp=<...>` si hay Mini App
   principal). La Mini App lee/valida `initData.start_param`. El `https://t.me` del borrador está
   incompleto.
4. **Metadata**: ERC-20 no tiene "descripción"; subir **imagen/descripción/socials a IPFS** y añadir
   **`metadataURI`** al evento (sin esto, el post sale sin logo/descripción).
5. **Listener idempotente**: dedup por **`txHash + logIndex`**, **cursor persistente** y **backfill** al
   reiniciar; asumir **RPC 429**.
6. **Seguridad del contrato**: **fee de creación** (anti-spam), math de la curva explícita
   (x·y=k con reservas virtuales vs lineal), **anti-snipe / max-tx**, **graduación atómica** en la misma
   tx que cruza el umbral, **reentrancy guard**, **pausa de emergencia**, y **auditoría**.
7. **Stack**: adaptar a nuestro stack real (**backend Python**, Mini App **JS vanilla**) — el borrador
   asume **Node.js + React/Next.js**; migrar o adaptar, no copiar.
8. **Anti-spam / marca**: aunque el canal es dedicado (no el público), un launchpad es superficie de
   rugs → **fee de creación**, **disclaimer "no avalado"** y, si se puede, **Safety Score por lanzamiento**
   en el post (alineado con la marca anti-rug).

## Decisiones abiertas (mañana)
- ¿Launchpad **propio** o **integrar/publicar sobre Argus** (ya indexamos su `TokenCreated`/hooks)?
- ¿Meta de graduación y modelo de curva? ¿fee de creación?
- ¿Cómo se filtran/curan los lanzamientos en el canal (safety score, revisión)?
- ¿La creación usa la **wallet custodial** (Modo Maestro) o flujo **no-custodial** (firma del usuario)?

## Relacionado en el repo (existente)
- `contracts/src/launchpad/*`, `docs/AGENT_LAUNCHPAD.md` (revisar solapamiento).
- `arc-intel/indexer/` ya indexa **Argus** (launchpad en Arc): `TokenCreated`, `CurveOpened`, hooks.
