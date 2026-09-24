import type { Iso8601, UnixMs } from "./branded.ts";
import type { TokenAmount, TokenRef } from "./money.ts";

export type PaperTradeStatus = "open" | "closed" | "cancelled";

export interface PaperTrade {
  readonly id: string;
  readonly tokenIn: TokenRef;
  readonly tokenOut: TokenRef;
  readonly amountIn: TokenAmount;
  readonly entryPrice: number;
  readonly exitPrice: number | null;
  readonly feesUsd: number;
  readonly slippageBps: number;
  readonly status: PaperTradeStatus;
  readonly openedAt: Iso8601;
  readonly closedAt: Iso8601 | null;
}

export interface PaperPortfolio {
  readonly cashUsd: number;
  readonly positions: readonly PaperTrade[];
  readonly realizedPnlUsd: number;
  readonly unrealizedPnlUsd: number;
  readonly updatedAt: UnixMs;
}
