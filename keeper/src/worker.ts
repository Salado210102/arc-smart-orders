// Persistent keeper worker: polls PENDING orders, checks the on-chain rate vs the signed minOut,
// fills via OrderExecutor v2 (input-side fee), and submits the ERC-8183 deliverable if a job is linked.
import { createPublicClient, createWalletClient, http, defineChain, encodeFunctionData, keccak256, toHex } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { listPending, markFilled, markFailed, expireOld, type OrderRow } from "./db.ts";
import { submitDeliverable } from "./agentic.ts";
import { ARC_TESTNET_CHAIN_ID } from "../../sdk/src/index.ts";

const RPC = process.env.ARC_TESTNET_RPC ?? "https://rpc.testnet.arc.io";
const EXECUTOR = (process.env.EXECUTOR ?? "") as `0x${string}`;
const ROUTER = (process.env.ROUTER ?? "") as `0x${string}`;
const MIN_FEE_GWEI = BigInt(process.env.MIN_FEE_GWEI ?? "20");
const LOOP_MS = Number(process.env.LOOP_MS ?? 8000);
const DRY = process.env.DRY === "1";

const chain = defineChain({
  id: ARC_TESTNET_CHAIN_ID,
  name: "Arc",
  nativeCurrency: { name: "USDC", symbol: "USDC", decimals: 18 },
  rpcUrls: { default: { http: [RPC] } },
});
const pc = createPublicClient({ chain, transport: http(RPC) });
const account = privateKeyToAccount((process.env.KEEPER_PK ?? "0x") as `0x${string}`);
const wc = createWalletClient({ account, chain, transport: http(RPC) });

const executorAbi = [
  { type: "function", name: "feeBps", stateMutability: "view", inputs: [], outputs: [{ type: "uint256" }] },
  {
    type: "function", name: "executeOrder", stateMutability: "nonpayable",
    inputs: [
      { name: "permit", type: "tuple", components: [{ name: "permitted", type: "tuple", components: [{ name: "token", type: "address" }, { name: "amount", type: "uint256" }] }, { name: "nonce", type: "uint256" }, { name: "deadline", type: "uint256" }] },
      { name: "orderOwner", type: "address" }, { name: "permitSignature", type: "bytes" },
      { name: "swapTarget", type: "address" }, { name: "swapData", type: "bytes" },
      { name: "tokenOut", type: "address" }, { name: "minOut", type: "uint256" },
    ], outputs: [],
  },
] as const;
const routerAbi = [
  { type: "function", name: "swap", stateMutability: "nonpayable", inputs: [{ name: "tokenIn", type: "address" }, { name: "amountIn", type: "uint256" }, { name: "tokenOut", type: "address" }, { name: "recipient", type: "address" }, { name: "minOut", type: "uint256" }], outputs: [{ type: "uint256" }] },
  { type: "function", name: "rateEurcPerUsdc", stateMutability: "view", inputs: [], outputs: [{ type: "uint256" }] },
] as const;

const gas = async () => {
  const floor = MIN_FEE_GWEI * 10n ** 9n;
  const s = await pc.getGasPrice().catch(() => floor);
  return s > floor ? s : floor;
};

/** Readiness: is the on-chain rate good enough to fill this order? (mock-router FX check) */
async function ready(o: OrderRow, swapAmount: bigint): Promise<boolean> {
  try {
    const rate = (await pc.readContract({ address: ROUTER, abi: routerAbi, functionName: "rateEurcPerUsdc" })) as bigint;
    const expectedOut = (swapAmount * rate) / 10n ** 18n;
    return expectedOut >= BigInt(o.min_out);
  } catch {
    return true; // no rate oracle available -> attempt the fill (revert-protected)
  }
}

async function processOrder(o: OrderRow) {
  const amountIn = BigInt(o.amount_in);
  const minOut = BigInt(o.min_out);
  const feeBps = (await pc.readContract({ address: EXECUTOR, abi: executorAbi, functionName: "feeBps" })) as bigint;
  const swapAmount = amountIn - (amountIn * feeBps) / 10_000n;

  if (!(await ready(o, swapAmount))) {
    console.log(`[orders] ${o.id}: rate no cumple minOut; se reintenta luego`);
    return;
  }

  const swapData = encodeFunctionData({
    abi: routerAbi, functionName: "swap",
    args: [o.token_in as `0x${string}`, swapAmount, o.token_out as `0x${string}`, o.maker as `0x${string}`, minOut],
  });
  const data = encodeFunctionData({
    abi: executorAbi, functionName: "executeOrder",
    args: [
      { permitted: { token: o.token_in as `0x${string}`, amount: amountIn }, nonce: BigInt(o.nonce), deadline: BigInt(o.deadline) },
      o.maker as `0x${string}`, o.signature as `0x${string}`, ROUTER, swapData, o.token_out as `0x${string}`, minOut,
    ],
  });

  if (DRY) {
    console.log(`[orders] ${o.id}: DRY (feeBps=${feeBps}, swapAmount=${swapAmount})`);
    return;
  }

  try {
    const hash = await wc.sendTransaction({ to: EXECUTOR, data, maxFeePerGas: await gas() });
    const rc = await pc.waitForTransactionReceipt({ hash, confirmations: 1 });
    if (rc.status !== "success") throw new Error("exec_reverted");
    markFilled(o.id, hash);
    console.log(`[orders] ${o.id} FILLED -> ${hash}`);
    if (o.job_id) {
      const d = keccak256(toHex(hash));
      await submitDeliverable(pc, wc, BigInt(o.job_id), d);
      console.log(`[orders] ${o.id}: deliverable enviado al job ${o.job_id}`);
    }
  } catch (e) {
    markFailed(o.id, (e as { shortMessage?: string; message?: string }).shortMessage ?? (e as Error).message ?? "exec_failed");
    console.error(`[orders] ${o.id} FAILED:`, (e as { shortMessage?: string; message?: string }).shortMessage ?? (e as Error).message);
  }
}

async function tick() {
  try {
    if (!EXECUTOR || !ROUTER) {
      console.warn("[orders] faltan EXECUTOR/ROUTER en el entorno");
      return;
    }
    expireOld(Math.floor(Date.now() / 1000));
    const orders = listPending(25);
    for (const o of orders) {
      try {
        await processOrder(o);
      } catch (e) {
        console.error(`[orders] ${o.id}:`, (e as Error).message);
      }
    }
  } catch (e) {
    console.error("[orders]", (e as Error).message);
  } finally {
    setTimeout(tick, LOOP_MS);
  }
}

export function startWorker() {
  console.log(`[orders] worker activo · keeper=${account.address} · chain=${chain.id} · loop=${LOOP_MS}ms${DRY ? " · DRY" : ""}`);
  void tick();
}
