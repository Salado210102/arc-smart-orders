#!/usr/bin/env node
// Keeper metrics bot — realtime metrics for the Arc Smart Orders stack, via Telegram and/or stdout.
//
//   node ops/keeper-metrics-bot.mjs            # print metrics (default)
//   node ops/keeper-metrics-bot.mjs send        # compute + send once to Telegram
//   node ops/keeper-metrics-bot.mjs watch       # compute + send every METRICS_MS
//   node ops/keeper-metrics-bot.mjs serve       # reply to /metrics in Telegram (long-poll) — needs a bot token
//   node ops/keeper-metrics-bot.mjs test        # send a one-off test message
//
// Metrics:
//   a) feeRecipient balance (USDC + EURC)
//   b) total fills + cumulative volume (from OrderExecutor.OrderExecuted logs) + last fill
//   c) keeper gas balance (USDC) + RPC latency + order latency (ready -> filled, from the keeper DB)
//
// Config: loaded from ops/launchpad-alerts.env by default (so it reuses the SAME bot token as
// arc-alerts), override with METRICS_ENV. Plain Node (ESM) using the repo's viem.
//
//   ARC_RPC            (default https://rpc.mainnet.arc.io)
//   EXECUTOR           (default the mainnet OrderExecutor v2)
//   USDC / EURC        (default mainnet tokens)
//   LOOKBACK_BLOCKS    (default 50000)   FROM_BLOCK (optional absolute start)
//   CHUNK_BLOCKS       (default 10000)   RPC log-scan chunk size
//   KEEPER_API         (default http://127.0.0.1:8788)   DB_PATH (keeper SQLite, for order latency)
//   TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID   METRICS_MS (default 3600000)   METRICS_CHAT_ID (authz for serve)
import { createPublicClient, http, parseAbiItem, formatUnits } from "viem";
import { existsSync } from "node:fs";

const ENV_FILE = process.env.METRICS_ENV ?? process.env.ALERTS_ENV ?? "ops/launchpad-alerts.env";
if (existsSync(ENV_FILE) && typeof process.loadEnvFile === "function") {
  try {
    process.loadEnvFile(ENV_FILE);
  } catch {
    /* ignore */
  }
}

const RPC = process.env.ARC_RPC ?? "https://rpc.mainnet.arc.io";
const EXPLORER = process.env.EXPLORER ?? "https://explorer.arc.io";
const EXECUTOR = process.env.EXECUTOR ?? "0x9b3a990d1a31Ff5E01ddB8702e10F2529811FDb7";
const USDC = (process.env.USDC ?? "0x3600000000000000000000000000000000000000").toLowerCase();
const EURC = (process.env.EURC ?? "0xbEf5f6d51CB62b58e6A8f77868681825C6fe21c1").toLowerCase();
const LOOKBACK = BigInt(process.env.LOOKBACK_BLOCKS ?? "50000");
const FROM_BLOCK = process.env.FROM_BLOCK ? BigInt(process.env.FROM_BLOCK) : null;
const CHUNK = BigInt(process.env.CHUNK_BLOCKS ?? "10000");
const KEEPER_API = process.env.KEEPER_API ?? "http://127.0.0.1:8788";
const DB_PATH = process.env.DB_PATH ?? process.env.KEEPER_DB ?? "";
const TG_TOKEN = process.env.TELEGRAM_BOT_TOKEN;
const TG_CHAT = process.env.TELEGRAM_CHAT_ID;
const ALLOWED_CHAT = process.env.METRICS_CHAT_ID ?? TG_CHAT;
const METRICS_MS = Number(process.env.METRICS_MS ?? 3600000);

const pc = createPublicClient({ transport: http(RPC) });

const executorAbi = [
  parseAbiItem("function feeBps() view returns (uint256)"),
  parseAbiItem("function feeRecipient() view returns (address)"),
  parseAbiItem("function keeper() view returns (address)"),
  parseAbiItem("function owner() view returns (address)"),
];
const erc20Abi = [parseAbiItem("function balanceOf(address) view returns (uint256)")];
const ORDER_EXECUTED = parseAbiItem(
  "event OrderExecuted(address indexed orderOwner, address indexed tokenIn, address indexed tokenOut, address swapTarget, uint256 amountIn, uint256 amountOut)",
);

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const short = (a) => (a ? `${a.slice(0, 6)}…${a.slice(-4)}` : "—");
const fmt = (v, d = 4) => Number(formatUnits(v, 6)).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
const link = (t) => `<a href="${EXPLORER}/tx/${t}">${t.slice(0, 10)}…</a>`;

