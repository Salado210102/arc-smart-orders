import { test } from "node:test";
import assert from "node:assert/strict";

import { MAINNET_SEED } from "../../src/data/config.ts";
import type { DataEngineConfig } from "../../src/data/config.ts";
import { compareEventOrder, TRANSFER_TOPIC0 } from "../../src/data/decoder.ts";
import { getHealth } from "../../src/data/health.ts";
import { Ingestor } from "../../src/data/ingest.ts";
import { MemoryStore } from "../../src/data/memory-store.ts";
import { collectingLogger, Metrics } from "../../src/data/metrics.ts";
import { FixtureSource } from "../../src/data/source.ts";
import type { RawBlock, RawLog } from "../../src/data/types.ts";

const CHAIN = 5042;
const EURC = "0xbef5f6d51cb62b58e6a8f77868681825c6fe21c1";
const FROM = "0x1111111111111111111111111111111111111111";
const TO = "0x2222222222222222222222222222222222222222";

const pad = (hexNoPrefix: string) => `0x${hexNoPrefix.padStart(64, "0")}`;
const addrTopic = (addr: string) => pad(addr.slice(2).toLowerCase());
const valueTopic = (value: bigint) => pad(value.toString(16));

interface Harness {
  store: MemoryStore;
  source: FixtureSource;
  metrics: Metrics;
  config: DataEngineConfig;
  logs: Record<string, unknown>[];
  spawn: (overrides?: Partial<DataEngineConfig>) => Ingestor;
  ingestor: Ingestor;
}

function setup(overrides: Partial<DataEngineConfig> = {}): Harness {
  const store = new MemoryStore();
  const source = new FixtureSource();
  const metrics = new Metrics();
  const logs: Record<string, unknown>[] = [];
  const logger = collectingLogger((l) => logs.push(l));
  const config: DataEngineConfig = {
    chainId: CHAIN,
    rpcUrl: "http://fixture",
    databaseUrl: "",
    operationalConfirmationDepth: 0,
    finalitySource: "none",
    maxReorgDepth: 8,
    startBlock: 100n,
    pollIntervalMs: 1,
    maxRetries: 2,
    retryBaseMs: 1,
    maxBlocksPerTick: 100,
    healthPort: null,
    stream: "live",
    sourceId: "fixture",
    seed: MAINNET_SEED,
    ...overrides,
  };
  let tick = 1_000_000;
  const now = () => (tick += 1);
  let seq = 0;
  const newId = () => `id-${(seq += 1)}`;
  const spawn = (o: Partial<DataEngineConfig> = {}) =>
    new Ingestor({
      store,
      source,
      config: { ...config, ...o },
      logger,
      metrics,
      now,
      newId,
      sleep: async () => {},
    });
  return { store, source, metrics, config, logs, spawn, ingestor: spawn() };
}

function addBlock(
  source: FixtureSource,
  n: number,
  parentHash: string,
  hash: string,
  opts: { address?: string; value?: bigint; from?: string; to?: string; topic0?: string; withTx?: boolean } = {},
): RawBlock {
  const txHash = `0x${n.toString(16).padStart(4, "0")}`;
  const block: RawBlock = {
    number: BigInt(n),
    hash,
    parentHash,
    timestamp: BigInt(1_700_000_000 + n),
    transactions: opts.withTx === false
      ? []
      : [
          {
            hash: txHash,
            transactionIndex: 0,
            from: FROM,
            to: TO,
            value: 0n,
            nonce: n,
            input: "0x",
            status: null,
            gasUsed: null,
            effectiveGasPrice: null,
          },
        ],
  };
  source.addBlock(block);
  if (opts.withTx !== false) {
    const log: RawLog = {
      address: (opts.address ?? EURC).toLowerCase(),
      topics: [opts.topic0 ?? TRANSFER_TOPIC0, addrTopic(opts.from ?? FROM), addrTopic(opts.to ?? TO)],
      data: valueTopic(opts.value ?? 1_000_000n),
      blockNumber: BigInt(n),
      blockHash: hash,
      transactionHash: txHash,
      transactionIndex: 0,
      logIndex: 0,
      removed: false,
    };
    source.addLog(log);
  }
  return block;
}

