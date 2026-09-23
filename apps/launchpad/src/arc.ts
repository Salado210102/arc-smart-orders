import {
  defineChain,
  createPublicClient,
  http,
  createWalletClient,
  custom,
  type WalletClient,
} from "viem";

export const arcTestnet = defineChain({
  id: 5042002,
  name: "Arc Testnet",
  nativeCurrency: { name: "USDC", symbol: "USDC", decimals: 18 },
  rpcUrls: { default: { http: ["https://rpc.testnet.arc.io"] } },
  blockExplorers: { default: { name: "Arc Explorer", url: "https://explorer.testnet.arc.io" } },
});

export const publicClient = createPublicClient({ chain: arcTestnet, transport: http() });

const hexId = `0x${arcTestnet.id.toString(16)}`;

export async function connect(): Promise<`0x${string}`> {
  const eth = (window as unknown as { ethereum?: any }).ethereum;
  if (!eth) throw new Error("No EVM wallet detected (install MetaMask).");
  const [addr] = (await eth.request({ method: "eth_requestAccounts" })) as `0x${string}`[];
  try {
    await eth.request({ method: "wallet_switchEthereumChain", params: [{ chainId: hexId }] });
  } catch {
    await eth.request({
      method: "wallet_addEthereumChain",
      params: [
        {
          chainId: hexId,
          chainName: "Arc Testnet",
          nativeCurrency: { name: "USDC", symbol: "USDC", decimals: 18 },
          rpcUrls: ["https://rpc.testnet.arc.io"],
          blockExplorerUrls: ["https://explorer.testnet.arc.io"],
        },
      ],
    });
  }
  return addr;
}

export function walletClient(): WalletClient {
  return createWalletClient({
    chain: arcTestnet,
    transport: custom((window as unknown as { ethereum: any }).ethereum),
  });
}

export const EXPLORER = "https://explorer.testnet.arc.io";
