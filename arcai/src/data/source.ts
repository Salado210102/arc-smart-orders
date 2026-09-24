import { createPublicClient, defineChain, http } from "viem";
import type { PublicClient } from "viem";
import type { RawBlock, RawLog } from "./types.ts";

export interface BlockSource {
  readonly id: string;
  latestBlockNumber(): Promise<bigint>;
  getBlock(blockNumber: bigint): Promise<RawBlock | null>;
  getLogs(fromBlock: bigint, toBlock: bigint): Promise<RawLog[]>;
}

export interface HttpRpcSourceOptions {
  rpcUrl: string;
  chainId: number;
  seedAddresses: string[];
}

export class HttpRpcSource implements BlockSource {
  readonly id: string;
  private readonly client: PublicClient;
  private readonly addresses: `0x${string}`[];

  constructor(options: HttpRpcSourceOptions) {
    this.id = "arc-rpc-primary";
    const chain = defineChain({
      id: options.chainId,
      name: "Arc",
      nativeCurrency: { name: "USDC", symbol: "USDC", decimals: 18 },
      rpcUrls: { default: { http: [options.rpcUrl] } },
    });
    this.client = createPublicClient({ chain, transport: http(options.rpcUrl) });
    this.addresses = options.seedAddresses.map((a) => a as `0x${string}`);
  }

  async latestBlockNumber(): Promise<bigint> {
    return this.client.getBlockNumber();
  }

  async getBlock(blockNumber: bigint): Promise<RawBlock | null> {
    const raw = await this.client.getBlock({ blockNumber, includeTransactions: true });
    if (raw.number === null || raw.hash === null) return null;
    const txs = (raw.transactions as unknown[]).map((t) => {
      const tx = t as {
        hash: string;
        transactionIndex: number | null;
        from: string;
        to: string | null;
        value: bigint;
        nonce: number;
        input: string;
      };
      return {
        hash: tx.hash,
        transactionIndex: tx.transactionIndex ?? 0,
        from: tx.from,
        to: tx.to,
        value: tx.value,
        nonce: tx.nonce,
        input: tx.input,
        status: null,
        gasUsed: null,
        effectiveGasPrice: null,
      };
    });
    return {
      number: raw.number,
      hash: raw.hash,
      parentHash: raw.parentHash,
      timestamp: raw.timestamp,
      transactions: txs,
    };
  }

  async getLogs(fromBlock: bigint, toBlock: bigint): Promise<RawLog[]> {
    const logs = await this.client.getLogs({
      address: this.addresses,
      fromBlock,
      toBlock,
    });
    const out: RawLog[] = [];
    for (const log of logs) {
      if (log.blockNumber === null || log.blockHash === null || log.transactionHash === null) continue;
      out.push({
        address: log.address.toLowerCase(),
        topics: [...log.topics],
        data: log.data,
        blockNumber: log.blockNumber,
        blockHash: log.blockHash,
        transactionHash: log.transactionHash,
        transactionIndex: log.transactionIndex ?? 0,
        logIndex: log.logIndex ?? 0,
        removed: log.removed ?? false,
      });
    }
    return out;
  }
}

export class FixtureSource implements BlockSource {
  readonly id = "fixture";
  readonly blocks = new Map<string, RawBlock>();
  readonly logs: RawLog[] = [];
  readonly failBlocks = new Set<string>();
  head = 0n;
  failGetBlockTimes = 0;
  failGetLogsTimes = 0;
  failLatestTimes = 0;
  duplicateLogs = false;

  addBlock(block: RawBlock): void {
    this.blocks.set(block.number.toString(), block);
    if (block.number > this.head) this.head = block.number;
  }

  replaceBlock(block: RawBlock): void {
    this.blocks.set(block.number.toString(), block);
  }

  addLog(log: RawLog): void {
    this.logs.push(log);
  }

  async latestBlockNumber(): Promise<bigint> {
    if (this.failLatestTimes > 0) {
      this.failLatestTimes -= 1;
      throw new Error("injected_failure:latestBlockNumber");
    }
    return this.head;
  }

  async getBlock(blockNumber: bigint): Promise<RawBlock | null> {
    if (this.failGetBlockTimes > 0) {
      this.failGetBlockTimes -= 1;
      throw new Error("injected_failure:getBlock");
    }
    if (this.failBlocks.has(blockNumber.toString())) {
      throw new Error(`injected_failure:getBlock:${blockNumber}`);
    }
    return this.blocks.get(blockNumber.toString()) ?? null;
  }

  async getLogs(fromBlock: bigint, toBlock: bigint): Promise<RawLog[]> {
    if (this.failGetLogsTimes > 0) {
      this.failGetLogsTimes -= 1;
      throw new Error("injected_failure:getLogs");
    }
    const base = this.logs.filter(
      (l) => l.blockNumber >= fromBlock && l.blockNumber <= toBlock,
    );
    return this.duplicateLogs ? [...base, ...base] : base;
  }
}