function chain101to102(h: Harness): void {
  addBlock(h.source, 100, "0x0", "0x100");
  addBlock(h.source, 101, "0x100", "0x101");
  addBlock(h.source, 102, "0x101", "0x102");
  h.source.head = 102n;
}

test("ingests blocks and produces canonical candidates with provenance", async () => {
  const h = setup();
  chain101to102(h);
  await h.ingestor.runOnce();

  assert.equal(await h.store.getCheckpoint(CHAIN, "live"), 102n);
  assert.equal(await h.store.getMaxCanonicalBlockNumber(CHAIN), 102n);
  assert.equal(await h.store.countCanonicalCandidates(CHAIN), 3);

  const candidate = await h.store.getCandidate(CHAIN, "0x100", 0);
  assert.ok(candidate);
  if (!candidate) return;
  assert.equal(candidate.canonical, true);
  assert.equal(candidate.sourceId, "fixture");
  assert.equal(candidate.decoder, "erc20_transfer");
  assert.equal(candidate.decoderVersion, 1);

  const log = await h.store.getLog(CHAIN, "0x100", 0);
  assert.ok(log);
  if (!log) return;
  const tx = await h.store.getTransaction(CHAIN, log.transactionHash);
  assert.ok(tx);
  const block = await h.store.getBlockByHash(CHAIN, candidate.blockHash);
  assert.ok(block);
  assert.equal(block?.blockNumber, 100n);
});

test("four timestamps remain distinct", async () => {
  const h = setup();
  addBlock(h.source, 100, "0x0", "0x100");
  h.source.head = 100n;
  await h.ingestor.runOnce();

  const block = await h.store.getBlockByHash(CHAIN, "0x100");
  const candidate = await h.store.getCandidate(CHAIN, "0x100", 0);
  assert.ok(block && candidate);
  if (!block || !candidate) return;
  assert.equal(block.timestamp, 1_700_000_100n);
  assert.ok(block.firstSeenAt > 1_000_000);
  assert.ok(candidate.decodedAt > block.firstSeenAt);
  assert.ok(candidate.canonicalizedAt !== null && candidate.canonicalizedAt > candidate.decodedAt);
  assert.notEqual(block.firstSeenAt, candidate.decodedAt);
});

test("event ordering is deterministic (block -> tx -> log)", async () => {
  const h = setup();
  chain101to102(h);
  await h.ingestor.runOnce();
  const candidates = [...h.store.candidates.values()];
  const sorted = [...candidates].sort(compareEventOrder);
  assert.deepEqual(
    sorted.map((c) => c.blockNumber),
    [100n, 101n, 102n],
  );
});

test("A: interruption does not advance checkpoint and resumes", async () => {
  const h = setup();
  chain101to102(h);
  h.source.failBlocks.add("102");
  await assert.rejects(() => h.ingestor.runOnce());
  assert.equal(await h.store.getCheckpoint(CHAIN, "live"), 101n);
  assert.equal(await h.store.getBlockByHash(CHAIN, "0x102"), null);
  assert.equal(h.metrics.counters.providerErrors, 1);

  h.source.failBlocks.delete("102");
  await h.ingestor.runOnce();
  assert.equal(await h.store.getCheckpoint(CHAIN, "live"), 102n);
  assert.ok(await h.store.getBlockByHash(CHAIN, "0x102"));
  assert.equal(await h.store.countCanonicalCandidates(CHAIN), 3);
});

test("B: reprocessing the same block is idempotent", async () => {
  const h = setup();
  addBlock(h.source, 100, "0x0", "0x100");
  h.source.head = 100n;
  await h.ingestor.ingestBlock(100n);
  const candidates = h.store.candidates.size;
  const logs = h.store.logs.size;
  const txs = h.store.txs.size;
  const result = await h.ingestor.ingestBlock(100n);
  assert.equal(result.candidates, 0);
  assert.equal(h.store.candidates.size, candidates);
  assert.equal(h.store.logs.size, logs);
  assert.equal(h.store.txs.size, txs);
});

