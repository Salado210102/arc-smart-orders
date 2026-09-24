import type { ChainId } from "../types/branded.ts";
import type { NetworkName } from "../types/chain.ts";

export interface ArcNetworkConfig {
  readonly name: NetworkName;
  readonly chainId: ChainId;
  readonly rpcUrl: string;
  readonly wsUrl: string | null;
  readonly explorerUrl: string;
  readonly nativeDecimals: number;
}

export const ARC_MAINNET: ArcNetworkConfig = {
  name: "arc-mainnet",
  chainId: 5042 as ChainId,
  rpcUrl: "https://rpc.mainnet.arc.io",
  wsUrl: null,
  explorerUrl: "https://explorer.arc.io",
  nativeDecimals: 18,
};

export const ARC_TESTNET: ArcNetworkConfig = {
  name: "arc-testnet",
  chainId: 5042002 as ChainId,
  rpcUrl: "https://rpc.testnet.arc.io",
  wsUrl: "wss://rpc.testnet.arc.io",
  explorerUrl: "https://explorer.testnet.arc.io",
  nativeDecimals: 18,
};
