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
export type WalletInfo = { name: string; icon?: string; rdns?: string; provider: Eip1193 };

let evm: Eip1193 | null = null;

/** Discover injected wallets via EIP-6963 (falls back to window.ethereum). */
async function discoverProviders(): Promise<{ info?: { name?: string; icon?: string; rdns?: string }; provider: Eip1193 }[]> {
  const announced: { info?: { name?: string; icon?: string; rdns?: string }; provider: Eip1193 }[] = [];
  const on = (e: Event) => announced.push((e as CustomEvent).detail);
  window.addEventListener("eip6963:announceProvider", on as EventListener);
  window.dispatchEvent(new Event("eip6963:requestProvider"));
  await new Promise((r) => setTimeout(r, 300));
  window.removeEventListener("eip6963:announceProvider", on as EventListener);
  if (announced.length) return announced;

  const inj = (window as unknown as { ethereum?: Eip1193 & { isMetaMask?: boolean } }).ethereum;
  return inj ? [{ info: { name: inj.isMetaMask ? "MetaMask" : "Injected", rdns: "injected" }, provider: inj }] : [];
}

/** All wallets the user can choose from. */
export async function listWallets(): Promise<WalletInfo[]> {
  const ds = await discoverProviders();
  return ds.map((d) => ({
    name: d.info?.name ?? "Wallet",
    icon: d.info?.icon,
    rdns: d.info?.rdns,
    provider: d.provider,
  }));
}

/** Connect a specific wallet (from `listWallets`) and switch/add the Arc chain. */
export async function connectProvider(provider: Eip1193): Promise<`0x${string}`> {
  evm = provider;
  const accounts = (await provider.request({ method: "eth_requestAccounts" })) as `0x${string}`[];
  const addr = accounts[0];
  try {
    await provider.request({ method: "wallet_switchEthereumChain", params: [{ chainId: hexId }] });
  } catch {
    await provider.request({
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

/** Disconnect: ask the wallet to revoke this dApp's account permission (best-effort) and forget it. */
export async function disconnect(): Promise<void> {
  try {
    await evm?.request({ method: "wallet_revokePermissions", params: [{ eth_accounts: {} }] });
  } catch {
    /* ignore — not all wallets support it */
  }
  evm = null;
}

export const EXPLORER = "https://explorer.arc.io";
