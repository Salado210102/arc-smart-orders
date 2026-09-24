import type { Address, BlockNumber, ChainId } from "../types/branded.ts";
import type { BlockRef } from "../types/chain.ts";
import type {
  DataSourceKind,
  SwapEvent,
  TokenLaunchEvent,
  TransferEvent,
} from "../types/data.ts";

export interface LogQuery {
  readonly chainId: ChainId;
  readonly address: Address;
  readonly fromBlock: BlockNumber;
  readonly toBlock: BlockNumber;
}

export interface DataProvider {
  readonly kind: DataSourceKind;
  latestBlock(chainId: ChainId): Promise<BlockRef>;
  getBlock(chainId: ChainId, block: BlockNumber): Promise<BlockRef | null>;
  getLogs(query: LogQuery): Promise<readonly unknown[]>;
  getSwaps(query: LogQuery): Promise<readonly SwapEvent[]>;
  getTransfers(query: LogQuery): Promise<readonly TransferEvent[]>;
  getLaunches(query: LogQuery): Promise<readonly TokenLaunchEvent[]>;
}
