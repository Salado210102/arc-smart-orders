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

type Eip1193 = { request: (a: { method: string; params?: unknown[] }) => Promise<unknown> };

/** The EIP-1193 provider chosen for this session (prefers MetaMask via EIP-6963). */
let evm: Eip1193 | null = null;

/** Discover injected wallets (EIP-6963) and prefer MetaMask over Phantom/others. */
async function discover(): Promise<Eip1193> {
  const announced: { info?: { name?: string; rdns?: string }; provider: Eip1193 }[] = [];
  const on = (e: Event) => announced.push((e as CustomEvent).detail);
  window.addEventListener("eip6963:announceProvider", on as EventListener);
  window.dispatchEvent(new Event("eip6963:requestProvider"));
  await new Promise((r) => setTimeout(r, 250));
  window.removeEventListener("eip6963:announceProvider", on as EventListener);

  const isMetaMask = (d: { info?: { name?: string; rdns?: string } }) =>
    (d.info?.name ?? "").toLowerCase().includes("metamask") || (d.info?.rdns ?? "").includes("metamask");
  const chosen = announced.find(isMetaMask) ?? announced[0];
  const fallback = (window as unknown as { ethereum?: Eip1193 }).ethereum;
  const provider = chosen?.provider ?? fallback;
  if (!provider) throw new Error("No EVM wallet detected (install MetaMask).");
  return provider;
}

export async function connect(): Promise<`0x${string}`> {
  evm = await discover();
  const accounts = (await evm.request({ method: "eth_requestAccounts" })) as `0x${string}`[];
  const addr = accounts[0];
  try {
    await evm.request({ method: "wallet_switchEthereumChain", params: [{ chainId: hexId }] });
  } catch {
    await evm.request({
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
  const provider = evm ?? (window as unknown as { ethereum: Eip1193 }).ethereum;
  return createWalletClient({ chain: arc, transport: custom(provider as never) });
}

export const EXPLORER = "https://explorer.arc.io";
