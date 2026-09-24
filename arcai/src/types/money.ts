import type { Address, ChainId } from "./branded.ts";

export interface TokenRef {
  readonly chainId: ChainId;
  readonly address: Address;
  readonly symbol: string;
  readonly decimals: number;
}

export interface TokenAmount {
  readonly token: TokenRef;
  readonly raw: bigint;
}

export interface UsdNotional {
  readonly usd: number;
}
