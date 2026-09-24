# ARC AI (`arcai/`) — M0.1 foundation

Additive, type-only foundation for **ARC AI**, the AI-native trading + on-chain
intelligence platform for **Arc**. This milestone contains **types, interfaces and
read-only config constants only**. There is **no runtime logic**, no external calls,
no keys, no RPC, no database, no Telegram, and no transaction code.

Reference architecture: [`docs/ARC_AI_MASTER_ARCHITECTURE.md`](../docs/ARC_AI_MASTER_ARCHITECTURE.md) (Revision 02, authoritative).

## Scope of M0.1

- Add `arcai/` as a workspace in the monorepo.
- Define the domain model and the integration interfaces the later milestones implement.
- Pin verified Arc network identity (chain ids, RPC/WS, explorer, native decimals).
- Typecheck (`tsc --noEmit`) and structural tests (`node --test`) in CI.

Explicitly **out of scope**: indexer, feature store, quant engine, backtest, replay,
AI providers, Telegram bot, execution, venue adapters, paper trading, database, and
any secret handling. Those arrive in M0.2+ behind their own designs and approvals.

Token and contract registries (USDC/EURC/cirBTC, OrderExecutor, Permit2, Morpho,
Uniswap v3/v4 routers) are intentionally **not** part of M0.1. They belong to the
Data Engine (M0.2) and the execution/venue milestones.

## Non-negotiable invariants encoded in these types

1. **Non-custodial.** No type carries a private key. Signing stays client-side.
2. **`TradeIntent` is not a transaction**, and **`AIResponse` is not an `Authorization`.**
   These are distinct types; the structural tests assert they are not interchangeable.
3. **Provider-agnostic AI.** `AIProvider` is an interface; the LLM never computes
   PnL/score/risk and never signs.
4. **Typed tools only.** The LLM reaches data through `ToolDefinition` with strict
   input/output schemas — never raw SQL or arbitrary execution.
5. **Paper-first.** `TradeIntent.paper` defaults the product to paper trading; live
   execution is gated separately and is not present here.
6. **Arc-only MVP.** `ChainId` values are pinned to Arc mainnet/testnet; interfaces
   stay modular for future chains.

## Layout

```
arcai/
  src/
    types/        domain types (branded ids, chain, money, intent, ai, data,
                  feature, signal, risk, paper, venue)
    interfaces/   AIProvider, ToolDefinition/ToolRegistry, DataProvider,
                  VenueAdapter, FeatureStore, Clock
    config/       read-only Arc network identity (chain ids, rpc/ws, explorer, decimals)
    index.ts      barrel export
  test/           structural tests
```

## Usage

```
npm run typecheck --workspace @arc-smart-orders/arcai
npm run test --workspace @arc-smart-orders/arcai
```

Type-only imports must use `import type` (`verbatimModuleSyntax` is enabled), and
only erasable TypeScript syntax is allowed (`erasableSyntaxOnly`) so the sources can be
executed directly by Node's type stripping. No enums or namespaces.
