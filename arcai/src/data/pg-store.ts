import { Pool } from "pg";
import type { QueryResultRow } from "pg";
import { MIGRATION_1, SCHEMA_VERSION } from "./schema.ts";
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

export interface PgQueryable {
  query(text: string, params?: unknown[]): Promise<{ rows: QueryResultRow[]; rowCount: number | null }>;
}

export interface PgClientLike extends PgQueryable {
  release(): void;
}

export interface PgPoolLike extends PgQueryable {
  connect(): Promise<PgClientLike>;
  end(): Promise<void>;
}

const toBigInt = (v: unknown, fallback = 0n): bigint => {
  if (v === null || v === undefined) return fallback;
  return BigInt(v as string);
};

const toNumber = (v: unknown): number => (v === null || v === undefined ? 0 : Number(v));

const toNullableNumber = (v: unknown): number | null =>
  v === null || v === undefined ? null : Number(v);

const toNullableString = (v: unknown): string | null =>
  v === null || v === undefined ? null : String(v);

export class PgStore implements DataStore {
  private readonly pool: PgPoolLike;

  constructor(connectionString: string, poolFactory?: () => PgPoolLike) {
    this.pool = poolFactory
      ? poolFactory()
      : (new Pool({ connectionString, max: 5 }) as unknown as PgPoolLike);
  }

  async migrate(): Promise<void> {
    const client = await this.pool.connect();
    try {
      await client.query("BEGIN");
      for (const stmt of MIGRATION_1) await client.query(stmt);
      await client.query(
        "INSERT INTO schema_version(version, applied_at) VALUES($1, $2) ON CONFLICT (version) DO NOTHING",
        [SCHEMA_VERSION, Date.now()],
      );
      await client.query("COMMIT");
    } catch (e) {
      await client.query("ROLLBACK");
      throw e;
    } finally {
      client.release();
    }
  }

  async upsertSource(row: SourceRow): Promise<void> {
    await this.pool.query(
      `INSERT INTO sources(source_id, kind, endpoint_ref, priority, created_at)
       VALUES($1,$2,$3,$4,$5) ON CONFLICT (source_id) DO UPDATE SET
       kind=EXCLUDED.kind, endpoint_ref=EXCLUDED.endpoint_ref, priority=EXCLUDED.priority`,
      [row.sourceId, row.kind, row.endpointRef, row.priority, row.createdAt],
    );
  }

  async upsertSourceToken(row: TokenRow): Promise<void> {
    await this.pool.query(
      `INSERT INTO tokens(chain_id, address, symbol, name, decimals, status, discovery_source, first_seen_at)
       VALUES($1,$2,$3,$4,$5,$6,$7,$8) ON CONFLICT (chain_id, address) DO NOTHING`,
      [
        row.chainId,
        row.address.toLowerCase(),
        row.symbol,
        row.name,
        row.decimals,
        row.status,
        row.discoverySource,
        row.firstSeenAt,
      ],
    );
  }

  async getToken(chainId: number, address: string): Promise<TokenRow | null> {
    const res = await this.pool.query(
      "SELECT * FROM tokens WHERE chain_id=$1 AND address=$2",
      [chainId, address.toLowerCase()],
    );
    const r = res.rows[0];
    if (!r) return null;
    return {
      chainId: Number(r.chain_id),
      address: String(r.address),
      symbol: toNullableString(r.symbol),
      name: toNullableString(r.name),
      decimals: toNullableNumber(r.decimals),
      status: r.status as TokenRow["status"],
      discoverySource: String(r.discovery_source),
      firstSeenAt: toNumber(r.first_seen_at),
    };
  }

  async upsertBlock(row: BlockRow): Promise<void> {
    await this.pool.query(
      `INSERT INTO blocks(chain_id, block_number, block_hash, parent_hash, timestamp, first_seen_at,
         decoded_at, canonicalized_at, status, canonical, source_id, tx_count, log_count)
       VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
       ON CONFLICT (chain_id, block_hash) DO NOTHING`,
      [
        row.chainId,
        row.blockNumber.toString(),
        row.blockHash.toLowerCase(),
        row.parentHash.toLowerCase(),
        row.timestamp.toString(),
        row.firstSeenAt,
        row.decodedAt,
        row.canonicalizedAt,
        row.status,
        row.canonical,
        row.sourceId,
        row.txCount,
        row.logCount,
      ],
    );
  }

