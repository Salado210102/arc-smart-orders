// Smart-order helpers for the launchpad UI: EIP-712 Permit2 signing + keeper API client.
//
// Two networks:
//   - mainnet (5042)   : keeper runs DRY-RUN (no FX venue) -> orders stay PENDING (Beta).
//   - testnet (5042002): keeper fills live on-chain against MockStableRouter (Live fills).
// Keeper API base is configurable at build time via VITE_KEEPER_API / VITE_KEEPER_TESTNET_API.
import type { Address, Hex, WalletClient } from "viem";
import { ADDR } from "../contracts";

export const PERMIT2 = "0x000000000022D473030F116dDEE9F6B43aC78BA3" as const;
export const USDC_ADDR = ADDR.usdc as Address; // same on mainnet + testnet

const _env = (import.meta as unknown as { env?: Record<string, string | undefined> }).env ?? {};

export type Network = "mainnet" | "testnet";

export const NETWORKS = {
  mainnet: {
    key: "mainnet" as const,
    chainId: 5042,
    label: "Arc Mainnet",
    executor: "0x9b3a990d1a31Ff5E01ddB8702e10F2529811FDb7" as Address,
    eurc: "0xbEf5f6d51CB62b58e6A8f77868681825C6fe21c1" as Address,
    keeperApi: (_env.VITE_KEEPER_API ?? "http://127.0.0.1:8788").replace(/\/$/, ""),
    explorer: "https://explorer.arc.io",
    mode: "Live fills" as const,
  },
  testnet: {
    key: "testnet" as const,
    chainId: 5042002,
    label: "Arc Testnet",
    executor: "0xB19F1193BcC50c2aC0fdD9f1a28F95f7493f6Ee3" as Address,
    eurc: "0x89B50855Aa3bE2F677cD6303Cec089B5F319D72a" as Address,
    keeperApi: (_env.VITE_KEEPER_TESTNET_API ?? "http://127.0.0.1:8789").replace(/\/$/, ""),
    explorer: "https://explorer.testnet.arc.io",
    mode: "Live fills" as const,
  },
} as const;

export type NetConfig = (typeof NETWORKS)[Network];

// Must match OrderExecutor.WITNESS_TYPE_STRING / the TS+Python SDKs.
export const WITNESS_TYPES = {
  PermitWitnessTransferFrom: [
    { name: "permitted", type: "TokenPermissions" },
    { name: "spender", type: "address" },
    { name: "nonce", type: "uint256" },
    { name: "deadline", type: "uint256" },
    { name: "witness", type: "OrderIntent" },
  ],
  TokenPermissions: [
    { name: "token", type: "address" },
    { name: "amount", type: "uint256" },
  ],
  OrderIntent: [
    { name: "tokenOut", type: "address" },
    { name: "minOut", type: "uint256" },
  ],
} as const;

export const permit2Domain = (chainId: number) =>
  ({ name: "Permit2", chainId, verifyingContract: PERMIT2 }) as const;

export type LimitOrderParams = {
  tokenIn: Address;
  tokenOut: Address;
  amountIn: bigint;
  minOut: bigint;
  nonce: bigint;
  deadline: bigint;
};

/** Sign a one-shot LIMIT order (Permit2 SignatureTransfer + witness). No gas, no transaction. */
export async function signLimitOrder(
  w: WalletClient,
  account: Address,
  net: NetConfig,
  p: LimitOrderParams,
): Promise<Hex> {
  return w.signTypedData({
    account,
    domain: permit2Domain(net.chainId),
    types: WITNESS_TYPES,
    primaryType: "PermitWitnessTransferFrom",
    message: {
      permitted: { token: p.tokenIn, amount: p.amountIn },
      spender: net.executor,
      nonce: p.nonce,
      deadline: p.deadline,
      witness: { tokenOut: p.tokenOut, minOut: p.minOut },
    },
  });
}

export type OrderRow = {
  id: string;
  maker: string;
  token_in: string;
  token_out: string;
  amount_in: string;
  min_out: string;
  status: string;
  fill_tx: string | null;
  error: string | null;
  created_at: number;
  filled_at: number | null;
};

export type SubmitResult = { ok: boolean; order?: OrderRow; error?: string; detail?: string };

/** POST a signed order to the keeper. */
export async function submitOrder(
  net: NetConfig,
  payload: {
    maker: string;
    tokenIn: string;
    tokenOut: string;
    amountIn: string;
    minOut: string;
    nonce: string;
    deadline: number;
    signature: string;
  },
): Promise<SubmitResult> {
  try {
    const r = await fetch(`${net.keeperApi}/v1/orders`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
    const j = (await r.json()) as SubmitResult;
    return r.ok ? { ok: true, order: j.order } : { ok: false, error: j.error, detail: j.detail };
  } catch (e) {
    return { ok: false, error: "keeper_unreachable", detail: (e as Error).message };
  }
}

/** GET the current order state (poll until FILLED/FAILED/EXPIRED). */
export async function getOrder(net: NetConfig, id: string): Promise<OrderRow | null> {
  try {
    const r = await fetch(`${net.keeperApi}/v1/orders/${id}`);
    if (!r.ok) return null;
    return (await r.json()) as OrderRow;
  } catch {
    return null;
  }
}
