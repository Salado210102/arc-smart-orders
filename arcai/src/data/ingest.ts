import type { DataEngineConfig } from "./config.ts";
import { seedFor } from "./config.ts";
import { decodeErc20TransferV1 } from "./decoder.ts";
import type { Logger, Metrics } from "./metrics.ts";
import type { BlockSource } from "./source.ts";
import type { DataStore } from "./store.ts";
import type { BlockRow, BlockStatus, LogRow, RawBlock, RawLog, TxRow } from "./types.ts";

export interface IngestDeps {
  store: DataStore;
  source: BlockSource;
  config: DataEngineConfig;
  logger: Logger;
  metrics: Metrics;
  now?: () => number;
  newId?: () => string;
  sleep?: (ms: number) => Promise<void>;
}

export type BlockStatusResult = "ingested" | "missing" | "conflict" | "ambiguous";

export interface BlockIngestResult {
  blockNumber: bigint;
  status: BlockStatusResult;
  candidates: number;
  decodeFailures: number;
  conflict: boolean;
}

export interface TickResult {
  from: bigint;
  to: bigint;
  processed: number;
  primed: boolean;
}

const defaultSleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

export class Ingestor {
  private readonly store: DataStore;
  private readonly source: BlockSource;
  private readonly config: DataEngineConfig;
  private readonly logger: Logger;
  private readonly metrics: Metrics;
  private readonly now: () => number;
  private readonly newId: () => string;
  private readonly sleep: (ms: number) => Promise<void>;
  private headValue = 0n;

  constructor(deps: IngestDeps) {
    this.store = deps.store;
    this.source = deps.source;
    this.config = deps.config;
    this.logger = deps.logger;
    this.metrics = deps.metrics;
    this.now = deps.now ?? (() => Date.now());
    this.newId = deps.newId ?? (() => `issue-${Date.now()}-${Math.random().toString(16).slice(2)}`);
    this.sleep = deps.sleep ?? defaultSleep;
  }

  get head(): bigint {
    return this.headValue;
  }

  async init(): Promise<void> {
    await this.store.migrate();
    await this.store.upsertSource({
      sourceId: this.config.sourceId,
      kind: "rpc",
      endpointRef: this.config.rpcUrl,
      priority: 0,
      createdAt: this.now(),
    });
    for (const token of this.config.seed) {
      await this.store.upsertSourceToken({
        chainId: this.config.chainId,
        address: token.address,
        symbol: token.symbol,
        name: null,
        decimals: token.decimals,
        status: "registered",
        discoverySource: "seed",
        firstSeenAt: this.now(),
      });
    }
  }

  private async issue(
    kind: string,
    severity: "info" | "warning" | "critical",
    detail: string,
    extra: { blockNumber?: bigint; txHash?: string; logIndex?: number } = {},
  ): Promise<void> {
    this.metrics.inc("qualityIssues");
    await this.store.recordIssue({
      id: this.newId(),
      chainId: this.config.chainId,
      kind,
      severity,
      blockNumber: extra.blockNumber ?? null,
      txHash: extra.txHash ?? null,
      logIndex: extra.logIndex ?? null,
      detail,
      detectedAt: this.now(),
    });
    this.logger.warn("data_quality_issue", {
      kind,
      severity,
      detail,
      blockNumber: extra.blockNumber?.toString(),
    });
  }

  private async withRetry<T>(op: () => Promise<T>, label: string): Promise<T> {
    let attempt = 0;
    for (;;) {
      try {
        return await op();
      } catch (e) {
        attempt += 1;
        if (attempt > this.config.maxRetries) {
          this.metrics.inc("providerErrors");
          throw e;
        }
        this.metrics.inc("retries");
        this.logger.warn("provider_retry", { label, attempt, error: (e as Error).message });
        await this.sleep(this.config.retryBaseMs * 2 ** (attempt - 1));
      }
    }
  }

  private toTxRows(block: RawBlock): TxRow[] {
    return block.transactions.map((tx) => ({
      chainId: this.config.chainId,
      txHash: tx.hash.toLowerCase(),
      blockNumber: block.number,
      blockHash: block.hash.toLowerCase(),
      transactionIndex: tx.transactionIndex,
      fromAddress: tx.from === null ? null : tx.from.toLowerCase(),
      toAddress: tx.to === null ? null : tx.to.toLowerCase(),
      value: tx.value.toString(),
      status: tx.status,
      gasUsed: tx.gasUsed === null ? null : tx.gasUsed.toString(),
      effectiveGasPrice: tx.effectiveGasPrice === null ? null : tx.effectiveGasPrice.toString(),
      nonce: tx.nonce,
      input: tx.input,
      inputSelector:
        tx.input.startsWith("0x") && tx.input.length >= 10 ? tx.input.slice(0, 10).toLowerCase() : null,
      canonical: false,
      firstSeenAt: this.now(),
      decodedAt: null,
      sourceId: this.config.sourceId,
    }));
  }