  private mapBlock(r: QueryResultRow): BlockRow {
    return {
      chainId: Number(r.chain_id),
      blockNumber: toBigInt(r.block_number),
      blockHash: String(r.block_hash),
      parentHash: String(r.parent_hash),
      timestamp: toBigInt(r.timestamp),
      firstSeenAt: toNumber(r.first_seen_at),
      decodedAt: toNullableNumber(r.decoded_at),
      canonicalizedAt: toNullableNumber(r.canonicalized_at),
      status: r.status as BlockRow["status"],
      canonical: Boolean(r.canonical),
      sourceId: String(r.source_id),
      txCount: toNumber(r.tx_count),
      logCount: toNumber(r.log_count),
    };
  }

  async getBlockByHash(chainId: number, blockHash: string): Promise<BlockRow | null> {
    const res = await this.pool.query(
      "SELECT * FROM blocks WHERE chain_id=$1 AND block_hash=$2",
      [chainId, blockHash.toLowerCase()],
    );
    return res.rows[0] ? this.mapBlock(res.rows[0]) : null;
  }

  async getCanonicalBlockAtHeight(chainId: number, blockNumber: bigint): Promise<BlockRow | null> {
    const res = await this.pool.query(
      "SELECT * FROM blocks WHERE chain_id=$1 AND block_number=$2 AND canonical=true LIMIT 1",
      [chainId, blockNumber.toString()],
    );
    return res.rows[0] ? this.mapBlock(res.rows[0]) : null;
  }

  async getMaxCanonicalBlockNumber(chainId: number): Promise<bigint | null> {
    const res = await this.pool.query(
      "SELECT MAX(block_number) AS m FROM blocks WHERE chain_id=$1 AND canonical=true",
      [chainId],
    );
    const m = res.rows[0]?.m;
    return m === null || m === undefined ? null : BigInt(m as string);
  }

  async getObservedBlocksAtHeight(chainId: number, blockNumber: bigint): Promise<BlockRow[]> {
    const res = await this.pool.query(
      "SELECT * FROM blocks WHERE chain_id=$1 AND block_number=$2 AND canonical=false",
      [chainId, blockNumber.toString()],
    );
    return res.rows.map((r) => this.mapBlock(r));
  }

  async setBlockStatus(
    chainId: number,
    blockHash: string,
    status: BlockStatus,
    canonical: boolean,
    canonicalizedAt: number | null,
  ): Promise<void> {
    await this.pool.query(
      `UPDATE blocks SET status=$3, canonical=$4,
         canonicalized_at=COALESCE($5, canonicalized_at)
       WHERE chain_id=$1 AND block_hash=$2`,
      [chainId, blockHash.toLowerCase(), status, canonical, canonicalizedAt],
    );
  }

  async confirmObservedUpTo(
    chainId: number,
    upToBlock: bigint,
    status: BlockStatus,
    canonicalizedAt: number,
  ): Promise<number> {
    const upTo = upToBlock.toString();
    const observed = await this.pool.query(
      "SELECT block_number FROM blocks WHERE chain_id=$1 AND status='observed' AND block_number<=$2",
      [chainId, upTo],
    );
    const counts = new Map<string, number>();
    for (const r of observed.rows) {
      const h = String(r.block_number);
      counts.set(h, (counts.get(h) ?? 0) + 1);
    }
    const canonicalRows = await this.pool.query(
      "SELECT block_number FROM blocks WHERE chain_id=$1 AND canonical=true AND block_number<=$2",
      [chainId, upTo],
    );
    const canonicalSet = new Set(canonicalRows.rows.map((r) => String(r.block_number)));
    const heights = [...counts.entries()]
      .filter(([h, n]) => n === 1 && !canonicalSet.has(h))
      .map(([h]) => h);
    if (heights.length === 0) return 0;

    const blockList = heights.map((_, i) => `$${i + 4}`).join(",");
    let total = 0;
    const b = await this.pool.query(
      `UPDATE blocks SET status=$2, canonical=true, canonicalized_at=$3
       WHERE chain_id=$1 AND status='observed' AND block_number IN (${blockList})`,
      [chainId, status, canonicalizedAt, ...heights],
    );
    total += b.rowCount ?? 0;

    const plainList = heights.map((_, i) => `$${i + 2}`).join(",");
    const t = await this.pool.query(
      `UPDATE transactions SET canonical=true
       WHERE chain_id=$1 AND canonical=false AND block_number IN (${plainList})`,
      [chainId, ...heights],
    );
    total += t.rowCount ?? 0;
    const l = await this.pool.query(
      `UPDATE logs SET canonical=true
       WHERE chain_id=$1 AND canonical=false AND block_number IN (${plainList})`,
      [chainId, ...heights],
    );
    total += l.rowCount ?? 0;
    const candList = heights.map((_, i) => `$${i + 3}`).join(",");
    const c = await this.pool.query(
      `UPDATE token_transfer_candidates SET canonical=true, canonicalized_at=$2
       WHERE chain_id=$1 AND canonical=false AND block_number IN (${candList})`,
      [chainId, canonicalizedAt, ...heights],
    );
    total += c.rowCount ?? 0;
    return total;
  }

