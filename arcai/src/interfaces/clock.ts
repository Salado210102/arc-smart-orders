import type { Iso8601, UnixMs } from "../types/branded.ts";

export interface Clock {
  nowMs(): UnixMs;
  nowIso(): Iso8601;
}