  private toLogRows(logs: RawLog[]): LogRow[] {
    return logs.map((log) => ({
      chainId: this.config.chainId,
      blockNumber: log.blockNumber,
      blockHash: log.blockHash.toLowerCase(),
      transactionHash: log.transactionHash.toLowerCase(),
      transactionIndex: log.transactionIndex,
      logIndex: log.logIndex,
      address: log.address.toLowerCase(),
      topics: log.topics,
      data: log.data,
      removed: log.removed,
      canonical: false,
      firstSeenAt: this.now(),
      decodedAt: null,
      sourceId: this.config.sourceId,
      decodedEventType: null,
    }));
  }

  private rawBlockRow(block: RawBlock, status: BlockStatus, canonical: boolean): BlockRow {
    return {
      chainId: this.config.chainId,
      blockNumber: block.number,
      blockHash: block.hash.toLowerCase(),
      parentHash: block.parentHash.toLowerCase(),
      timestamp: block.timestamp,
      firstSeenAt: this.now(),
      decodedAt: null,
      canonicalizedAt: null,
      status,
      canonical,
      sourceId: this.config.sourceId,
      txCount: block.transactions.length,
      logCount: 0,
    };
  }

  async confirmUpTo(blockNumber: bigint): Promise<number> {
    const upTo = blockNumber - BigInt(this.config.operationalConfirmationDepth);
    if (upTo < 0n) return 0;
    const status: BlockStatus = this.config.finalitySource === "none" ? "confirmed" : "finalized";
    return this.store.confirmObservedUpTo(this.config.chainId, upTo, status, this.now());
  }

  async ingestBlock(blockNumber: bigint): Promise<BlockIngestResult> {
    const block = await this.withRetry(() => this.source.getBlock(blockNumber), "getBlock");
    if (block === null) {
      await this.issue("missing_block", "warning", `block ${blockNumber} unavailable`, {
        blockNumber,
      });
      return { blockNumber, status: "missing", candidates: 0, decodeFailures: 0, conflict: false };
    }

    const incomingHash = block.hash.toLowerCase();
    const canonicalAtHeight = await this.store.getCanonicalBlockAtHeight(
      this.config.chainId,
      blockNumber,
    );

    if (canonicalAtHeight) {
      if (canonicalAtHeight.blockHash.toLowerCase() === incomingHash) {
        await this.store.upsertBlock(this.rawBlockRow(block, "observed", false));
        await this.store.setCheckpoint(this.config.chainId, this.config.stream, blockNumber, this.now());
        return { blockNumber, status: "ingested", candidates: 0, decodeFailures: 0, conflict: false };
      }
      await this.store.upsertBlock(this.rawBlockRow(block, "observed", false));
      this.metrics.inc("conflicts");
      await this.issue(
        "provider_conflict_after_canonical",
        "critical",
        `height ${blockNumber} canonical=${canonicalAtHeight.blockHash} incoming=${block.hash}; canonical preserved, incoming quarantined`,
        { blockNumber },
      );
      this.logger.warn("provider_conflict_after_canonical", {
        blockNumber: blockNumber.toString(),
        canonical: canonicalAtHeight.blockHash,
        incoming: block.hash,
      });
      await this.store.setCheckpoint(this.config.chainId, this.config.stream, blockNumber, this.now());
      return { blockNumber, status: "conflict", candidates: 0, decodeFailures: 0, conflict: true };
    }

    const parentCanonical = await this.store.getCanonicalBlockAtHeight(
      this.config.chainId,
      blockNumber - 1n,
    );
    const observedAtHeight = await this.store.getObservedBlocksAtHeight(
      this.config.chainId,
      blockNumber,
    );
    const observedConflict = observedAtHeight.some((b) => b.blockHash.toLowerCase() !== incomingHash);
    const parentConflict =
      parentCanonical !== null &&
      parentCanonical.blockHash.toLowerCase() !== block.parentHash.toLowerCase();

    await this.store.upsertBlock(this.rawBlockRow(block, "observed", false));

    if (observedConflict || parentConflict) {
      this.metrics.inc("conflicts");
      await this.issue(
        parentConflict ? "provider_conflict_parent_mismatch" : "provider_conflict_before_canonical",
        "critical",
        `ambiguous observation at height ${blockNumber} (parentConflict=${parentConflict})`,
        { blockNumber },
      );
      return { blockNumber, status: "ambiguous", candidates: 0, decodeFailures: 0, conflict: true };
    }

    this.metrics.inc("blocksProcessed");

    const txRows = this.toTxRows(block);
    await this.store.upsertTransactions(txRows);
    this.metrics.inc("transactionsStored", txRows.length);

    const logs = await this.withRetry(() => this.source.getLogs(blockNumber, blockNumber), "getLogs");
    const logRows = this.toLogRows(logs);
    await this.store.upsertLogs(logRows);
    this.metrics.inc("logsStored", logRows.length);

    const decodedAt = this.now();
    let candidates = 0;
    let decodeFailures = 0;
    for (const log of logs) {
      const seed = seedFor(this.config, log.address);
      if (!seed) continue;
      const token = await this.store.getToken(this.config.chainId, log.address);
      const decimals = token?.decimals ?? seed.decimals;
      const tokenStatus = token?.status ?? "unvalidated";
      const result = decodeErc20TransferV1({
        chainId: this.config.chainId,
        log,
        sourceId: this.config.sourceId,
        firstSeenAt: this.now(),
        decodedAt,
        emitterKind: seed.emitterKind,
        tokenStatus,
        decimals,
      });
      if (!result.ok) {
        decodeFailures += 1;
        this.metrics.inc("decodeFailures");
        await this.issue("decode_failure", "warning", result.error, {
          blockNumber,
          txHash: log.transactionHash,
          logIndex: log.logIndex,
        });
        continue;
      }
      const inserted = await this.store.insertCandidate(result.candidate);
      if (inserted) {
        candidates += 1;
        this.metrics.inc("candidatesStored");
      } else {
        this.metrics.inc("duplicateObservations");
      }
      await this.store.setLogDecoded(
        this.config.chainId,
        log.blockHash,
        log.logIndex,
        `${result.candidate.decoder}@${result.candidate.decoderVersion}`,
      );
    }

    await this.confirmUpTo(blockNumber);
    await this.store.setCheckpoint(this.config.chainId, this.config.stream, blockNumber, this.now());

    return { blockNumber, status: "ingested", candidates, decodeFailures, conflict: false };
  }