test("C: duplicate provider observations collapse; provenance kept", async () => {
  const h = setup();
  addBlock(h.source, 100, "0x0", "0x100");
  h.source.head = 100n;
  h.source.duplicateLogs = true;
  await h.ingestor.ingestBlock(100n);
  assert.equal(h.store.candidates.size, 1);
  assert.ok(h.metrics.counters.duplicateObservations >= 1);
  const candidate = await h.store.getCandidate(CHAIN, "0x100", 0);
  assert.equal(candidate?.sourceId, "fixture");
});

test("D: temporary provider failure retries then succeeds", async () => {
  const h = setup({ maxRetries: 3 });
  addBlock(h.source, 100, "0x0", "0x100");
  h.source.head = 100n;
  h.source.failGetBlockTimes = 2;
  await h.ingestor.runOnce();
  assert.equal(h.metrics.counters.retries, 2);
  assert.equal(h.metrics.counters.providerErrors, 0);
  assert.equal(await h.store.getCheckpoint(CHAIN, "live"), 100n);
});

test("E: post-canonical conflict is quarantined; canonical history unchanged", async () => {
  const h = setup();
  chain101to102(h);
  await h.ingestor.runOnce();
  assert.equal(await h.store.countCanonicalCandidates(CHAIN), 3);

  addBlock(h.source, 102, "0x101", "0x102b", { withTx: false });

  const result = await h.ingestor.ingestBlock(102n);
  assert.equal(result.status, "conflict");

  const canonical102 = await h.store.getCanonicalBlockAtHeight(CHAIN, 102n);
  assert.equal(canonical102?.blockHash, "0x102");
  assert.equal(canonical102?.canonical, true);
  assert.notEqual(canonical102?.status, "orphaned");

  const quarantined = await h.store.getBlockByHash(CHAIN, "0x102b");
  assert.ok(quarantined);
  assert.equal(quarantined?.canonical, false);
  assert.equal(quarantined?.status, "observed");

  assert.ok(h.store.issues.some((i) => i.kind === "provider_conflict_after_canonical"));
  assert.ok(h.metrics.counters.conflicts >= 1);
  assert.ok(h.logs.some((l) => l.msg === "provider_conflict_after_canonical"));

  const before = await h.store.getCanonicalBlockAtHeight(CHAIN, 102n);
  await h.ingestor.ingestBlock(102n);
  const after = await h.store.getCanonicalBlockAtHeight(CHAIN, 102n);
  assert.equal(after?.blockHash, "0x102");
  assert.equal(before?.blockHash, after?.blockHash);
  assert.equal(await h.store.countCanonicalCandidates(CHAIN), 3);
  const candidate = await h.store.getCandidate(CHAIN, "0x102", 0);
  assert.equal(candidate?.canonical, true);

  // This test does not demonstrate that Arc reorganizes. It demonstrates that the
  // ingestion system fails safely if a provider supplies conflicting observations.
});

test("pre-canonical conflicting observations are quarantined together", async () => {
  const h = setup();
  await h.store.upsertBlock({
    chainId: CHAIN,
    blockNumber: 200n,
    blockHash: "0xaaa",
    parentHash: "0x199",
    timestamp: 1n,
    firstSeenAt: 1,
    decodedAt: null,
    canonicalizedAt: null,
    status: "observed",
    canonical: false,
    sourceId: "fixture",
    txCount: 0,
    logCount: 0,
  });
  h.source.addBlock({ number: 200n, hash: "0xbbb", parentHash: "0x199", timestamp: 2n, transactions: [] });
  h.source.head = 200n;

  const result = await h.ingestor.ingestBlock(200n);
  assert.equal(result.status, "ambiguous");
  assert.equal(await h.store.getCanonicalBlockAtHeight(CHAIN, 200n), null);
  assert.equal(await h.store.getCheckpoint(CHAIN, "live"), null);
  assert.ok(h.store.issues.some((i) => i.kind === "provider_conflict_before_canonical"));
  assert.ok(await h.store.getBlockByHash(CHAIN, "0xaaa"));
  assert.ok(await h.store.getBlockByHash(CHAIN, "0xbbb"));

  // This test does not demonstrate that Arc reorganizes. It demonstrates that the
  // ingestion system fails safely if a provider supplies conflicting observations.
});

