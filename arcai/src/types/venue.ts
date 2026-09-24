import type { Address, ChainId } from "./branded.ts";
import type { TokenRef } from "./money.ts";

export type VenueKind = "uniswap-v3" | "uniswap-v4" | "launchpad-dex";

export interface Quote {
  readonly venue: VenueKind;
  readonly tokenIn: TokenRef;
  readonly tokenOut: TokenRef;
  readonly amountIn: bigint;
  readonly amountOut: bigint;
  readonly priceImpactBps: number;
  readonly feeTierBps: number;
  readonly route: readonly Address[];
}

export interface RoutePlan {
  readonly chainId: ChainId;
  readonly venue: VenueKind;
  readonly quote: Quote;
  readonly minAmountOut: bigint;
  readonly deadline: bigint;
}
