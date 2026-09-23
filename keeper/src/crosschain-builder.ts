// Cross-chain intent builder for the CrossChainOrderExecutor.
//
// Flow: the user signs a `CrossChainIntent` ON THE SOURCE CHAIN (e.g. Base Sepolia); the input USDC is
// delivered to the executor on Arc by the interop/CCTP message; the keeper fills it with swapData that
// sends `tokenOut` to the owner. The EIP-712 domain is the STANDARD 4-field domain (name/version/
// chainId/verifyingContract) so viem & wallets can sign it; `chainId` = destination chain, and the
// signed intent itself carries sourceChainId + destinationChainId + a single-use nonce for anti-replay.
import { encodeFunctionData, type Address, type Hex, type TypedDataDomain, type WalletClient } from "viem";

export const CROSS_CHAIN_DOMAIN_NAME = "ArcCrossChainOrders";
export const CROSS_CHAIN_DOMAIN_VERSION = "1";

/** Standard EIP-712 domain. `chainId` MUST be the DESTINATION (execution) chain. */
export const crossChainDomain = (executor: Address, destinationChainId: number): TypedDataDomain => ({
  name: CROSS_CHAIN_DOMAIN_NAME,
  version: CROSS_CHAIN_DOMAIN_VERSION,
  chainId: destinationChainId,
  verifyingContract: executor,
});

// Field order MUST match CrossChainOrderExecutor.INTENT_TYPEHASH exactly.
export const CROSS_CHAIN_TYPES = {
  CrossChainIntent: [
    { name: "owner", type: "address" },
    { name: "tokenIn", type: "address" },
    { name: "tokenOut", type: "address" },
    { name: "amountIn", type: "uint256" },
    { name: "minOut", type: "uint256" },
    { name: "sourceChainId", type: "uint256" },
    { name: "destinationChainId", type: "uint256" },
    { name: "nonce", type: "uint256" },
    { name: "deadline", type: "uint256" },
  ],
} as const;

export type CrossChainIntent = {
  owner: Address; // order author (signer)
  tokenIn: Address; // delivered token (USDC in MVP)
  tokenOut: Address; // desired output
  amountIn: bigint; // gross input (base units)
  minOut: bigint; // minimum output on the NET (after fee)
  sourceChainId: bigint; // origin chain (must equal executor.sourceChainId)
  destinationChainId: bigint; // execution chain (must equal block.chainid)
  nonce: bigint;
  deadline: bigint;
};

/**
 * Sign a cross-chain intent. Call this on the SOURCE chain (the signer's wallet `chainId` is irrelevant
 * to the domain — the domain uses the destination chainId, which is what the executor verifies).
 */
export async function signCrossChainIntent(
  wallet: WalletClient,
  executor: Address,
  o: CrossChainIntent,
): Promise<Hex> {
  if (!wallet.account) throw new Error("wallet has no account");
  return wallet.signTypedData({
    account: wallet.account,
    domain: crossChainDomain(executor, Number(o.destinationChainId)),
    types: CROSS_CHAIN_TYPES,
    primaryType: "CrossChainIntent",
    message: o,
  });
}

export const crossChainExecutorAbi = [
  {
    type: "function",
    name: "executeCrossChain",
    stateMutability: "nonpayable",
    inputs: [
      {
        name: "intent",
        type: "tuple",
        components: [
          { name: "owner", type: "address" },
          { name: "tokenIn", type: "address" },
          { name: "tokenOut", type: "address" },
          { name: "amountIn", type: "uint256" },
          { name: "minOut", type: "uint256" },
          { name: "sourceChainId", type: "uint256" },
          { name: "destinationChainId", type: "uint256" },
          { name: "nonce", type: "uint256" },
          { name: "deadline", type: "uint256" },
        ],
      },
      { name: "signature", type: "bytes" },
      { name: "swapTarget", type: "address" },
      { name: "swapData", type: "bytes" },
    ],
    outputs: [],
  },
] as const;

/** Encode the keeper's fill call for CrossChainOrderExecutor.executeCrossChain. */
export function buildExecuteCrossChainData(
  intent: CrossChainIntent,
  signature: Hex,
  swapTarget: Address,
  swapData: Hex,
): Hex {
  return encodeFunctionData({
    abi: crossChainExecutorAbi,
    functionName: "executeCrossChain",
    args: [intent, signature, swapTarget, swapData],
  });
}
