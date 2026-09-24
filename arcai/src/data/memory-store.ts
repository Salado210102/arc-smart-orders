import type { DataStore } from "./store.ts";
import type {
  BlockRow,
  BlockStatus,
  IngestionRunRow,
  LogRow,
  QualityIssueRow,
  RunStatus,
  SourceRow,
  TokenRow,
  TransferCandidateRow,
  TxRow,
} from "./types.ts";

const blockKey = (chainId: number, hash: string) => `${chainId}:${hash.toLowerCase()}`;
const txKey = (chainId: number, hash: string) => `${chainId}:${hash.toLowerCase()}`;
const logKey = (chainId: number, hash: string, idx: number) =>
  `${chainId}:${hash.toLowerCase()}:${idx}`;
const tokenKey = (chainId: number, addr: string) => `${chainId}:${addr.toLowerCase()}`;
const cpKey = (chainId: number, stream: string) => `${chainId}:${stream}`;

export class MemoryStore implements DataStore {
  readonly blocks = new Map<string, BlockRow>();
  readonly txs = new Map<string, TxRow>();
  readonly logs = new Map<string, LogRow>();
  readonly candidates = new Map<string, TransferCandidateRow>();
  readonly tokens = new Map<string, TokenRow>();
  readonly sources = new Map<string, SourceRow>();
  readonly checkpoints = new Map<string, bigint>();
  readonly runs = new Map<string, IngestionRunRow>();
  readonly issues: QualityIssueRow[] = [];
  readonly failures = new Map<string, number>();

  injectFailure(operation: string, times = 1): void {
    this.failures.set(operation, (this.failures.get(operation) ?? 0) + times);
  }

  private maybeFail(operation: string): void {
    const remaining = this.failures.get(operation) ?? 0;
    if (remaining > 0) {
      this.failures.set(operation, remaining - 1);
      throw new Error(`injected_failure:${operation}`);
    }
  }

  async migrate(): Promise<void> {}

  async upsertSource(row: SourceRow): Promise<void> {
    if (!this.sources.has(row.sourceId)) this.sources.set(row.sourceId, { ...row });
  }

  async upsertSourceToken(row: TokenRow): Promise<void> {
    const key = tokenKey(row.chainId, row.address);
    if (!this.tokens.has(key)) this.tokens.set(key, { ...row, address: row.address.toLowerCase() });
  }

  async getToken(chainId: number, address: string): Promise<TokenRow | null> {
    return this.tokens.get(tokenKey(chainId, address)) ?? null;
  }

  async upsertBlock(row: BlockRow): Promise<void> {
    this.maybeFail("upsertBlock");
    const key = blockKey(row.chainId, row.blockHash);
    if (this.blocks.has(key)) return;
    this.blocks.set(key, { ...row, blockHash: row.blockHash.toLowerCase() });
  }

  async getBlockByHash(chainId: number, blockHash: string): Promise<BlockRow | null> {
    return this.blocks.get(blockKey(chainId, blockHash)) ?? null;
  }

  async getCanonicalBlockAtHeight(chainId: number, blockNumber: bigint): Promise<BlockRow | null> {
    for (const b of this.blocks.values()) {
      if (b.chainId === chainId && b.blockNumber === blockNumber && b.canonical) return b;
    }
    return null;
  }

  async getMaxCanonicalBlockNumber(chainId: number): Promise<bigint | null> {
    let max: bigint | null = null;
    for (const b of this.blocks.values()) {
      if (b.chainId === chainId && b.canonical) {
        if (max === null || b.blockNumber > max) max = b.blockNumber;
      }
    }
    return max;
  }

  async setBlockStatus(
    chainId: number,
    blockHash: string,
    status: BlockStatus,
    canonical: boolean,
    canonicalizedAt: number | null,
  ): Promise<void> {
    const b = this.blocks.get(blockKey(chainId, blockHash));
    if (!b) return;
    b.status = status;
    b.canonical = canonical;
    if (canonicalizedAt !== null) b.canonicalizedAt = canonicalizedAt;
  }

  async getObservedBlocksAtHeight(chainId: number, blockNumber: bigint): Promise<BlockRow[]> {
    const out: BlockRow[] = [];
    for (const b of this.blocks.values()) {
      if (b.chainId === chainId && b.blockNumber === blockNumber && !b.canonical) out.push(b);
    }
    return out;
  }

