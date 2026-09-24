import type { AIProviderKind, AIRequest, AIResponse } from "../types/ai.ts";

export interface AIProvider {
  readonly kind: AIProviderKind;
  readonly model: string;
  complete(request: AIRequest): Promise<AIResponse>;
  healthy(): Promise<boolean>;
}
