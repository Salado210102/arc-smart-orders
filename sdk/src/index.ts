// EIP-712 intents + signing for Arc Smart Orders.
// Two flows:
//   1) One-shot LIMIT (FX): Permit2 permitWitnessTransferFrom with witness (tokenOut, minOut).
//   2) Recurring TWAP:      Permit2 AllowanceTransfer (PermitSingle) + signed DcaIntent.
//
// Arc facts baked in:
//   - USDC uses the ERC-20 interface (6 decimals) at 0x3600...0000 for Permit2 flows.
//   - Permit2 is deployed at the canonical address 0x0000...BA3.
//   - The DcaIntent domain name MUST match the executor ("ArcSmartOrders", version "1").
import type { Address, Hex, PublicClient, TypedDataDomain, WalletClient } from "viem";
import { keccak256, maxUint256, stringToHex } from "viem";

export const ARC_MAINNET_CHAIN_ID = 5042;
export const ARC_TESTNET_CHAIN_ID = 5042002;

export const RPC = {
  mainnet: "https://rpc.mainnet.arc.io",
  testnet: "https://rpc.testnet.arc.io",
} as const;

// USDC ERC-20 interface (6 decimals). The native balance is the SAME asset (18-dec accounting).
export const USDC = "0x3600000000000000000000000000000000000000" as const;
export const EURC = {
  mainnet: "0xbEf5f6d51CB62b58e6A8f77868681825C6fe21c1",
  testnet: "0x89B50855Aa3bE2F677cD6303Cec089B5F319D72a",
} as const;
export const PERMIT2 = "0x000000000022D473030F116dDEE9F6B43aC78BA3" as const;

// ---- Permit2 domain (no version) ----
export const permit2Domain = (chainId: number): TypedDataDomain => ({
  name: "Permit2",
  chainId,
  verifyingContract: PERMIT2,
});

// ---- One-shot witness (limit FX order) ----
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

// Must match OrderExecutor.WITNESS_TYPE_STRING exactly (referenced types sorted alphabetically).
export const WITNESS_TYPE_STRING =
  "OrderIntent witness)OrderIntent(address tokenOut,uint256 minOut)TokenPermissions(address token,uint256 amount)";

// ---- Recurring intent (TWAP) — our own domain ----
export const intentDomain = (chainId: number, executor: Address): TypedDataDomain => ({
  name: "ArcSmartOrders",
  version: "1",
  chainId,
  verifyingContract: executor,
});

export const INTENT_TYPES = {
  DcaIntent: [
    { name: "owner", type: "address" },
    { name: "tokenIn", type: "address" },
    { name: "tokenOut", type: "address" },
    { name: "maxAmountIn", type: "uint256" },
    { name: "minRate", type: "uint256" },
    { name: "deadline", type: "uint256" },
  ],
} as const;

// Permit2 AllowanceTransfer (PermitSingle) types.
export const PERMIT_SINGLE_TYPES = {
  PermitSingle: [
    { name: "details", type: "PermitDetails" },
    { name: "spender", type: "address" },
    { name: "sigDeadline", type: "uint256" },
  ],
  PermitDetails: [
    { name: "token", type: "address" },
    { name: "amount", type: "uint160" },
    { name: "expiration", type: "uint48" },
    { name: "nonce", type: "uint48" },
  ],
} as const;

export type LimitOrder = {
  tokenIn: Address; // USDC
  tokenOut: Address; // EURC
  amountIn: bigint; // base units (6 dec)
  minOut: bigint; // minimum tokenOut (6 dec) — the FX limit
  spender: Address; // the OrderExecutor
  nonce: bigint;
  deadline: bigint;
  chainId: number;
};

/** Sign a one-shot LIMIT FX order (Permit2 SignatureTransfer + witness). Returns the signature. */
export async function signLimitOrder(wallet: WalletClient, o: LimitOrder): Promise<Hex> {
  if (!wallet.account) throw new Error("wallet has no account");
  return wallet.signTypedData({
    account: wallet.account,
    domain: permit2Domain(o.chainId),
    types: WITNESS_TYPES,
    primaryType: "PermitWitnessTransferFrom",
    message: {
      permitted: { token: o.tokenIn, amount: o.amountIn },
      spender: o.spender,
      nonce: o.nonce,
      deadline: o.deadline,
      witness: { tokenOut: o.tokenOut, minOut: o.minOut },
    },
  });
}

