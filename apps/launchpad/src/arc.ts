import {
  defineChain,
  createPublicClient,
  http,
  createWalletClient,
  custom,
  type WalletClient,
} from "viem";

export const arc = defineChain({
  id: 5042,
  name: "Arc Mainnet",
  nativeCurrency: { name: "USDC", symbol: "USDC", decimals: 18 },
  rpcUrls: { default: { http: ["https://rpc.mainnet.arc.io"] } },
  blockExplorers: { default: { name: "Arc Explorer", url: "https://explorer.arc.io" } },
});

export const publicClient = createPublicClient({ chain: arc, transport: http() });

const hexId = `0x${arc.id.toString(16)}`;

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
          chainName: "Arc Mainnet",
          nativeCurrency: { name: "USDC", symbol: "USDC", decimals: 18 },
          rpcUrls: ["https://rpc.mainnet.arc.io"],
          blockExplorerUrls: ["https://explorer.arc.io"],
        },
      ],
    });
  }
  return addr;
}

export function walletClient(): WalletClient {
  return createWalletClient({
    chain: arc,
    transport: custom((window as unknown as { ethereum: any }).ethereum),
  });
}

export const EXPLORER = "https://explorer.arc.io";
