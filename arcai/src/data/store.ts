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

export interface DataStore {
  migrate(): Promise<void>;
  upsertSource(row: SourceRow): Promise<void>;
  upsertSourceToken(row: TokenRow): Promise<void>;
  getToken(chainId: number, address: string): Promise<TokenRow | null>;

  upsertBlock(row: BlockRow): Promise<void>;
  getBlockByHash(chainId: number, blockHash: string): Promise<BlockRow | null>;
  getCanonicalBlockAtHeight(chainId: number, blockNumber: bigint): Promise<BlockRow | null>;
  getObservedBlocksAtHeight(chainId: number, blockNumber: bigint): Promise<BlockRow[]>;
  getMaxCanonicalBlockNumber(chainId: number): Promise<bigint | null>;
  setBlockStatus(
    chainId: number,
    blockHash: string,
    status: BlockStatus,
    canonical: boolean,
    canonicalizedAt: number | null,
  ): Promise<void>;
  confirmObservedUpTo(
    chainId: number,
    upToBlock: bigint,
    status: BlockStatus,
    canonicalizedAt: number,
  ): Promise<number>;

  upsertTransactions(rows: TxRow[]): Promise<void>;
  getTransaction(chainId: number, txHash: string): Promise<TxRow | null>;

  upsertLogs(rows: LogRow[]): Promise<void>;
  setLogDecoded(chainId: number, blockHash: string, logIndex: number, eventType: string): Promise<void>;
  getLog(chainId: number, blockHash: string, logIndex: number): Promise<LogRow | null>;
  countLogsInRange(chainId: number, fromBlock: bigint, toBlock: bigint): Promise<number>;

  insertCandidate(row: TransferCandidateRow): Promise<boolean>;
  getCandidate(chainId: number, blockHash: string, logIndex: number): Promise<TransferCandidateRow | null>;
  countCanonicalCandidates(chainId: number): Promise<number>;

  getCheckpoint(chainId: number, stream: string): Promise<bigint | null>;
  setCheckpoint(chainId: number, stream: string, cursorBlock: bigint, updatedAt: number): Promise<void>;

  startIngestionRun(row: IngestionRunRow): Promise<void>;
  finishIngestionRun(runId: string, status: RunStatus, progressBlock: bigint, error: string | null): Promise<void>;
  getIngestionRun(runId: string): Promise<IngestionRunRow | null>;

  recordIssue(row: QualityIssueRow): Promise<void>;
  countIssues(chainId: number): Promise<number>;

  close(): Promise<void>;
}
