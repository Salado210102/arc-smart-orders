import { test } from "node:test";
import assert from "node:assert/strict";

import { newDb } from "pg-mem";
import { PgStore } from "../../src/data/pg-store.ts";
import type { PgPoolLike } from "../../src/data/pg-store.ts";
import type { BlockRow, TransferCandidateRow, TxRow } from "../../src/data/types.ts";

const CHAIN = 5042;

function emulatedStore(): PgStore {
  const db = newDb();
  const adapter = db.adapters.createPg();
  return new PgStore("pg-mem", () => new adapter.Pool() as unknown as PgPoolLike);
}

function blockRow(hash: string, n: number, parent: string): BlockRow {
  return {
    chainId: CHAIN,
    blockNumber: BigInt(n),
    blockHash: hash,
    parentHash: parent,
    timestamp: BigInt(1_700_000_000 + n),
    firstSeenAt: 1000 + n,
    decodedAt: null,
    canonicalizedAt: null,
    status: "observed",
    canonical: false,
    sourceId: "pg-mem",
    txCount: 0,
    logCount: 0,
  };
}

function candidateRow(blockHash: string, n: number): TransferCandidateRow {
  return {
    chainId: CHAIN,
    blockNumber: BigInt(n),
    blockHash,
    transactionHash: `0xtx${n}`,
    transactionIndex: 0,
    logIndex: 0,
    tokenAddress: "0xbef5f6d51cb62b58e6a8f77868681825c6fe21c1",
    emitterKind: "erc20",
    fromAddress: "0x1111111111111111111111111111111111111111",
    toAddress: "0x2222222222222222222222222222222222222222",
    valueRaw: "1000000",
    decimals: 6,
    amount: "1",
    isZeroValue: false,
    isSelf: false,
    tokenStatus: "registered",
    canonical: false,
    sourceId: "pg-mem",
    firstSeenAt: 1000 + n,
    decodedAt: 2000 + n,
    canonicalizedAt: null,
    decoder: "erc20_transfer",
    decoderVersion: 1,
  };
}

test("PgStore migrate + idempotent block/transaction writes (emulated Postgres)", async () => {
  const store = emulatedStore();
  await store.migrate();

  await store.upsertBlock(blockRow("0x100", 100, "0x0"));
  await store.upsertBlock(blockRow("0x100", 100, "0x0"));
  const observed = await store.getObservedBlocksAtHeight(CHAIN, 100n);
  assert.equal(observed.length, 1);

  const tx: TxRow = {
    chainId: CHAIN,
    txHash: "0xabc",
    blockNumber: 100n,
    blockHash: "0x100",
    transactionIndex: 0,
    fromAddress: null,
    toAddress: null,
    value: "0",
    status: null,
    gasUsed: null,
    effectiveGasPrice: null,
    nonce: 0,
    input: "0x",
    inputSelector: null,
    canonical: false,
    firstSeenAt: 1,
    decodedAt: null,
    sourceId: "pg-mem",
  };
  await store.upsertTransactions([tx]);
  await store.upsertTransactions([{ ...tx, blockHash: "0x999", blockNumber: 999n }]);
  const stored = await store.getTransaction(CHAIN, "0xabc");
  assert.equal(stored?.blockHash, "0x100");
  assert.equal(stored?.blockNumber, 100n);

  await store.close();
});

test("PgStore confirms observed block and derived candidate (emulated Postgres)", async () => {
  const store = emulatedStore();
  await store.migrate();
  await store.upsertBlock(blockRow("0x100", 100, "0x0"));
  await store.insertCandidate(candidateRow("0x100", 100));
  await store.confirmObservedUpTo(CHAIN, 100n, "confirmed", 5000);

  const canonical = await store.getCanonicalBlockAtHeight(CHAIN, 100n);
  assert.equal(canonical?.blockHash, "0x100");
  assert.equal(canonical?.canonical, true);
  assert.equal(await store.countCanonicalCandidates(CHAIN), 1);
  await store.close();
});

test("PgStore does not confirm a conflicting observation at a canonical height (emulated Postgres)", async () => {
  const store = emulatedStore();
  await store.migrate();
  await store.upsertBlock(blockRow("0x100", 100, "0x0"));
  await store.confirmObservedUpTo(CHAIN, 100n, "confirmed", 5000);

  await store.upsertBlock(blockRow("0x100b", 100, "0x0"));
  await store.confirmObservedUpTo(CHAIN, 100n, "confirmed", 6000);

  const canonical = await store.getCanonicalBlockAtHeight(CHAIN, 100n);
  assert.equal(canonical?.blockHash, "0x100");
  const observed = await store.getObservedBlocksAtHeight(CHAIN, 100n);
  assert.equal(observed.length, 1);
  assert.equal(observed[0].blockHash, "0x100b");
  assert.equal(observed[0].canonical, false);
  await store.close();
});

test("PgStore records and counts issues (emulated Postgres)", async () => {
  const store = emulatedStore();
  await store.migrate();
  await store.recordIssue({
    id: "issue-1",
    chainId: CHAIN,
    kind: "provider_conflict_after_canonical",
    severity: "critical",
    blockNumber: 100n,
    txHash: null,
    logIndex: null,
    detail: "conflict",
    detectedAt: 1,
  });
  await store.recordIssue({
    id: "issue-1",
    chainId: CHAIN,
    kind: "provider_conflict_after_canonical",
    severity: "critical",
    blockNumber: 100n,
    txHash: null,
    logIndex: null,
    detail: "conflict",
    detectedAt: 1,
  });
  assert.equal(await store.countIssues(CHAIN), 1);
  await store.close();
});

const realUrl = process.env.ARC_AI_TEST_DATABASE_URL;

test(
  "PgStore against a real PostgreSQL (set ARC_AI_TEST_DATABASE_URL to run)",
  { skip: realUrl === undefined || realUrl === "" },
  async () => {
    const store = new PgStore(realUrl as string);
    await store.migrate();
    const hash = `0x${Date.now().toString(16)}`;
    await store.upsertBlock(blockRow(hash, 900000, "0x0"));
    const observed = await store.getObservedBlocksAtHeight(CHAIN, 900000n);
    assert.ok(observed.some((b) => b.blockHash === hash));
    await store.close();
  },
);