async function readExecutor() {
  try {
    const [feeBps, feeRecipient, keeper, owner] = await Promise.all([
      pc.readContract({ address: EXECUTOR, abi: executorAbi, functionName: "feeBps" }),
      pc.readContract({ address: EXECUTOR, abi: executorAbi, functionName: "feeRecipient" }),
      pc.readContract({ address: EXECUTOR, abi: executorAbi, functionName: "keeper" }),
      pc.readContract({ address: EXECUTOR, abi: executorAbi, functionName: "owner" }),
    ]);
    return { feeBps, feeRecipient, keeper, owner };
  } catch (e) {
    return {
      feeBps: null,
      feeRecipient: process.env.FEE_RECIPIENT ?? null,
      keeper: process.env.KEEPER ?? null,
      owner: null,
      error: e.message,
    };
  }
}

async function balance(addr, token) {
  if (!addr) return 0n;
  try {
    return await pc.readContract({ address: token, abi: erc20Abi, functionName: "balanceOf", args: [addr] });
  } catch {
    return 0n;
  }
}

async function fills() {
  const latest = await pc.getBlockNumber();
  const from = FROM_BLOCK ?? (latest > LOOKBACK ? latest - LOOKBACK : 0n);
  let logs = [];
  for (let start = from; start <= latest; start += CHUNK) {
    const end = start + CHUNK - 1n > latest ? latest : start + CHUNK - 1n;
    const part = await pc.getLogs({ address: EXECUTOR, event: ORDER_EXECUTED, fromBlock: start, toBlock: end });
    logs = logs.concat(part);
  }
  let count = 0n;
  let inUsdc = 0n;
  let inEurc = 0n;
  let outUsdc = 0n;
  let outEurc = 0n;
  for (const l of logs) {
    const { tokenIn, tokenOut, amountIn, amountOut } = l.args;
    count += 1n;
    const ti = (tokenIn ?? "").toLowerCase();
    const to = (tokenOut ?? "").toLowerCase();
    if (ti === USDC) inUsdc += amountIn;
    if (ti === EURC) inEurc += amountIn;
    if (to === USDC) outUsdc += amountOut;
    if (to === EURC) outEurc += amountOut;
  }
  const last = logs.length ? logs[logs.length - 1] : null;
  return { count, inUsdc, inEurc, outUsdc, outEurc, last, from, to: latest };
}

async function orderLatency() {
  let pending = null;
  try {
    const r = await fetch(`${KEEPER_API}/v1/mempool`);
    if (r.ok) pending = (await r.json())?.pending?.length ?? null;
  } catch {
    /* keeper API not reachable */
  }

  let avg = null;
  let med = null;
  let n = 0;
  if (DB_PATH && existsSync(DB_PATH)) {
    try {
      const { DatabaseSync } = await import("node:sqlite");
      const db = new DatabaseSync(DB_PATH, { readOnly: true });
      const rows = db
        .prepare(
          "SELECT created_at, filled_at FROM orders WHERE status='FILLED' AND filled_at IS NOT NULL ORDER BY filled_at DESC LIMIT 100",
        )
        .all();
      const d = rows
        .map((r) => Number(r.filled_at) - Number(r.created_at))
        .filter((x) => Number.isFinite(x) && x >= 0)
        .sort((a, b) => a - b);
      n = d.length;
      if (n) {
        avg = Math.round(d.reduce((a, b) => a + b, 0) / n);
        med = d[Math.floor(n / 2)];
      }
      db.close();
    } catch {
      /* DB not readable from here — skip */
    }
  }
  return { pending, avg, med, n };
}

async function rpcLatency() {
  const t0 = performance.now();
  await pc.getBlockNumber();
  return Math.round(performance.now() - t0);
}

async function computeMetrics() {
  const ex = await readExecutor();
  const recipient = ex.feeRecipient ?? process.env.FEE_RECIPIENT ?? null;
  const keeper = ex.keeper ?? process.env.KEEPER ?? null;

  const [treasury, gas, f, lat, rpcMs] = await Promise.all([
    Promise.all([balance(recipient, USDC), balance(recipient, EURC)]),
    Promise.all([balance(keeper, USDC), balance(keeper, EURC)]),
    fills(),
    orderLatency(),
    rpcLatency(),
  ]);

  return {
    ts: Date.now(),
    executor: EXECUTOR,
    feeBps: ex.feeBps,
    owner: ex.owner,
    recipient,
    keeper,
    treasury: { usdc: treasury[0], eurc: treasury[1] },
    gas: { usdc: gas[0], eurc: gas[1] },
    fills: f,
    order: lat,
    rpcMs,
  };
}

