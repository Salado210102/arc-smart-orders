import type { DataEngineConfig } from "./config.ts";
import type { Counters, Metrics } from "./metrics.ts";
import type { DataStore } from "./store.ts";

export interface HealthReport {
  ok: boolean;
  chainId: number;
  stream: string;
  head: string;
  checkpoint: string | null;
  lag: string | null;
  counters: Counters;
  issues: number;
}

export async function getHealth(
  store: DataStore,
  config: DataEngineConfig,
  metrics: Metrics,
  head: bigint,
): Promise<HealthReport> {
  const checkpoint = await store.getCheckpoint(config.chainId, config.stream);
  const issues = await store.countIssues(config.chainId);
  return {
    ok: true,
    chainId: config.chainId,
    stream: config.stream,
    head: head.toString(),
    checkpoint: checkpoint === null ? null : checkpoint.toString(),
    lag: checkpoint === null ? null : (head - checkpoint).toString(),
    counters: metrics.snapshot(),
    issues,
  };
}
