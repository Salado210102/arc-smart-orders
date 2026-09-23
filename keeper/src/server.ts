// Order API + off-chain validation (Fastify). Persists signed orders for the worker.
import { randomUUID } from "node:crypto";
import Fastify from "fastify";
import websocket from "@fastify/websocket";
import { createPublicClient, http, defineChain, verifyTypedData } from "viem";
import { PERMIT2, USDC, EURC, ARC_MAINNET_CHAIN_ID, RPC as RPCS } from "../../sdk/src/index.ts";
import { WITNESS_TYPES } from "../../sdk/src/index.ts";
import { insertOrder, getOrder, listByMaker, listPending } from "./db.ts";
import { bus, emitEvent } from "./events.ts";

const RPC = process.env.ARC_RPC ?? RPCS.mainnet;
const CHAIN_ID = Number(process.env.CHAIN_ID ?? ARC_MAINNET_CHAIN_ID);
const EXECUTOR = (process.env.EXECUTOR ?? "") as `0x${string}`;
const PORT = Number(process.env.PORT ?? 8788);

const chain = defineChain({
  id: CHAIN_ID,
  name: "Arc",
  nativeCurrency: { name: "USDC", symbol: "USDC", decimals: 18 },
  rpcUrls: { default: { http: [RPC] } },
});
const pc = createPublicClient({ chain, transport: http(RPC) });

const permit2Domain = { name: "Permit2", chainId: CHAIN_ID, verifyingContract: PERMIT2 } as const;
const erc20Abi = [
  { type: "function", name: "balanceOf", stateMutability: "view", inputs: [{ name: "a", type: "address" }], outputs: [{ type: "uint256" }] },
  { type: "function", name: "allowance", stateMutability: "view", inputs: [{ name: "o", type: "address" }, { name: "s", type: "address" }], outputs: [{ type: "uint256" }] },
] as const;

const isAddr = (a: unknown): a is string => typeof a === "string" && /^0x[0-9a-fA-F]{40}$/.test(a);
const isHexSig = (s: unknown): s is string => typeof s === "string" && /^0x[0-9a-fA-F]{130}$/.test(s);
const isDigits = (s: unknown): s is string => typeof s === "string" && /^\d+$/.test(s) && s !== "0";

export async function buildServer() {
  const app = Fastify({ logger: true });
  await app.register(websocket);

  //  Live feed: broadcasts order lifecycle events (created/filled/failed).
  app.get("/ws", { websocket: true }, (socket) => {
    try {
      socket.send(JSON.stringify({ type: "hello", ts: Date.now() }));
    } catch {
      /* ignore */
    }
    const on = (e: unknown) => {
      try {
        socket.send(JSON.stringify(e));
      } catch {
        /* ignore */
      }
    };
    bus.on("event", on);
    socket.on("close", () => bus.off("event", on));
  });

  app.get("/health", async () => ({ ok: true, chainId: CHAIN_ID, executor: EXECUTOR }));

  app.get("/v1/orders", async (req) => {
    const maker = String((req.query as { maker?: string })?.maker ?? "").toLowerCase();
    const limit = Math.min(200, Math.max(1, Number((req.query as { limit?: string })?.limit ?? 100)));
    return { orders: maker && isAddr(maker) ? listByMaker(maker, limit) : [] };
  });

  app.get("/v1/orders/:id", async (req, reply) => {
    const o = getOrder(String((req.params as { id: string }).id));
    if (!o) return reply.code(404).send({ error: "not_found" });
    return o;
  });

  app.get("/v1/mempool", async () => ({ pending: listPending(100) }));

  app.post("/v1/orders", async (req, reply) => {
    try {
      const b = (req.body ?? {}) as Record<string, string>;
      const maker = String(b.maker ?? "").toLowerCase();
      const tokenIn = String(b.tokenIn ?? "").toLowerCase();
      const tokenOut = String(b.tokenOut ?? "").toLowerCase();
      const amountIn = String(b.amountIn ?? "");
      const minOut = String(b.minOut ?? "");
      const nonce = String(b.nonce ?? "");
      const deadline = Number(b.deadline);
      const signature = String(b.signature ?? "");

      if (!EXECUTOR) return reply.code(503).send({ error: "executor_not_configured" });
      if (!isAddr(maker) || !isAddr(tokenIn) || !isAddr(tokenOut)) return reply.code(400).send({ error: "bad_address" });
      if (!isDigits(amountIn) || !isDigits(minOut) || !isDigits(nonce)) return reply.code(400).send({ error: "bad_amount" });
      if (!isHexSig(signature)) return reply.code(400).send({ error: "bad_signature" });
      const now = Math.floor(Date.now() / 1000);
      if (!Number.isFinite(deadline) || deadline <= now + 30) return reply.code(400).send({ error: "deadline_too_soon" });

      //  1) EIP-712 signature (Permit2 witness) — spender = executor.
      const ok = await verifyTypedData({
        address: maker as `0x${string}`,
        domain: permit2Domain,
        types: WITNESS_TYPES,
        primaryType: "PermitWitnessTransferFrom",
        message: {
          permitted: { token: tokenIn as `0x${string}`, amount: BigInt(amountIn) },
          spender: EXECUTOR,
          nonce: BigInt(nonce),
          deadline: BigInt(deadline),
          witness: { tokenOut: tokenOut as `0x${string}`, minOut: BigInt(minOut) },
        },
        signature: signature as `0x${string}`,
      }).catch(() => false);
      if (!ok) return reply.code(400).send({ error: "bad_signature" });

      //  2) Balance + Permit2 allowance (ERC-20 interface).
      const [bal, allowance] = await Promise.all([
        pc.readContract({ address: tokenIn as `0x${string}`, abi: erc20Abi, functionName: "balanceOf", args: [maker as `0x${string}`] }) as Promise<bigint>,
        pc.readContract({ address: tokenIn as `0x${string}`, abi: erc20Abi, functionName: "allowance", args: [maker as `0x${string}`, PERMIT2] }) as Promise<bigint>,
      ]);
      if (bal < BigInt(amountIn)) return reply.code(400).send({ error: "insufficient_balance" });
      if (allowance < BigInt(amountIn)) return reply.code(400).send({ error: "permit2_allowance_missing" });

      const order = insertOrder({
        id: randomUUID(),
        maker,
        order_type: "LIMIT",
        token_in: tokenIn,
        token_out: tokenOut,
        amount_in: amountIn,
        min_out: minOut,
        nonce,
        deadline,
        signature,
        job_id: b.jobId ? String(b.jobId) : null,
      });
      emitEvent({ type: "order.created", id: order.id, maker });
      return { ok: true, order };
    } catch (e) {
      req.log.error(e);
      return reply.code(500).send({ error: "internal", detail: (e as Error).message });
    }
  });

  return app;
}

export async function startServer() {
  const app = await buildServer();
  await app.listen({ port: PORT, host: "0.0.0.0" });
  return app;
}

export { USDC, EURC };
