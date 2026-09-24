import type {
  Address,
  BlockHash,
  BlockNumber,
  ChainId,
  TxHash,
  UnixMs,
} from "./branded.ts";

export type NetworkName = "arc-mainnet" | "arc-testnet";

export interface ChainRef {
  readonly name: NetworkName;
  readonly chainId: ChainId;
}

export interface BlockRef {
  readonly chainId: ChainId;
  readonly number: BlockNumber;
  readonly hash: BlockHash;
  readonly timestamp: UnixMs;
}

export interface TxRef {
  readonly chainId: ChainId;
  readonly hash: TxHash;
  readonly block: BlockRef | null;
}

export interface ContractRef {
  readonly chainId: ChainId;
  readonly address: Address;
  readonly label: string | null;
}