  async runOnce(): Promise<TickResult> {
    const latest = await this.withRetry(() => this.source.latestBlockNumber(), "latestBlockNumber");
    this.headValue = latest;
    const checkpoint = await this.store.getCheckpoint(this.config.chainId, this.config.stream);

    if (checkpoint === null && this.config.startBlock === null) {
      await this.store.setCheckpoint(this.config.chainId, this.config.stream, latest, this.now());
      this.logger.info("checkpoint_primed", { at: latest.toString() });
      return { from: latest, to: latest, processed: 0, primed: true };
    }

    const from = checkpoint === null ? this.config.startBlock ?? latest : checkpoint + 1n;
    const maxEnd = from + BigInt(this.config.maxBlocksPerTick) - 1n;
    const end = latest < maxEnd ? latest : maxEnd;
    if (end < from) return { from, to: from - 1n, processed: 0, primed: false };

    const runId = this.newId();
    await this.store.startIngestionRun({
      runId,
      kind: "live",
      chainId: this.config.chainId,
      fromBlock: from,
      toBlock: end,
      status: "running",
      progressBlock: from - 1n,
      startedAt: this.now(),
      updatedAt: this.now(),
      error: null,
    });

    let last = from - 1n;
    try {
      for (let n = from; n <= end; n += 1n) {
        const result = await this.ingestBlock(n);
        if (result.status === "missing" || result.status === "ambiguous") break;
        last = n;
      }
      await this.store.finishIngestionRun(runId, "completed", last, null);
    } catch (e) {
      await this.store.finishIngestionRun(runId, "failed", last, (e as Error).message);
      throw e;
    }

    return { from, to: last, processed: last >= from ? Number(last - from + 1n) : 0, primed: false };
  }

  async run(signal?: { aborted: boolean }): Promise<void> {
    for (;;) {
      try {
        await this.runOnce();
      } catch (e) {
        this.logger.error("ingest_tick_failed", { error: (e as Error).message });
      }
      if (signal?.aborted === true) break;
      await this.sleep(this.config.pollIntervalMs);
    }
  }
}