  async upsertTransactions(rows: TxRow[]): Promise<void> {
    if (rows.length === 0) return;
    const client = await this.pool.connect();
    try {
      for (const row of rows) {
        await client.query(
          `INSERT INTO transactions(chain_id, tx_hash, block_number, block_hash, transaction_index,
             from_address, to_address, value, status, gas_used, effective_gas_price, nonce, input,
             input_selector, canonical, first_seen_at, decoded_at, source_id)
           VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18)
           ON CONFLICT (chain_id, tx_hash) DO NOTHING`,
          [
            row.chainId,
            row.txHash.toLowerCase(),
            row.blockNumber.toString(),
            row.blockHash.toLowerCase(),
            row.transactionIndex,
            row.fromAddress,
            row.toAddress,
            row.value,
            row.status,
            row.gasUsed,
            row.effectiveGasPrice,
            row.nonce,
            row.input,
            row.inputSelector,
            row.canonical,
            row.firstSeenAt,
            row.decodedAt,
            row.sourceId,
          ],
        );
      }
    } finally {
      client.release();
    }
  }

  async getTransaction(chainId: number, txHash: string): Promise<TxRow | null> {
    const res = await this.pool.query(
      "SELECT * FROM transactions WHERE chain_id=$1 AND tx_hash=$2",
      [chainId, txHash.toLowerCase()],
    );
    const r = res.rows[0];
    if (!r) return null;
    return {
      chainId: Number(r.chain_id),
      txHash: String(r.tx_hash),
      blockNumber: toBigInt(r.block_number),
      blockHash: String(r.block_hash),
      transactionIndex: toNumber(r.transaction_index),
      fromAddress: toNullableString(r.from_address),
      toAddress: toNullableString(r.to_address),
      value: String(r.value),
      status: toNullableNumber(r.status),
      gasUsed: toNullableString(r.gas_used),
      effectiveGasPrice: toNullableString(r.effective_gas_price),
      nonce: toNullableNumber(r.nonce),
      input: String(r.input),
      inputSelector: toNullableString(r.input_selector),
      canonical: Boolean(r.canonical),
      firstSeenAt: toNumber(r.first_seen_at),
      decodedAt: toNullableNumber(r.decoded_at),
      sourceId: String(r.source_id),
    };
  }

  async upsertLogs(rows: LogRow[]): Promise<void> {
    if (rows.length === 0) return;
    const client = await this.pool.connect();
    try {
      for (const row of rows) {
        await client.query(
          `INSERT INTO logs(chain_id, block_hash, log_index, block_number, transaction_hash,
             transaction_index, address, topics, data, removed, decoded_event_type, canonical,
             first_seen_at, decoded_at, source_id)
           VALUES($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9,$10,$11,$12,$13,$14,$15)
           ON CONFLICT (chain_id, block_hash, log_index) DO NOTHING`,
          [
            row.chainId,
            row.blockHash.toLowerCase(),
            row.logIndex,
            row.blockNumber.toString(),
            row.transactionHash.toLowerCase(),
            row.transactionIndex,
            row.address.toLowerCase(),
            JSON.stringify(row.topics),
            row.data,
            row.removed,
            row.decodedEventType,
            row.canonical,
            row.firstSeenAt,
            row.decodedAt,
            row.sourceId,
          ],
        );
      }
    } finally {
      client.release();
    }
  }

