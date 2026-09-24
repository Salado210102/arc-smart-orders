import type { Iso8601, UnixMs } from "./branded.ts";

export type AIProviderKind = "openai" | "anthropic" | "google" | "local" | "custom";

export type AIRole = "system" | "user" | "assistant" | "tool";

export type AICapability =
  | "analysis"
  | "summarize"
  | "translate"
  | "tool-call"
  | "refuse";

export type AIRefusalReason =
  | "insufficient-evidence"
  | "out-of-scope"
  | "unsafe-request"
  | "rate-limited";

export interface AIMessage {
  readonly role: AIRole;
  readonly content: string;
  readonly name: string | null;
  readonly at: UnixMs;
}

export interface AIRequest {
  readonly messages: readonly AIMessage[];
  readonly tools: readonly string[];
  readonly temperature: number;
  readonly maxOutputTokens: number;
  readonly cacheKey: string | null;
}

export interface AIUsage {
  readonly provider: AIProviderKind;
  readonly model: string;
  readonly inputTokens: number;
  readonly outputTokens: number;
  readonly costUsd: number;
  readonly latencyMs: number;
}

export interface AIResponse {
  readonly kind: "answer" | "refusal" | "tool-call";
  readonly text: string;
  readonly structured: unknown | null;
  readonly refusalReason: AIRefusalReason | null;
  readonly usage: AIUsage;
  readonly disclaimer: string;
  readonly createdAt: Iso8601;
}
