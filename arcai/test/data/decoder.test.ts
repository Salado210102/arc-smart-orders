import { test } from "node:test";
import assert from "node:assert/strict";

import {
  compareEventOrder,
  decodeErc20TransferV1,
  formatUnits,
  TRANSFER_TOPIC0,
} from "../../src/data/decoder.ts";
import type { RawLog } from "../../src/data/types.ts";

const pad = (hexNoPrefix: string) => `0x${hexNoPrefix.padStart(64, "0")}`;
const addrTopic = (addr: string) => pad(addr.slice(2).toLowerCase());
const valueTopic = (value: bigint) => pad(value.toString(16));

const FROM = "0x1111111111111111111111111111111111111111";
const TO = "0x2222222222222222222222222222222222222222";
const TOKEN = "0x89b50855aa3be2f677cd6303cec089b5f319d72a";

function log(overrides: Partial<RawLog> = {}): RawLog {
  return {
    address: TOKEN,
    topics: [TRANSFER_TOPIC0, addrTopic(FROM), addrTopic(TO)],
    data: valueTopic(1_000_000n),
    blockNumber: 100n,
    blockHash: "0xaaa",
    transactionHash: "0xbbb",
    transactionIndex: 0,
    logIndex: 0,
    removed: false,
    ...overrides,
  };
}

const input = (l: RawLog) => ({
  chainId: 5042,
  log: l,
  sourceId: "fixture",
  firstSeenAt: 1000,
  decodedAt: 2000,
  emitterKind: "erc20" as const,
  tokenStatus: "registered" as const,
  decimals: 6,
});

test("decodes a well-formed ERC-20 Transfer into a candidate", () => {
  const res = decodeErc20TransferV1(input(log()));
  assert.equal(res.ok, true);
  if (!res.ok) return;
  assert.equal(res.candidate.fromAddress, FROM);
  assert.equal(res.candidate.toAddress, TO);
  assert.equal(res.candidate.tokenAddress, TOKEN);
  assert.equal(res.candidate.valueRaw, "1000000");
  assert.equal(res.candidate.amount, "1");
  assert.equal(res.candidate.decimals, 6);
  assert.equal(res.candidate.emitterKind, "erc20");
  assert.equal(res.candidate.decoder, "erc20_transfer");
  assert.equal(res.candidate.decoderVersion, 1);
  assert.equal(res.candidate.canonical, false);
});

test("keeps decimals and amount null when decimals are unknown", () => {
  const res = decodeErc20TransferV1({ ...input(log()), decimals: null });
  assert.equal(res.ok, true);
  if (!res.ok) return;
  assert.equal(res.candidate.decimals, null);
  assert.equal(res.candidate.amount, null);
});

test("flags zero-value and self transfers without dropping them", () => {
  const zero = decodeErc20TransferV1(input(log({ data: valueTopic(0n) })));
  assert.equal(zero.ok, true);
  if (zero.ok) assert.equal(zero.candidate.isZeroValue, true);
  const self = decodeErc20TransferV1(
    input(log({ topics: [TRANSFER_TOPIC0, addrTopic(FROM), addrTopic(FROM)] })),
  );
  assert.equal(self.ok, true);
  if (self.ok) assert.equal(self.candidate.isSelf, true);
});

test("propagates native-system emitter kind", () => {
  const res = decodeErc20TransferV1({
    ...input(log({ address: "0xfffffffffffffffffffffffffffffffffffffffe" })),
    emitterKind: "native-system",
    decimals: 18,
  });
  assert.equal(res.ok, true);
  if (res.ok) assert.equal(res.candidate.emitterKind, "native-system");
});

test("rejects malformed topics length", () => {
  const res = decodeErc20TransferV1(input(log({ topics: [TRANSFER_TOPIC0, addrTopic(FROM)] })));
  assert.equal(res.ok, false);
  if (!res.ok) assert.match(res.error, /bad_topics_length/);
});

test("rejects unknown topic0", () => {
  const res = decodeErc20TransferV1(
    input(log({ topics: [pad("dead"), addrTopic(FROM), addrTopic(TO)] })),
  );
  assert.equal(res.ok, false);
  if (!res.ok) assert.match(res.error, /unknown_topic0/);
});

test("rejects malformed data length", () => {
  const res = decodeErc20TransferV1(input(log({ data: "0x00" })));
  assert.equal(res.ok, false);
  if (!res.ok) assert.match(res.error, /bad_data_length/);
});

test("formatUnits keeps bigint precision", () => {
  assert.equal(formatUnits(1_000_000n, 6), "1");
  assert.equal(formatUnits(1_234_567n, 6), "1.234567");
  assert.equal(formatUnits(1n, 8), "0.00000001");
  assert.equal(formatUnits(42n, 0), "42");
});

test("event ordering is block -> tx -> log", () => {
  const items = [
    { blockNumber: 2n, transactionIndex: 0, logIndex: 0 },
    { blockNumber: 1n, transactionIndex: 5, logIndex: 9 },
    { blockNumber: 2n, transactionIndex: 0, logIndex: 1 },
    { blockNumber: 1n, transactionIndex: 5, logIndex: 2 },
  ];
  const sorted = [...items].sort(compareEventOrder);
  assert.deepEqual(
    sorted.map((i) => [i.blockNumber.toString(), i.transactionIndex, i.logIndex]),
    [
      ["1", 5, 2],
      ["1", 5, 9],
      ["2", 0, 0],
      ["2", 0, 1],
    ],
  );
});