  async setLogDecoded(
    chainId: number,
    blockHash: string,
    logIndex: number,
    eventType: string,
  ): Promise<void> {
    await this.pool.query(
      "UPDATE logs SET decoded_event_type=$4 WHERE chain_id=$1 AND block_hash=$2 AND log_index=$3",
      [chainId, blockHash.toLowerCase(), logIndex, eventType],
    );
  }

  async getLog(chainId: number, blockHash: string, logIndex: number): Promise<LogRow | null> {
    const res = await this.pool.query(
      "SELECT * FROM logs WHERE chain_id=$1 AND block_hash=$2 AND log_index=$3",
      [chainId, blockHash.toLowerCase(), logIndex],
    );
    const r = res.rows[0];
    if (!r) return null;
    return {
      chainId: Number(r.chain_id),
      blockNumber: toBigInt(r.block_number),
      blockHash: String(r.block_hash),
      transactionHash: String(r.transaction_hash),
      transactionIndex: toNumber(r.transaction_index),
      logIndex: toNumber(r.log_index),
      address: String(r.address),
      topics: r.topics as string[],
      data: String(r.data),
      removed: Boolean(r.removed),
      canonical: Boolean(r.canonical),
      firstSeenAt: toNumber(r.first_seen_at),
      decodedAt: toNullableNumber(r.decoded_at),
      sourceId: String(r.source_id),
      decodedEventType: toNullableString(r.decoded_event_type),
    };
  }

  async countLogsInRange(chainId: number, fromBlock: bigint, toBlock: bigint): Promise<number> {
    const res = await this.pool.query(
      "SELECT COUNT(*) AS n FROM logs WHERE chain_id=$1 AND block_number>=$2 AND block_number<=$3",
      [chainId, fromBlock.toString(), toBlock.toString()],
    );
    return toNumber(res.rows[0]?.n);
  }

  async insertCandidate(row: TransferCandidateRow): Promise<boolean> {
    const res = await this.pool.query(
      `INSERT INTO token_transfer_candidates(chain_id, block_hash, log_index, block_number,
         transaction_hash, transaction_index, token_address, emitter_kind, from_address, to_address,
         value_raw, decimals, amount, is_zero_value, is_self, token_status, canonical, source_id,
         first_seen_at, decoded_at, canonicalized_at, decoder, decoder_version)
       VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23)
       ON CONFLICT (chain_id, block_hash, log_index) DO NOTHING`,
      [
        row.chainId,
        row.blockHash.toLowerCase(),
        row.logIndex,
        row.blockNumber.toString(),
        row.transactionHash.toLowerCase(),
        row.transactionIndex,
        row.tokenAddress.toLowerCase(),
        row.emitterKind,
        row.fromAddress.toLowerCase(),
        row.toAddress.toLowerCase(),
        row.valueRaw,
        row.decimals,
        row.amount,
        row.isZeroValue,
        row.isSelf,
        row.tokenStatus,
        row.canonical,
        row.sourceId,
        row.firstSeenAt,
        row.decodedAt,
        row.canonicalizedAt,
        row.decoder,
        row.decoderVersion,
      ],
    );
    return (res.rowCount ?? 0) > 0;
  }

  async getCandidate(
    chainId: number,
    blockHash: string,
    logIndex: number,
  ): Promise<TransferCandidateRow | null> {
    const res = await this.pool.query(
      "SELECT * FROM token_transfer_candidates WHERE chain_id=$1 AND block_hash=$2 AND log_index=$3",
      [chainId, blockHash.toLowerCase(), logIndex],
    );
    const r = res.rows[0];
    if (!r) return null;
    return {
      chainId: Number(r.chain_id),
      blockNumber: toBigInt(r.block_number),
      blockHash: String(r.block_hash),
      transactionHash: String(r.transaction_hash),
      transactionIndex: toNumber(r.transaction_index),
      logIndex: toNumber(r.log_index),
      tokenAddress: String(r.token_address),
      emitterKind: r.emitter_kind as TransferCandidateRow["emitterKind"],
      fromAddress: String(r.from_address),
      toAddress: String(r.to_address),
      valueRaw: String(r.value_raw),
      decimals: toNullableNumber(r.decimals),
      amount: toNullableString(r.amount),
      isZeroValue: Boolean(r.is_zero_value),
      isSelf: Boolean(r.is_self),
      tokenStatus: r.token_status as TransferCandidateRow["tokenStatus"],
      canonical: Boolean(r.canonical),
      sourceId: String(r.source_id),
      firstSeenAt: toNumber(r.first_seen_at),
      decodedAt: toNumber(r.decoded_at),
      canonicalizedAt: toNullableNumber(r.canonicalized_at),
      decoder: String(r.decoder),
      decoderVersion: toNumber(r.decoder_version),
    };
  }

