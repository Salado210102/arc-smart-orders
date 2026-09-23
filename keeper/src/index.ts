// Arc Smart Orders — keeper/relayer
// Executes users' signed intents on Arc via the OrderExecutor, paying gas in USDC.
//
// Arc specifics handled here:
//   - maxFeePerGas >= 20 gwei (the mempool silently drops lower txs).
//   - USDC/EURC are ERC-20 (6 decimals); never mix with native (18).
//   - Instant finality: a single confirmation is enough.
//
// Usage: cp ../.env.example .env  → fill EXECUTOR/ROUTER → npm install → npm start
import { readFileSync } from "node:fs";
import {
  createPublicClient,
  createWalletClient,
  http,
  defineChain,
  encodeFunctionData,
} from "viem";
import { privateKeyToAccount } from "viem/accounts";

const RPC = process.env.ARC_TESTNET_RPC ?? "https://rpc.testnet.arc.io";
const EXECUTOR = process.env.EXECUTOR as `0x${string}`;
const ROUTER = process.env.ROUTER as `0x${string}`;
const MIN_FEE_GWEI = BigInt(process.env.MIN_FEE_GWEI ?? "20");
const LOOP_MS = Number(process.env.LOOP_MS ?? 5000);
const ORDERS_FILE = process.env.ORDERS_FILE ?? "orders.json";

const USDC = "0x3600000000000000000000000000000000000000" as const;
const EURC = "0x89B50855Aa3bE2F677cD6303Cec089B5F319D72a" as const; // testnet

// Arc testnet (viem also ships `arcTestnet` in recent versions).
const arcTestnet = defineChain({
  id: 5042002,
  name: "Arc Testnet",
  nativeCurrency: { name: "USDC", symbol: "USDC", decimals: 18 },
  rpcUrls: { default: { http: [RPC] } },
  blockExplorers: { default: { name: "Arc Explorer", url: "https://explorer.testnet.arc.io" } },
});

// OrderExecutor ABI (only the two entrypoints) — JSON to avoid nested-tuple parsing issues.
const executorAbi = [
  {
    type: "function",
    name: "executeOrder",
    stateMutability: "nonpayable",
    inputs: [
      {
        name: "permit",
        type: "tuple",
        components: [
          {
            name: "permitted",
            type: "tuple",
            components: [{ name: "token", type: "address" }, { name: "amount", type: "uint256" }],
          },
          { name: "nonce", type: "uint256" },
          { name: "deadline", type: "uint256" },
        ],
      },
      { name: "orderOwner", type: "address" },
      { name: "permitSignature", type: "bytes" },
      { name: "swapTarget", type: "address" },
      { name: "swapData", type: "bytes" },
      { name: "tokenOut", type: "address" },
      { name: "minOut", type: "uint256" },
    ],
    outputs: [],
  },
  {
    type: "function",
    name: "executeDca",
    stateMutability: "nonpayable",
    inputs: [
      {
        name: "permitSingle",
        type: "tuple",
        components: [
          {
            name: "details",
            type: "tuple",
            components: [
              { name: "token", type: "address" },
              { name: "amount", type: "uint160" },
              { name: "expiration", type: "uint48" },
              { name: "nonce", type: "uint48" },
            ],
          },
          { name: "spender", type: "address" },
          { name: "sigDeadline", type: "uint256" },
        ],
      },
      { name: "permitSignature", type: "bytes" },
      { name: "orderOwner", type: "address" },
      { name: "partAmount", type: "uint256" },
      { name: "swapTarget", type: "address" },
      { name: "swapData", type: "bytes" },
      { name: "tokenOut", type: "address" },
      { name: "minOut", type: "uint256" },
      {
        name: "intent",
        type: "tuple",
        components: [
          { name: "owner", type: "address" },
          { name: "tokenIn", type: "address" },
          { name: "tokenOut", type: "address" },
          { name: "maxAmountIn", type: "uint256" },
          { name: "minRate", type: "uint256" },
          { name: "deadline", type: "uint256" },
        ],
      },
      { name: "intentSignature", type: "bytes" },
    ],
    outputs: [],
  },
] as const;

const routerAbi = [
  {
    type: "function",
    name: "swap",
    stateMutability: "nonpayable",
    inputs: [
      { name: "tokenIn", type: "address" },
      { name: "amountIn", type: "uint256" },
      { name: "tokenOut", type: "address" },
      { name: "recipient", type: "address" },
      { name: "minOut", type: "uint256" },
    ],
    outputs: [{ type: "uint256" }],
  },
] as const;

type LimitOrder = {
  id: string;
  type: "LIMIT";
  owner: `0x${string}`;
  tokenIn: `0x${string}`;
  tokenOut: `0x${string}`;
  amountIn: string;
  minOut: string;
  nonce: string;
  deadline: number;
  signature: `0x${string}`;
  ready: boolean;
};

const account = privateKeyToAccount((process.env.KEEPER_PK ?? "0x") as `0x${string}`);
const pc = createPublicClient({ chain: arcTestnet, transport: http(RPC) });
const wc = createWalletClient({ account, chain: arcTestnet, transport: http(RPC) });

async function fee(): Promise<bigint> {
  const gwei = 10n ** 9n;
  const floor = MIN_FEE_GWEI * gwei;
  const suggested = await pc.getGasPrice().catch(() => floor);
  return suggested > floor ? suggested : floor; // never below the 20 gwei floor
}

async function processLimit(o: LimitOrder) {
  const amountIn = BigInt(o.amountIn);
  const minOut = BigInt(o.minOut);

  // The swap output goes straight to the user; the executor then verifies minOut.
  const swapData = encodeFunctionData({
    abi: routerAbi,
    functionName: "swap",
    args: [o.tokenIn, amountIn, o.tokenOut, o.owner, minOut],
  });

  const data = encodeFunctionData({
    abi: executorAbi,
    functionName: "executeOrder",
    args: [
      { permitted: { token: o.tokenIn, amount: amountIn }, nonce: BigInt(o.nonce), deadline: BigInt(o.deadline) },
      o.owner,
      o.signature,
      ROUTER,
      swapData,
      o.tokenOut,
      minOut,
    ],
  });

  const hash = await wc.sendTransaction({ to: EXECUTOR, data, maxFeePerGas: await fee() });
  console.log(`[arc] ${o.id} executeOrder enviado ${hash}`);
  const rc = await pc.waitForTransactionReceipt({ hash, confirmations: 1 }); // instant finality
  console.log(`[arc] ${o.id} ${rc.status === "success" ? "FILLED" : "REVERTED"}`);
}

async function tick() {
  try {
    if (!EXECUTOR || !ROUTER) {
      console.warn("[arc] faltan EXECUTOR/ROUTER en .env");
      return;
    }
    const orders = JSON.parse(readFileSync(ORDERS_FILE, "utf8")) as LimitOrder[];
    for (const o of orders) {
      if (o.type === "LIMIT" && o.ready) {
        // TODO: en produccion, marcar readiness comparando el FX real (oraculo/StableFX/App Kit quote)
        // contra el limite firmado (minOut / amountIn), no un flag manual.
        await processLimit(o).catch((e) => console.error(`[arc] ${o.id}:`, e.shortMessage ?? e.message));
      }
    }
  } catch (e) {
    console.error("[arc]", (e as Error).message);
  } finally {
    setTimeout(tick, LOOP_MS);
  }
}

console.log(`Arc keeper activo · keeper=${account.address} · chain=${arcTestnet.id}`);
void tick();

export { arcTestnet, USDC, EURC };
