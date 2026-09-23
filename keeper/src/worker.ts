// Persistent keeper worker: polls PENDING orders, checks the on-chain rate vs the signed minOut,
// fills via OrderExecutor v2 (input-side fee), and submits the ERC-8183 deliverable if a job is linked.
//
// Two venues (SWAP_VENUE env):
//   - "mock"        : a fixed-rate MockStableRouter (testnet) exposing swap(...) + rateEurcPerUsdc().
//   - "uniswap-v3"  : Uniswap SwapRouter02 on Arc mainnet (exactInputSingle) — live USDC/EURC pool.
import { createPublicClient, createWalletClient, http, defineChain, encodeFunctionData, keccak256, toHex } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { listPending, markFilled, markFailed, expireOld, type OrderRow } from "./db.ts";
import { submitDeliverable } from "./agentic.ts";
import { emitEvent } from "./events.ts";
import { ARC_MAINNET_CHAIN_ID, RPC as RPCS } from "../../sdk/src/index.ts";

const RPC = process.env.ARC_RPC ?? RPCS.mainnet;
const CHAIN_ID = Number(process.env.CHAIN_ID ?? ARC_MAINNET_CHAIN_ID);
const EXECUTOR = (process.env.EXECUTOR ?? "") as `0x${string}`;
const ROUTER = (process.env.ROUTER ?? "") as `0x${string}`;
const MIN_FEE_GWEI = BigInt(process.env.MIN_FEE_GWEI ?? "20");
const LOOP_MS = Number(process.env.LOOP_MS ?? 8000);
const DRY = process.env.DRY === "1";

// Venue selection. Default: mock (testnet). Mainnet: SWAP_VENUE=uniswap-v3.
const SWAP_VENUE = (process.env.SWAP_VENUE ?? "mock").toLowerCase();
const UNIV3_FEE = Number(process.env.UNIV3_FEE ?? "500"); // USDC/EURC pool fee tier (500 = 0.05%)
const UNIV3_FACTORY = (process.env.UNIV3_FACTORY ?? "0xf0db7b58379503491d857dB50AC9ece64c653918") as `0x${string}`;