  async countCanonicalCandidates(chainId: number): Promise<number> {
    const res = await this.pool.query(
      "SELECT COUNT(*) AS n FROM token_transfer_candidates WHERE chain_id=$1 AND canonical=true",
      [chainId],
    );
    return toNumber(res.rows[0]?.n);
  }

  async getCheckpoint(chainId: number, stream: string): Promise<bigint | null> {
    const res = await this.pool.query(
      "SELECT cursor_block FROM checkpoints WHERE chain_id=$1 AND stream=$2",
      [chainId, stream],
    );
    const r = res.rows[0];
    return r ? toBigInt(r.cursor_block) : null;
  }

  async setCheckpoint(
    chainId: number,
    stream: string,
    cursorBlock: bigint,
    updatedAt: number,
  ): Promise<void> {
    await this.pool.query(
      `INSERT INTO checkpoints(chain_id, stream, cursor_block, updated_at)
       VALUES($1,$2,$3,$4)
       ON CONFLICT (chain_id, stream) DO UPDATE SET
         cursor_block=EXCLUDED.cursor_block, updated_at=EXCLUDED.updated_at`,
      [chainId, stream, cursorBlock.toString(), updatedAt],
    );
  }

  async startIngestionRun(row: IngestionRunRow): Promise<void> {
    await this.pool.query(
      `INSERT INTO ingestion_runs(run_id, kind, chain_id, from_block, to_block, status,
         progress_block, started_at, updated_at, error)
       VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) ON CONFLICT (run_id) DO NOTHING`,
      [
        row.runId,
        row.kind,
        row.chainId,
        row.fromBlock.toString(),
        row.toBlock.toString(),
        row.status,
        row.progressBlock.toString(),
        row.startedAt,
        row.updatedAt,
        row.error,
      ],
    );
  }

  async finishIngestionRun(
    runId: string,
    status: RunStatus,
    progressBlock: bigint,
    error: string | null,
  ): Promise<void> {
    await this.pool.query(
      "UPDATE ingestion_runs SET status=$2, progress_block=$3, updated_at=$4, error=$5 WHERE run_id=$1",
      [runId, status, progressBlock.toString(), Date.now(), error],
    );
  }

  async getIngestionRun(runId: string): Promise<IngestionRunRow | null> {
    const res = await this.pool.query("SELECT * FROM ingestion_runs WHERE run_id=$1", [runId]);
    const r = res.rows[0];
    if (!r) return null;
    return {
      runId: String(r.run_id),
      kind: r.kind as IngestionRunRow["kind"],
      chainId: Number(r.chain_id),
      fromBlock: toBigInt(r.from_block),
      toBlock: toBigInt(r.to_block),
      status: r.status as RunStatus,
      progressBlock: toBigInt(r.progress_block),
      startedAt: toNumber(r.started_at),
      updatedAt: toNumber(r.updated_at),
      error: toNullableString(r.error),
    };
  }

  async recordIssue(row: QualityIssueRow): Promise<void> {
    await this.pool.query(
      `INSERT INTO data_quality_issues(id, chain_id, kind, severity, block_number, tx_hash,
         log_index, detail, detected_at)
       VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9) ON CONFLICT (id) DO NOTHING`,
      [
        row.id,
        row.chainId,
        row.kind,
        row.severity,
        row.blockNumber === null ? null : row.blockNumber.toString(),
        row.txHash,
        row.logIndex,
        row.detail,
        row.detectedAt,
      ],
    );
  }

  async countIssues(chainId: number): Promise<number> {
    const res = await this.pool.query(
      "SELECT COUNT(*) AS n FROM data_quality_issues WHERE chain_id=$1",
      [chainId],
    );
    return toNumber(res.rows[0]?.n);
  }

  async close(): Promise<void> {
    await this.pool.end();
  }
}