test("F: unknown event is kept raw and not fabricated", async () => {
  const h = setup();
  addBlock(h.source, 100, "0x0", "0x100", { topic0: pad("dead") });
  h.source.head = 100n;
  await h.ingestor.ingestBlock(100n);
  assert.ok(await h.store.getLog(CHAIN, "0x100", 0));
  assert.equal(await h.store.getCandidate(CHAIN, "0x100", 0), null);
  assert.equal(h.metrics.counters.decodeFailures, 1);
  assert.ok(h.store.issues.some((i) => i.kind === "decode_failure"));
});

test("G: database failure does not advance checkpoint and recovers", async () => {
  const h = setup();
  addBlock(h.source, 100, "0x0", "0x100");
  h.source.head = 100n;
  h.store.injectFailure("upsertBlock", 1);
  await assert.rejects(() => h.ingestor.runOnce());
  assert.equal(await h.store.getCheckpoint(CHAIN, "live"), null);
  await h.ingestor.runOnce();
  assert.equal(await h.store.getCheckpoint(CHAIN, "live"), 100n);
});

test("H: restart from checkpoint resumes without duplicates or gaps", async () => {
  const h = setup();
  chain101to102(h);
  await h.ingestor.runOnce();
  assert.equal(await h.store.getCheckpoint(CHAIN, "live"), 102n);
  const before = h.store.candidates.size;

  addBlock(h.source, 103, "0x102", "0x103");
  addBlock(h.source, 104, "0x103", "0x104");
  h.source.head = 104n;

  const restarted = h.spawn();
  await restarted.runOnce();
  assert.equal(await h.store.getCheckpoint(CHAIN, "live"), 104n);
  assert.equal(h.store.candidates.size, before + 2);
  for (const n of [100n, 101n, 102n, 103n, 104n]) {
    assert.ok(await h.store.getCanonicalBlockAtHeight(CHAIN, n));
  }
});

test("decoder is reproducible from raw", async () => {
  const h = setup();
  addBlock(h.source, 100, "0x0", "0x100");
  h.source.head = 100n;
  await h.ingestor.ingestBlock(100n);
  const a = await h.store.getCandidate(CHAIN, "0x100", 0);
  const raw = await h.store.getLog(CHAIN, "0x100", 0);
  assert.ok(a && raw);
  if (!a || !raw) return;
  const { decodeErc20TransferV1 } = await import("../../src/data/decoder.ts");
  const again = decodeErc20TransferV1({
    chainId: CHAIN,
    log: raw,
    sourceId: "fixture",
    firstSeenAt: a.firstSeenAt,
    decodedAt: a.decodedAt,
    emitterKind: a.emitterKind,
    tokenStatus: a.tokenStatus,
    decimals: a.decimals,
  });
  assert.equal(again.ok, true);
  if (!again.ok) return;
  assert.deepEqual(again.candidate, { ...a, canonical: false, canonicalizedAt: null });
  assert.equal(a.canonical, true);
});

test("health snapshot exposes checkpoint, lag and counters", async () => {
  const h = setup();
  addBlock(h.source, 100, "0x0", "0x100");
  h.source.head = 100n;
  await h.ingestor.runOnce();
  const report = await getHealth(h.store, h.config, h.metrics, h.ingestor.head);
  assert.equal(report.ok, true);
  assert.equal(report.checkpoint, "100");
  assert.equal(report.lag, "0");
  assert.equal(report.counters.blocksProcessed, 1);
});
