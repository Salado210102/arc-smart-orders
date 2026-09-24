import type { Address, Hex, Iso8601, TradeIntentId, UnixMs } from "./branded.ts";
import type { TokenRef } from "./money.ts";

export type IntentKind = "limit" | "dca" | "twap" | "swap";
export type IntentSide = "buy" | "sell";

export type IntentStatus =
  | "draft"
  | "simulated"
  | "awaiting-signature"
  | "signed"
  | "submitted"
  | "filled"
  | "rejected"
  | "expired"
  | "failed";

export interface TradeIntent {
  readonly id: TradeIntentId;
  readonly kind: IntentKind;
  readonly side: IntentSide;
  readonly owner: Address;
  readonly tokenIn: TokenRef;
  readonly tokenOut: TokenRef;
  readonly maxAmountIn: bigint;
  readonly minAmountOut: bigint;
  readonly deadline: UnixMs;
  readonly nonce: bigint;
  readonly venue: string;
  readonly paper: boolean;
  readonly createdAt: UnixMs;
}

export interface SignedIntent {
  readonly intent: TradeIntent;
  readonly signature: Hex;
  readonly signer: Address;
  readonly signedAt: UnixMs;
}

export type AuthorizationScope = "single-use";

export interface Authorization {
  readonly intentId: TradeIntentId;
  readonly authorizedBy: Address;
  readonly scope: AuthorizationScope;
  readonly authorizedAt: Iso8601;
}
