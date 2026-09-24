export interface Counters {
  blocksProcessed: number;
  transactionsStored: number;
  logsStored: number;
  candidatesStored: number;
  decodeFailures: number;
  providerErrors: number;
  retries: number;
  reorgs: number;
  qualityIssues: number;
  duplicateObservations: number;
  conflicts: number;
}

export function newCounters(): Counters {
  return {
    blocksProcessed: 0,
    transactionsStored: 0,
    logsStored: 0,
    candidatesStored: 0,
    decodeFailures: 0,
    providerErrors: 0,
    retries: 0,
    reorgs: 0,
    qualityIssues: 0,
    duplicateObservations: 0,
    conflicts: 0,
  };
}

export class Metrics {
  readonly counters: Counters;

  constructor(counters: Counters = newCounters()) {
    this.counters = counters;
  }

  inc(key: keyof Counters, by = 1): void {
    this.counters[key] += by;
  }

  snapshot(): Counters {
    return { ...this.counters };
  }
}

export interface Logger {
  info(message: string, meta?: Record<string, unknown>): void;
  warn(message: string, meta?: Record<string, unknown>): void;
  error(message: string, meta?: Record<string, unknown>): void;
}

export function consoleLogger(): Logger {
  const emit = (level: string, message: string, meta?: Record<string, unknown>) => {
    const line = { ts: Date.now(), level, msg: message, ...(meta ?? {}) };
    const out = JSON.stringify(line);
    if (level === "error") console.error(out);
    else if (level === "warn") console.warn(out);
    else console.log(out);
  };
  return {
    info: (m, meta) => emit("info", m, meta),
    warn: (m, meta) => emit("warn", m, meta),
    error: (m, meta) => emit("error", m, meta),
  };
}

export interface LoggerSink {
  (line: Record<string, unknown>): void;
}

export function collectingLogger(sink: LoggerSink): Logger {
  const emit = (level: string, message: string, meta?: Record<string, unknown>) =>
    sink({ ts: Date.now(), level, msg: message, ...(meta ?? {}) });
  return {
    info: (m, meta) => emit("info", m, meta),
    warn: (m, meta) => emit("warn", m, meta),
    error: (m, meta) => emit("error", m, meta),
  };
}
