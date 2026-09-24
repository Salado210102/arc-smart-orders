import type { Iso8601, Score0to100, SignalId } from "./branded.ts";
import type { FeatureKey } from "./feature.ts";

export type SignalKind =
  | "smart-money"
  | "consensus"
  | "pattern"
  | "risk"
  | "exit";

export type SignalDirection = "long" | "short" | "neutral" | "avoid";

export interface Signal {
  readonly id: SignalId;
  readonly kind: SignalKind;
  readonly direction: SignalDirection;
  readonly score: Score0to100;
  readonly confidence: Score0to100;
  readonly features: readonly FeatureKey[];
  readonly modelVersion: string;
  readonly rationale: string;
  readonly createdAt: Iso8601;
}

export interface SignalOutcome {
  readonly signalId: SignalId;
  readonly horizonMs: number;
  readonly entryAssumption: number | null;
  readonly observedReturn: number | null;
  readonly liquidityAdjustedReturn: number | null;
  readonly slippageAdjustedReturn: number | null;
  readonly resolvedAt: Iso8601 | null;
}

export interface SignalMetrics {
  readonly sampleSize: number;
  readonly winRate: number | null;
  readonly medianReturn: number | null;
  readonly meanReturn: number | null;
  readonly maxDrawdown: number | null;
  readonly falsePositives: number;
  readonly falseNegatives: number;
}
