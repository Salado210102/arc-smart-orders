// Test client: signs a LIMIT order with wallet A and POSTs it to the keeper API, then polls status.
import { readFileSync } from "node:fs";
import { createPublicClient, createWalletClient, http, defineChain, parseUnits } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { signLimitOrder, ensurePermit2Approval, USDC, EURC, ARC_TESTNET_CHAIN_ID } from "../../sdk/src/index.ts";

const API = process.env.API_URL ?? "http://127.0.0.1:8788";
const RPC = "https://rpc.testnet.arc.io";
const EXECUTOR = (process.env.EXECUTOR ?? "0x5E9dCd592B37fda481Fc203756DA4D990cE438bA") as `0x${string}`;

const chain = defineChain({
  id: ARC_TESTNET_CHAIN_ID, name: "Arc",
  nativeCurrency: { name: "USDC", symbol: "USDC", decimals: 18 },
  rpcUrls: { default: { http: [RPC] } },
});
const pc = createPublicClient({ chain, transport: http(RPC) });
const A = privateKeyToAccount(JSON.parse(readFileSync("../.secrets/arc-deployer.json", "utf8")).privateKey as `0x${string}`);
const wc = createWalletClient({ account: A, chain, transport: http(RPC) });

await ensurePermit2Approval(pc, wc, USDC); // idempotent

const amountIn = parseUnits("1", 6);
const minOut = parseUnits("0.90", 6);
const nonce = BigInt(Date.now());
const deadline = BigInt(Math.floor(Date.now() / 1000) + 3600);
const signature = await signLimitOrder(wc, {
  tokenIn: USDC, tokenOut: EURC.testnet as `0x${string}`, amountIn, minOut,
  spender: EXECUTOR, nonce, deadline, chainId: ARC_TESTNET_CHAIN_ID,
});

const res = await fetch(`${API}/v1/orders`, {
  method: "POST", headers: { "content-type": "application/json" },
  body: JSON.stringify({ maker: A.address, tokenIn: USDC, tokenOut: EURC.testnet, amountIn: amountIn.toString(), minOut: minOut.toString(), nonce: nonce.toString(), deadline: Number(deadline), signature }),
});
const body = (await res.json()) as { ok?: boolean; order?: { id: string }; error?: string };
console.log("POST /v1/orders ->", res.status, JSON.stringify(body).slice(0, 240));
if (!body?.order?.id) process.exit(1);

const id = body.order.id;
for (let i = 0; i < 12; i++) {
  await new Promise((r) => setTimeout(r, 3000));
  const d = (await (await fetch(`${API}/v1/orders/${id}`)).json()) as { status: string; fill_tx?: string; error?: string };
  console.log(`  poll ${i + 1}: status=${d.status}${d.fill_tx ? " tx=" + d.fill_tx : ""}${d.error ? " err=" + d.error : ""}`);
  if (d.status !== "PENDING") break;
}
