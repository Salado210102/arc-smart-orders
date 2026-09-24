export type BlockStatus = "observed" | "confirmed" | "finalized" | "orphaned";

export type EmitterKind = "erc20" | "native-system";

export type TokenStatus =
  | "unvalidated"
  | "discovered"
  | "validated"
  | "registered"
  | "rejected";

export type IssueSeverity = "info" | "warning" | "critical";

export type RunStatus = "running" | "completed" | "failed";

export interface RawTx {
  hash: string;
  transactionIndex: number;
  from: string | null;
  to: string | null;
  value: bigint;
  nonce: number | null;
  input: string;
  status: number | null;
  gasUsed: bigint | null;
  effectiveGasPrice: bigint | null;
}

export interface RawBlock {
  number: bigint;
  hash: string;
  parentHash: string;
  timestamp: bigint;
  transactions: RawTx[];
}

export interface RawLog {
  address: string;
  topics: string[];
  data: string;
  blockNumber: bigint;
  blockHash: string;
  transactionHash: string;
  transactionIndex: number;
  logIndex: number;
  removed: boolean;
}

export interface BlockRow {
  chainId: number;
  blockNumber: bigint;
  blockHash: string;
  parentHash: string;
  timestamp: bigint;
  firstSeenAt: number;
  decodedAt: number | null;
  canonicalizedAt: number | null;
  status: BlockStatus;
  canonical: boolean;
  sourceId: string;
  txCount: number;
  logCount: number;
}

export interface TxRow {
  chainId: number;
  txHash: string;
  blockNumber: bigint;
  blockHash: string;
  transactionIndex: number;
  fromAddress: string | null;
  toAddress: string | null;
  value: string;
  status: number | null;
  gasUsed: string | null;
  effectiveGasPrice: string | null;
  nonce: number | null;
  input: string;
  inputSelector: string | null;
  canonical: boolean;
  firstSeenAt: number;
  decodedAt: number | null;
  sourceId: string;
}

export interface LogRow {
  chainId: number;
  blockNumber: bigint;
  blockHash: string;
  transactionHash: string;
  transactionIndex: number;
  logIndex: number;
  address: string;
  topics: string[];
  data: string;
  removed: boolean;
  canonical: boolean;
  firstSeenAt: number;
  decodedAt: number | null;
  sourceId: string;
  decodedEventType: string | null;
}

export interface TransferCandidateRow {
  chainId: number;
  blockNumber: bigint;
  blockHash: string;
  transactionHash: string;
  transactionIndex: number;
  logIndex: number;
  tokenAddress: string;
  emitterKind: EmitterKind;
  fromAddress: string;
  toAddress: string;
  valueRaw: string;
  decimals: number | null;
  amount: string | null;
  isZeroValue: boolean;
  isSelf: boolean;
  tokenStatus: TokenStatus;
  canonical: boolean;
  sourceId: string;
  firstSeenAt: number;
  decodedAt: number;
  canonicalizedAt: number | null;
  decoder: string;
  decoderVersion: number;
}

export interface TokenRow {
  chainId: number;
  address: string;
  symbol: string | null;
  name: string | null;
  decimals: number | null;
  status: TokenStatus;
  discoverySource: string;
  firstSeenAt: number;
}

export interface SourceRow {
  sourceId: string;
  kind: string;
  endpointRef: string;
  priority: number;
  createdAt: number;
}

export interface CheckpointRow {
  chainId: number;
  stream: string;
  cursorBlock: bigint;
  updatedAt: number;
}

export interface IngestionRunRow {
  runId: string;
  kind: "live" | "backfill";
  chainId: number;
  fromBlock: bigint;
  toBlock: bigint;
  status: RunStatus;
  progressBlock: bigint;
  startedAt: number;
  updatedAt: number;
  error: string | null;
}

export interface QualityIssueRow {
  id: string;
  chainId: number;
  kind: string;
  severity: IssueSeverity;
  blockNumber: bigint | null;
  txHash: string | null;
  logIndex: number | null;
  detail: string;
  detectedAt: number;
}

export interface SeedToken {
  address: string;
  emitterKind: EmitterKind;
  symbol: string;
  decimals: number | null;
}