const chain = defineChain({
  id: CHAIN_ID,
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

// --- mock venue (testnet) ---
const routerAbi = [
  { type: "function", name: "swap", stateMutability: "nonpayable", inputs: [{ name: "tokenIn", type: "address" }, { name: "amountIn", type: "uint256" }, { name: "tokenOut", type: "address" }, { name: "recipient", type: "address" }, { name: "minOut", type: "uint256" }], outputs: [{ type: "uint256" }] },
  { type: "function", name: "rateEurcPerUsdc", stateMutability: "view", inputs: [], outputs: [{ type: "uint256" }] },
] as const;

// --- Uniswap v3 venue (mainnet) ---
const factoryAbi = [
  { type: "function", name: "getPool", stateMutability: "view", inputs: [{ name: "", type: "address" }, { name: "", type: "address" }, { name: "", type: "uint24" }], outputs: [{ type: "address" }] },
] as const;
const poolAbi = [
  { type: "function", name: "slot0", stateMutability: "view", inputs: [], outputs: [{ type: "uint160" }, { type: "int24" }, { type: "uint16" }, { type: "uint16" }, { type: "uint16" }, { type: "uint8" }, { type: "bool" }] },
  { type: "function", name: "token0", stateMutability: "view", inputs: [], outputs: [{ type: "address" }] },
] as const;
const swapRouter02Abi = [
  {
    type: "function", name: "exactInputSingle", stateMutability: "payable",
    inputs: [{
      name: "params", type: "tuple", components: [
        { name: "tokenIn", type: "address" }, { name: "tokenOut", type: "address" }, { name: "fee", type: "uint24" },
        { name: "recipient", type: "address" }, { name: "amountIn", type: "uint256" },
        { name: "amountOutMinimum", type: "uint256" }, { name: "sqrtPriceLimitX96", type: "uint160" },
      ],
    }],
    outputs: [{ name: "amountOut", type: "uint256" }],
  },
] as const;

const gas = async () => {
  const floor = MIN_FEE_GWEI * 10n ** 9n;
  const s = await pc.getGasPrice().catch(() => floor);
  return s > floor ? s : floor;
};

const poolCache = new Map<string, `0x${string}`>();
async function v3Pool(tokenIn: `0x${string}`, tokenOut: `0x${string}`): Promise<`0x${string}`> {
  const key = `${tokenIn}-${tokenOut}-${UNIV3_FEE}`;
  const hit = poolCache.get(key);
  if (hit) return hit;
  const pool = (await pc.readContract({ address: UNIV3_FACTORY, abi: factoryAbi, functionName: "getPool", args: [tokenIn, tokenOut, UNIV3_FEE] })) as `0x${string}`;
  if (pool === "0x0000000000000000000000000000000000000000") throw new Error("no_pool");
  poolCache.set(key, pool);
  return pool;
}

/** tokenOut (raw) per tokenIn (raw), scaled 1e18, from the Uniswap v3 pool price. */
async function v3RateScaled(tokenIn: `0x${string}`, tokenOut: `0x${string}`): Promise<bigint> {
  const pool = await v3Pool(tokenIn, tokenOut);
  const [slot0, token0] = await Promise.all([
    pc.readContract({ address: pool, abi: poolAbi, functionName: "slot0" }) as Promise<readonly [bigint, number, number, number, number, number, boolean]>,
    pc.readContract({ address: pool, abi: poolAbi, functionName: "token0" }) as Promise<string>,
  ]);
  const sqrt = slot0[0];
  const priceScaled = (sqrt * sqrt * 10n ** 18n) / 2n ** 192n; // token1 per token0, raw, 1e18
  return token0.toLowerCase() === tokenIn.toLowerCase() ? priceScaled : (10n ** 36n) / priceScaled;
}

/** Readiness: is the on-chain rate good enough to fill this order? */
async function ready(o: OrderRow, swapAmount: bigint): Promise<boolean> {
  try {
    if (SWAP_VENUE === "uniswap-v3") {
      const rate = await v3RateScaled(o.token_in as `0x${string}`, o.token_out as `0x${string}`);
      return (swapAmount * rate) / 10n ** 18n >= BigInt(o.min_out);
    }
    const rate = (await pc.readContract({ address: ROUTER, abi: routerAbi, functionName: "rateEurcPerUsdc" })) as bigint;
    return (swapAmount * rate) / 10n ** 18n >= BigInt(o.min_out);
  } catch {
    return true; // no rate oracle available -> attempt the fill (revert-protected)
  }
}

/** Build the venue-specific swapTarget + swapData (output must go to `recipient`). */
async function buildSwap(o: OrderRow, swapAmount: bigint, minOut: bigint): Promise<{ target: `0x${string}`; data: `0x${string}` }> {
  if (SWAP_VENUE === "uniswap-v3") {
    const data = encodeFunctionData({
      abi: swapRouter02Abi,
      functionName: "exactInputSingle",
      args: [{
        tokenIn: o.token_in as `0x${string}`,
        tokenOut: o.token_out as `0x${string}`,
        fee: UNIV3_FEE,
        recipient: o.maker as `0x${string}`,
        amountIn: swapAmount,
        amountOutMinimum: minOut,
        sqrtPriceLimitX96: 0n,
      }],
    });
    return { target: ROUTER, data };
  }
  const data = encodeFunctionData({
    abi: routerAbi, functionName: "swap",
    args: [o.token_in as `0x${string}`, swapAmount, o.token_out as `0x${string}`, o.maker as `0x${string}`, minOut],
  });
  return { target: ROUTER, data };
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

  const swap = await buildSwap(o, swapAmount, minOut);
  const data = encodeFunctionData({
    abi: executorAbi, functionName: "executeOrder",
    args: [
      { permitted: { token: o.token_in as `0x${string}`, amount: amountIn }, nonce: BigInt(o.nonce), deadline: BigInt(o.deadline) },
      o.maker as `0x${string}`, o.signature as `0x${string}`, swap.target, swap.data, o.token_out as `0x${string}`, minOut,
    ],
  });

  if (DRY) {
    console.log(`[orders] ${o.id}: DRY (venue=${SWAP_VENUE}, feeBps=${feeBps}, swapAmount=${swapAmount})`);
    return;
  }

  try {
    const hash = await wc.sendTransaction({ to: EXECUTOR, data, maxFeePerGas: await gas() });
    const rc = await pc.waitForTransactionReceipt({ hash, confirmations: 1 });
    if (rc.status !== "success") throw new Error("exec_reverted");
    markFilled(o.id, hash);
    emitEvent({ type: "order.filled", id: o.id, tx: hash, maker: o.maker });
    console.log(`[orders] ${o.id} FILLED -> ${hash}`);
    if (o.job_id) {
      const d = keccak256(toHex(hash));
      await submitDeliverable(pc, wc, BigInt(o.job_id), d);
      emitEvent({ type: "order.deliverable", id: o.id, jobId: o.job_id, tx: hash });
      console.log(`[orders] ${o.id}: deliverable enviado al job ${o.job_id}`);
    }
  } catch (e) {
    const msg = (e as { shortMessage?: string; message?: string }).shortMessage ?? (e as Error).message ?? "exec_failed";
    markFailed(o.id, msg);
    emitEvent({ type: "order.failed", id: o.id, error: msg });
    console.error(`[orders] ${o.id} FAILED:`, msg);
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
  console.log(`[orders] worker activo · keeper=${account.address} · chain=${chain.id} · venue=${SWAP_VENUE} · loop=${LOOP_MS}ms${DRY ? " · DRY" : ""}`);
  void tick();
}
