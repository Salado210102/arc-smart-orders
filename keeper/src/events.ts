// Tiny in-process event bus for live updates (WebSocket broadcast).
import { EventEmitter } from "node:events";

export const bus = new EventEmitter();
bus.setMaxListeners(0);

export function emitEvent(e: Record<string, unknown>) {
  bus.emit("event", { ts: Date.now(), ...e });
}
