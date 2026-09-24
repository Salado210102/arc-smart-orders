import type {
  Address,
  BlockNumber,
  ChainId,
  TxHash,
  UnixMs,
} from "./branded.ts";
import type { BlockRef } from "./chain.ts";
import type { TokenRef } from "./money.ts";

export type DataSourceKind = "rpc" | "websocket" | "indexer" | "third-party";

export interface SwapEvent {
  readonly chainId: ChainId;
  readonly tx: TxHash;
  readonly block: BlockRef;
  readonly pool: Address;
  readonly sender: Address;
  readonly tokenIn: TokenRef;
  readonly amountIn: bigint;
  readonly tokenOut: TokenRef;
  readonly amountOut: bigint;
}

export interface TransferEvent {
  readonly chainId: ChainId;
  readonly tx: TxHash;
  readonly block: BlockRef;
  readonly token: TokenRef;
  readonly from: Address;
  readonly to: Address;
  readonly amount: bigint;
}

export interface TokenLaunchEvent {
  readonly chainId: ChainId;
  readonly tx: TxHash;
  readonly block: BlockRef;
  readonly token: TokenRef;
  readonly deployer: Address;
  readonly launchpad: Address;
}

export interface WalletRef {
  readonly chainId: ChainId;
  readonly address: Address;
  readonly firstSeenBlock: BlockNumber | null;
  readonly firstSeenAt: UnixMs | null;
}