  async confirmObservedUpTo(
    chainId: number,
    upToBlock: bigint,
    status: BlockStatus,
    canonicalizedAt: number,
  ): Promise<number> {
    const canonicalHeights = new Set<string>();
    for (const b of this.blocks.values()) {
      if (b.chainId === chainId && b.canonical) canonicalHeights.add(b.blockNumber.toString());
    }
    const observedByHeight = new Map<string, BlockRow[]>();
    for (const b of this.blocks.values()) {
      if (b.chainId === chainId && b.status === "observed" && b.blockNumber <= upToBlock) {
        const key = b.blockNumber.toString();
        const list = observedByHeight.get(key);
        if (list) list.push(b);
        else observedByHeight.set(key, [b]);
      }
    }
    let n = 0;
    for (const [height, list] of observedByHeight) {
      if (list.length !== 1 || canonicalHeights.has(height)) continue;
      const b = list[0];
      b.status = status;
      b.canonical = true;
      b.canonicalizedAt = canonicalizedAt;
      n += 1;
    }
    const canonicalHashes = new Set<string>();
    for (const b of this.blocks.values()) {
      if (b.chainId === chainId && b.canonical && b.blockNumber <= upToBlock) {
        canonicalHashes.add(b.blockHash);
      }
    }
    for (const t of this.txs.values()) {
      if (t.chainId === chainId && !t.canonical && canonicalHashes.has(t.blockHash)) {
        t.canonical = true;
        n += 1;
      }
    }
    for (const l of this.logs.values()) {
      if (l.chainId === chainId && !l.canonical && canonicalHashes.has(l.blockHash)) {
        l.canonical = true;
        n += 1;
      }
    }
    for (const c of this.candidates.values()) {
      if (c.chainId === chainId && !c.canonical && canonicalHashes.has(c.blockHash)) {
        c.canonical = true;
        c.canonicalizedAt = canonicalizedAt;
        n += 1;
      }
    }
    return n;
  }

  async upsertTransactions(rows: TxRow[]): Promise<void> {
    for (const row of rows) {
      const key = txKey(row.chainId, row.txHash);
      if (this.txs.has(key)) continue;
      this.txs.set(key, { ...row, txHash: row.txHash.toLowerCase() });
    }
  }

  async getTransaction(chainId: number, txHash: string): Promise<TxRow | null> {
    return this.txs.get(txKey(chainId, txHash)) ?? null;
  }

  async upsertLogs(rows: LogRow[]): Promise<void> {
    for (const row of rows) {
      const key = logKey(row.chainId, row.blockHash, row.logIndex);
      if (!this.logs.has(key)) {
        this.logs.set(key, { ...row, blockHash: row.blockHash.toLowerCase() });
      }
    }
  }

  async setLogDecoded(
    chainId: number,
    blockHash: string,
    logIndex: number,
    eventType: string,
  ): Promise<void> {
    const l = this.logs.get(logKey(chainId, blockHash, logIndex));
    if (l) l.decodedEventType = eventType;
  }

  async getLog(chainId: number, blockHash: string, logIndex: number): Promise<LogRow | null> {
    return this.logs.get(logKey(chainId, blockHash, logIndex)) ?? null;
  }

  async countLogsInRange(chainId: number, fromBlock: bigint, toBlock: bigint): Promise<number> {
    let n = 0;
    for (const l of this.logs.values()) {
      if (l.chainId === chainId && l.blockNumber >= fromBlock && l.blockNumber <= toBlock) n += 1;
    }
    return n;
  }

  async insertCandidate(row: TransferCandidateRow): Promise<boolean> {
    const key = logKey(row.chainId, row.blockHash, row.logIndex);
    if (this.candidates.has(key)) return false;
    this.candidates.set(key, { ...row, blockHash: row.blockHash.toLowerCase() });
    return true;
  }

  async getCandidate(
    chainId: number,
    blockHash: string,
    logIndex: number,
  ): Promise<TransferCandidateRow | null> {
    return this.candidates.get(logKey(chainId, blockHash, logIndex)) ?? null;
  }

  async countCanonicalCandidates(chainId: number): Promise<number> {
    let n = 0;
    for (const c of this.candidates.values()) {
      if (c.chainId === chainId && c.canonical) n += 1;
    }
    return n;
  }

  async getCheckpoint(chainId: number, stream: string): Promise<bigint | null> {
    return this.checkpoints.get(cpKey(chainId, stream)) ?? null;
  }

  async setCheckpoint(
    chainId: number,
    stream: string,
    cursorBlock: bigint,
    _updatedAt: number,
  ): Promise<void> {
    this.maybeFail("setCheckpoint");
    this.checkpoints.set(cpKey(chainId, stream), cursorBlock);
  }

  async startIngestionRun(row: IngestionRunRow): Promise<void> {
    this.runs.set(row.runId, { ...row });
  }

  async finishIngestionRun(
    runId: string,
    status: RunStatus,
    progressBlock: bigint,
    error: string | null,
  ): Promise<void> {
    const r = this.runs.get(runId);
    if (!r) return;
    r.status = status;
    r.progressBlock = progressBlock;
    r.error = error;
  }

  async getIngestionRun(runId: string): Promise<IngestionRunRow | null> {
    return this.runs.get(runId) ?? null;
  }

  async recordIssue(row: QualityIssueRow): Promise<void> {
    this.issues.push({ ...row });
  }

  async countIssues(chainId: number): Promise<number> {
    return this.issues.filter((i) => i.chainId === chainId).length;
  }

  async close(): Promise<void> {}
}