function formatMetrics(m) {
  const pct = m.feeBps != null ? (Number(m.feeBps) / 100).toFixed(2) : "?";
  const f = m.fills;
  const lat = m.order;
  const latLine =
    lat && lat.n > 0
      ? `• order latency <b>~${lat.avg}s</b> avg (median ${lat.med}s, n=${lat.n})`
      : "• order latency <i>n/a</i>";

  return [
    `📊 <b>Arc Smart Orders — metrics</b>`,
    `🧾 executor <code>${short(m.executor)}</code> · fee <b>${pct}%</b>`,
    ``,
    `💰 <b>Treasury</b> (feeRecipient <code>${short(m.recipient)}</code>)`,
    `• USDC <b>${fmt(m.treasury.usdc)}</b>`,
    `• EURC <b>${fmt(m.treasury.eurc)}</b>`,
    ``,
    `🔁 <b>Fills</b> (blocks ${f.from}→${f.to})`,
    `• count <b>${f.count}</b>`,
    `• in: <b>${fmt(f.inUsdc)} USDC</b> · <b>${fmt(f.inEurc)} EURC</b>`,
    `• out: ${fmt(f.outUsdc)} USDC · ${fmt(f.outEurc)} EURC`,
    f.last ? `• last: ${link(f.last.transactionHash)}` : `• last: <i>none in range</i>`,
    ``,
    `⛽ <b>Keeper</b> <code>${short(m.keeper)}</code>`,
    `• gas <b>${fmt(m.gas.usdc)} USDC</b>`,
    `• RPC latency <b>${m.rpcMs} ms</b>`,
    latLine,
    lat && lat.pending != null ? `• pending orders <b>${lat.pending}</b>` : null,
  ]
    .filter((l) => l !== null)
    .join("\n");
}

async function notify(text) {
  if (!TG_TOKEN || !TG_CHAT) return "no telegram target";
  try {
    const r = await fetch(`https://api.telegram.org/bot${TG_TOKEN}/sendMessage`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ chat_id: TG_CHAT, text, parse_mode: "HTML", disable_web_page_preview: true }),
    });
    return r.ok ? "telegram:ok" : `telegram:http ${r.status}`;
  } catch (e) {
    return `telegram:err ${e.message}`;
  }
}

async function once({ send }) {
  const m = await computeMetrics();
  const text = formatMetrics(m);
  console.log(text.replace(/<[^>]+>/g, ""));
  if (send) console.log("[metrics]", await notify(text));
  return m;
}

async function watch() {
  for (;;) {
    try {
      await once({ send: true });
    } catch (e) {
      console.error("[metrics]", e.message);
    }
    await sleep(METRICS_MS);
  }
}

async function serve() {
  if (!TG_TOKEN) {
    console.error(`[metrics] serve requires TELEGRAM_BOT_TOKEN (in ${ENV_FILE})`);
    process.exit(1);
  }
  let offset = 0;
  console.log("[metrics] listening for /metrics in Telegram…");
  for (;;) {
    try {
      const r = await fetch(`https://api.telegram.org/bot${TG_TOKEN}/getUpdates?timeout=30${offset ? `&offset=${offset}` : ""}`);
      const j = await r.json();
      if (j.ok) {
        for (const u of j.updates ?? []) {
          offset = u.update_id + 1;
          const msg = u.message ?? u.edited_message;
          const text = String(msg?.text ?? "").trim();
          const chat = String(msg?.chat?.id ?? "");
          if (ALLOWED_CHAT && chat !== ALLOWED_CHAT) continue;
          if (/^\/metrics(@\w+)?\b/.test(text)) {
            await notify(formatMetrics(await computeMetrics()));
          } else if (/^\/start\b|^\/help\b/.test(text)) {
            await notify("📊 <b>Arc metrics bot</b>\nSend /metrics for treasury, fills, volume and keeper health.");
          }
        }
      }
    } catch (e) {
      console.error("[metrics] poll:", e.message);
    }
    await sleep(1000);
  }
}

const cmd = process.argv[2] ?? "print";

if (cmd === "serve") {
  await serve();
} else if (cmd === "watch") {
  await watch();
} else if (cmd === "test") {
  console.log("[metrics]", await notify("✅ <b>Arc metrics bot</b> — test message. Try /metrics."));
} else if (cmd === "send") {
  await once({ send: true });
} else {
  await once({ send: false });
}
