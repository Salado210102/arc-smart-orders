import type { ChainId, UnixMs } from "../types/branded.ts";
import type { FeatureKey, FeatureRecord } from "../types/feature.ts";

export interface AsOfQuery {
  readonly key: FeatureKey;
  readonly subject: string;
  readonly chainId: ChainId;
  readonly asOf: UnixMs;
}

export interface FeatureStore {
  read(query: AsOfQuery): Promise<FeatureRecord | null>;
  readMany(queries: readonly AsOfQuery[]): Promise<readonly FeatureRecord[]>;
  latestVersion(key: FeatureKey): Promise<number | null>;
}
