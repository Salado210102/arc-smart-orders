import type { Iso8601, RequestId, UserId } from "../types/branded.ts";
import type { TradeIntent } from "../types/intent.ts";

export interface JsonSchema {
  readonly type:
    | "object"
    | "array"
    | "string"
    | "number"
    | "integer"
    | "boolean"
    | "null";
  readonly description?: string;
  readonly properties?: Readonly<Record<string, JsonSchema>>;
  readonly items?: JsonSchema;
  readonly required?: readonly string[];
  readonly enum?: readonly unknown[];
}

export interface ToolContext {
  readonly userId: UserId;
  readonly requestId: RequestId;
  readonly now: Iso8601;
}

export interface ToolError {
  readonly code: string;
  readonly message: string;
}

export type ToolResult<Output> =
  | { readonly ok: true; readonly data: Output }
  | { readonly ok: false; readonly error: ToolError };

export interface ToolDefinition<Input = unknown, Output = unknown> {
  readonly name: string;
  readonly description: string;
  readonly inputSchema: JsonSchema;
  readonly outputSchema: JsonSchema;
  readonly requiresAuthorization: boolean;
  readonly rateLimitPerMinute: number;
  invoke(input: Input, context: ToolContext): Promise<ToolResult<Output>>;
}

export interface ToolRegistry {
  get(name: string): ToolDefinition | null;
  list(): readonly ToolDefinition[];
}

export interface IntentToolOutput {
  readonly intent: TradeIntent;
  readonly requiresSignature: true;
}
