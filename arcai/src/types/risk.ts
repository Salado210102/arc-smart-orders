import type { Iso8601, Score0to100 } from "./branded.ts";

export type RiskLevel = "low" | "medium" | "high" | "critical";

export type RiskFlag =
  | "low-liquidity"
  | "holder-concentration"
  | "deployer-links"
  | "approval-anomaly"
  | "price-impact"
  | "malicious-contract";

export interface RiskAssessment {
  readonly level: RiskLevel;
  readonly score: Score0to100;
  readonly flags: readonly RiskFlag[];
  readonly rationale: string;
  readonly assessedAt: Iso8601;
}

export interface RiskLimits {
  readonly maxNotionalPerTradeUsd: number;
  readonly maxDailyNotionalUsd: number;
  readonly maxPriceImpactBps: number;
  readonly allowedVenues: readonly string[];
  readonly emergencyStop: boolean;
}
