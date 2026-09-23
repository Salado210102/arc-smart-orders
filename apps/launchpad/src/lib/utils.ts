import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const short = (a?: string) => (a && a.length > 10 ? `${a.slice(0, 6)}…${a.slice(-4)}` : a ?? "");

export const tokenTicker = (addr: string) => `$${addr.slice(2, 6).toUpperCase()}`;

export const IPFS_GATEWAYS = [
  "https://ipfs.io/ipfs/",
  "https://dweb.link/ipfs/",
  "https://gateway.pinata.cloud/ipfs/",
  "https://cloudflare-ipfs.com/ipfs/",
];

export function ipfsUrls(uri: string): string[] {
  if (!uri) return [];
  if (uri.startsWith("ipfs://")) return IPFS_GATEWAYS.map((g) => g + uri.slice(7));
  return [uri];
}
