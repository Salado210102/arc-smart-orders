// E2E setup: approves Permit2 for USDC and signs a LIMIT order into keeper/orders.json.
// Run after deploying (needs EXECUTOR in env):  npx tsx src/setup-order.ts
import { readFileSync, writeFileSync } from "node:fs";
import { createPublicClient, createWalletClient, http, defineChain, parseUnits } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import {
  signLimitOrder,
  ensurePermit2Approval,
  USDC,
  EURC,
  ARC_TESTNET_CHAIN_ID,
} from "../../sdk/src/index.ts";

const RPC = process.env.ARC_TESTNET_RPC ?? "https://rpc.testnet.arc.io";
const EXECUTOR = process.env.EXECUTOR as `0x${string}`;
const KEY_FILE = process.env.ARC_KEY_FILE ?? "../.secrets/arc-deployer.json";

const chain = defineChain({
  id: ARC_TESTNET_CHAIN_ID,
  name: "Arc Testnet",
  nativeCurrency: { name: "USDC", symbol: "USDC", decimals: 18 },
  rpcUrls: { default: { http: [RPC] } },
});

const { privateKey } = JSON.parse(readFileSync(KEY_FILE, "utf8")) as { privateKey: `0x${string}` };
const account = privateKeyToAccount(privateKey);
const pc = createPublicClient({ chain, transport: http(RPC) });
const wc = createWalletClient({ account, chain, transport: http(RPC) });

if (!EXECUTOR) throw new Error("set EXECUTOR env var (OrderExecutor address)");

console.log("account:", account.address);

// 1) One-time: approve Permit2 for USDC (the 6-decimal ERC-20 interface).
const appr = await ensurePermit2Approval(pc, wc, USDC);
console.log("Permit2 approval:", appr.alreadyApproved ? "already approved" : `sent ${appr.txHash}`);

// 2) Sign a LIMIT order: 1 USDC -> minOut 0.92 EURC.
const now = Math.floor(Date.now() / 1000);
const amountIn = parseUnits("1", 6);
const minOut = parseUnits("0.92", 6);
const signature = await signLimitOrder(wc, {
  tokenIn: USDC,
  tokenOut: EURC.testnet as `0x${string}`,
  amountIn,
  minOut,
  spender: EXECUTOR,
  nonce: 1n,
  deadline: BigInt(now + 3600),
  chainId: ARC_TESTNET_CHAIN_ID,
});

// 3) Write the order for the keeper.
writeFileSync(
  "orders.json",
  JSON.stringify(
    [
      {
        id: "e2e-1",
        type: "LIMIT",
        owner: account.address,
        tokenIn: USDC,
        tokenOut: EURC.testnet,
        amountIn: amountIn.toString(),
        minOut: minOut.toString(),
        nonce: "1",
        deadline: now + 3600,
        signature,
        ready: true,
      },
    ],
    null,
    2,
  ),
);
console.log("signed LIMIT order -> keeper/orders.json");
