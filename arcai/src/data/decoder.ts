import type { EmitterKind, RawLog, TokenStatus, TransferCandidateRow } from "./types.ts";

export const TRANSFER_TOPIC0 =
  "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef";
export const ERC20_TRANSFER_DECODER = "erc20_transfer";
export const ERC20_TRANSFER_DECODER_VERSION = 1;

export interface DecodeInput {
  chainId: number;
  log: RawLog;
  sourceId: string;
  firstSeenAt: number;
  decodedAt: number;
  emitterKind: EmitterKind;
  tokenStatus: TokenStatus;
  decimals: number | null;
}

export type DecodeResult =
  | { ok: true; candidate: TransferCandidateRow }
  | { ok: false; error: string };

export function formatUnits(value: bigint, decimals: number): string {
  if (decimals === 0) return value.toString();
  const base = 10n ** BigInt(decimals);
  const whole = value / base;
  const frac = value % base;
  if (frac === 0n) return whole.toString();
  const fracStr = frac.toString().padStart(decimals, "0").replace(/0+$/, "");
  return `${whole}.${fracStr}`;
}

const topicToAddress = (topic: string): string =>
  `0x${topic.slice(topic.length - 40).toLowerCase()}`;

export function decodeErc20TransferV1(input: DecodeInput): DecodeResult {
  const { log } = input;
  if (log.topics.length !== 3) {
    return { ok: false, error: `bad_topics_length:${log.topics.length}` };
  }
  if (log.topics[0].toLowerCase() !== TRANSFER_TOPIC0) {
    return { ok: false, error: `unknown_topic0:${log.topics[0]}` };
  }
  if (log.data.length !== 66 || !/^0x[0-9a-fA-F]{64}$/.test(log.data)) {
    return { ok: false, error: `bad_data_length:${log.data.length}` };
  }
  const fromAddress = topicToAddress(log.topics[1]);
  const toAddress = topicToAddress(log.topics[2]);
  const valueRaw = BigInt(log.data);
  const isZeroValue = valueRaw === 0n;
  const isSelf = fromAddress === toAddress;
  const amount = input.decimals === null ? null : formatUnits(valueRaw, input.decimals);
  return {
    ok: true,
    candidate: {
      chainId: input.chainId,
      blockNumber: log.blockNumber,
      blockHash: log.blockHash.toLowerCase(),
      transactionHash: log.transactionHash.toLowerCase(),
      transactionIndex: log.transactionIndex,
      logIndex: log.logIndex,
      tokenAddress: log.address.toLowerCase(),
      emitterKind: input.emitterKind,
      fromAddress,
      toAddress,
      valueRaw: valueRaw.toString(),
      decimals: input.decimals,
      amount,
      isZeroValue,
      isSelf,
      tokenStatus: input.tokenStatus,
      canonical: false,
      sourceId: input.sourceId,
      firstSeenAt: input.firstSeenAt,
      decodedAt: input.decodedAt,
      canonicalizedAt: null,
      decoder: ERC20_TRANSFER_DECODER,
      decoderVersion: ERC20_TRANSFER_DECODER_VERSION,
    },
  };
}

export function compareEventOrder(
  a: { blockNumber: bigint; transactionIndex: number; logIndex: number },
  b: { blockNumber: bigint; transactionIndex: number; logIndex: number },
): number {
  if (a.blockNumber !== b.blockNumber) return a.blockNumber < b.blockNumber ? -1 : 1;
  if (a.transactionIndex !== b.transactionIndex) return a.transactionIndex - b.transactionIndex;
  return a.logIndex - b.logIndex;
}