export type TwapOrder = {
  owner: Address;
  tokenIn: Address;
  tokenOut: Address;
  maxAmountIn: bigint; // total budget (base units)
  minRate: bigint; // min tokenOut per 1e18 tokenIn (base units)
  deadline: bigint; // also the PermitSingle expiration
  spender: Address;
  nonce: number;
  sigDeadline: bigint;
  chainId: number;
};

/** Sign the AllowanceTransfer permit + the recurring intent for a TWAP order. */
export async function signTwapOrder(
  wallet: WalletClient,
  o: TwapOrder,
): Promise<{ permitSignature: Hex; intentSignature: Hex }> {
  if (!wallet.account) throw new Error("wallet has no account");
  const permitSignature = await wallet.signTypedData({
    account: wallet.account,
    domain: permit2Domain(o.chainId),
    types: PERMIT_SINGLE_TYPES,
    primaryType: "PermitSingle",
    message: {
      details: { token: o.tokenIn, amount: o.maxAmountIn, expiration: Number(o.deadline), nonce: o.nonce },
      spender: o.spender,
      sigDeadline: o.sigDeadline,
    },
  });
  const intentSignature = await wallet.signTypedData({
    account: wallet.account,
    domain: intentDomain(o.chainId, o.spender),
    types: INTENT_TYPES,
    primaryType: "DcaIntent",
    message: {
      owner: o.owner,
      tokenIn: o.tokenIn,
      tokenOut: o.tokenOut,
      maxAmountIn: o.maxAmountIn,
      minRate: o.minRate,
      deadline: o.deadline,
    },
  });
  return { permitSignature, intentSignature };
}

/** minRate helper: minimum tokenOut (6 dec) per 1e18 of tokenIn (6 dec), from a human FX rate. */
export function minRateFromFx(humanTokenOutPerIn: number, bufferPct = 98): bigint {
  // tokensOut(base) per tokenIn(base) = rate (both 6 dec -> cancels), scaled to 1e18:
  return BigInt(Math.floor(humanTokenOutPerIn * (bufferPct / 100) * 1e18));
}

export { keccak256, stringToHex };

// ---- One-time Permit2 approval (required before any order can be filled) ----
export const erc20Abi = [
  {
    type: "function",
    name: "allowance",
    stateMutability: "view",
    inputs: [
      { name: "owner", type: "address" },
      { name: "spender", type: "address" },
    ],
    outputs: [{ type: "uint256" }],
  },
  {
    type: "function",
    name: "approve",
    stateMutability: "nonpayable",
    inputs: [
      { name: "spender", type: "address" },
      { name: "amount", type: "uint256" },
    ],
    outputs: [{ type: "bool" }],
  },
] as const;

/**
 * Approves Permit2 to pull `token` (e.g. USDC) from the user's wallet — one time per token.
 * Required before the executor can `permitWitnessTransferFrom` / `transferFrom`.
 */
export async function ensurePermit2Approval(
  publicClient: PublicClient,
  wallet: WalletClient,
  token: Address,
  amount: bigint = maxUint256,
): Promise<{ alreadyApproved: boolean; txHash?: Hex }> {
  if (!wallet.account) throw new Error("wallet has no account");
  const owner = wallet.account.address;
  const current = (await publicClient.readContract({
    address: token,
    abi: erc20Abi,
    functionName: "allowance",
    args: [owner, PERMIT2],
  })) as bigint;
  if (current >= amount) return { alreadyApproved: true };

  const txHash = await wallet.writeContract({
    account: wallet.account,
    address: token,
    abi: erc20Abi,
    functionName: "approve",
    args: [PERMIT2, amount],
  } as never);
  await publicClient.waitForTransactionReceipt({ hash: txHash });
  return { alreadyApproved: false, txHash };
}
