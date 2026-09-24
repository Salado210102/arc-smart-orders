import type { ChainId, Iso8601, UnixMs } from "./branded.ts";

export type FeatureScope = "wallet" | "token" | "market";

export type FeatureValue = number | string | boolean | bigint | null;

export interface FeatureKey {
  readonly scope: FeatureScope;
  readonly name: string;
}

export interface FeatureRecord {
  readonly key: FeatureKey;
  readonly version: number;
  readonly subject: string;
  readonly chainId: ChainId;
  readonly value: FeatureValue;
  readonly asOf: UnixMs;
  readonly computedAt: Iso8601;
}
