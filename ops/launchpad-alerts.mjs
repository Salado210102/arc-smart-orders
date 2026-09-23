// Launchpad alerts bot — posts new-agent launches and low-keeper-gas alerts to Telegram and/or Discord.
// Plain Node (ESM) using the repo's viem.
//
//   node ops/launchpad-alerts.mjs         # run the watcher (24/7)
//   node ops/launchpad-alerts.mjs test     # send a one-off test message and exit
//
// Config: loaded from ops/launchpad-alerts.env (override path with ALERTS_ENV), else process env.
//   ARC_RPC, REGISTRY, POLL_MS, START_BLOCK, STATE_FILE
//   TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID      (from @BotFather)
//   DISCORD_WEBHOOK_URL                        (channel webhook)
//   KEEPER_ADDRESS, KEEPER_MIN_USDC            (mainnet low-gas alert; base units, 6 dec)
//   ARC_RPC_TESTNET, KEEPER_ADDRESS_TESTNET, KEEPER_MIN_USDC_TESTNET  (testnet low-gas alert)
//   BALANCE_CHECK_MS                           (default 3600000 = 1h)
import { createPublicClient, http, parseAbiItem } from "viem";
import { readFileSync, writeFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";

// ---- load env file first ----
const ENV_FILE = process.env.ALERTS_ENV ?? "ops/launchpad-alerts.env";
if (existsSync(ENV_FILE) && typeof process.loadEnvFile === "function") {
  try {
    process.loadEnvFile(ENV_FILE);
  } catch {
    /* ignore */
  }
}

const RPC = process.env.ARC_RPC ?? "https://rpc.mainnet.arc.io";
const REGISTRY = process.env.REGISTRY ?? "0x8aE509565397C62a585c74aA44f7E3bFEab3Bb01";
const POLL_MS = Number(process.env.POLL_MS ?? 30000);
const STATE_FILE = process.env.STATE_FILE ?? "ops/.alerts-state.json";
const TG_TOKEN = process.env.TELEGRAM_BOT_TOKEN;
const TG_CHAT = process.env.TELEGRAM_CHAT_ID;
const DISCORD = process.env.DISCORD_WEBHOOK_URL;
const EXPLORER = "https://explorer.arc.io";
const USDC = "0x3600000000000000000000000000000000000000";

// ---- low-gas monitor ----
const CHECK_MS = Number(process.env.BALANCE_CHECK_MS ?? 3600000);
const KEEPER = process.env.KEEPER_ADDRESS; // mainnet keeper
const KEEPER_MIN = BigInt(process.env.KEEPER_MIN_USDC ?? "1000000"); // 1 USDC
const RPC_TESTNET = process.env.ARC_RPC_TESTNET;
const KEEPER_TESTNET = process.env.KEEPER_ADDRESS_TESTNET;
const KEEPER_MIN_TESTNET = BigInt(process.env.KEEPER_MIN_USDC_TESTNET ?? "1000000");

const client = createPublicClient({ transport: http(RPC) });
const clientTestnet = RPC_TESTNET ? createPublicClient({ transport: http(RPC_TESTNET) }) : null;

const AGENT_REGISTERED = parseAbiItem(
  "event AgentRegistered(uint256 indexed agentId, address indexed token, address indexed curve, address creator, string metadataURI)",
);
const ERC20 = parseAbiItem("function balanceOf(address) view returns (uint256)");

function loadState() {
  try {
    return existsSync(STATE_FILE) ? JSON.parse(readFileSync(STATE_FILE, "utf8")) : {};
  } catch {
    return {};
  }
}
function saveState(s) {
  try {
    mkdirSync(dirname(STATE_FILE), { recursive: true });
    writeFileSync(STATE_FILE, JSON.stringify(s));
  } catch {
    /* ignore */
  }
}

async function notify(text) {
  const targets = [];
  if (TG_TOKEN && TG_CHAT) {
    try {
      const r = await fetch(`https://api.telegram.org/bot${TG_TOKEN}/sendMessage`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ chat_id: TG_CHAT, text, parse_mode: "HTML", disable_web_page_preview: true }),
      });
      targets.push(`telegram:${r.ok ? "ok" : "http " + r.status}`);
    } catch (e) {
      targets.push(`telegram:err ${e.message}`);
    }
  }
  if (DISCORD) {
    try {
      const r = await fetch(DISCORD, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ content: text.replace(/<[^>]+>/g, "") }),
      });
      targets.push(`discord:${r.ok ? "ok" : "http " + r.status}`);
    } catch (e) {
      targets.push(`discord:err ${e.message}`);
    }
  }
  return targets;
}

// ---- one-off test ----
if (process.argv.includes("test")) {
  if (!TG_TOKEN && !DISCORD) {
    console.error("[alerts] no target configured — set TELEGRAM_BOT_TOKEN+TELEGRAM_CHAT_ID or DISCORD_WEBHOOK_URL in", ENV_FILE);
    process.exit(1);
  }
  const sent = await notify("✅ <b>Arc launchpad alerts</b> — test message. Watching AgentRegistry + keeper gas on Arc.");
  console.log("[alerts] test →", sent.join(", "));
  process.exit(0);
}

// ---- keeper low-gas check ----
const lastLow = {}; // chain -> last alert ts (cooldown 6h)
async function lowGas(label, pc, keeper, min) {
  if (!pc || !keeper) return;
  try {
    const bal = await pc.readContract({ address: USDC, abi: ERC20, functionName: "balanceOf", args: [keeper] });
    const low = bal < min;
    const now = Date.now();
    if (low && (!lastLow[label] || now - lastLow[label] > 6 * 3600 * 1000)) {
      lastLow[label] = now;
      const usd = (Number(bal) / 1e6).toFixed(4);
      const need = (Number(min) / 1e6).toFixed(2);
      const msg =
        `⛽ <b>Low keeper gas — ${label}</b>\n` +
        `• keeper: <code>${keeper}</code>\n` +
        `• balance: <b>${usd} USDC</b> (min ${need})\n` +
        `• top up, or the keeper can't pay gas for fills.`;
      console.log(`[alerts] LOW GAS ${label}: ${usd} USDC`);
      await notify(msg);
    } else {
      console.log(`[alerts] ${label} keeper gas: ${(Number(bal) / 1e6).toFixed(4)} USDC`);
    }
  } catch (e) {
    console.error(`[alerts] balance(${label}):`, e.message);
  }
}

async function balanceTick() {
  await lowGas("mainnet", client, KEEPER, KEEPER_MIN);
  await lowGas("testnet", clientTestnet, KEEPER_TESTNET, KEEPER_MIN_TESTNET);
  setTimeout(balanceTick, CHECK_MS);
}

// ---- new-agent events ----
async function tick() {
  const state = loadState();
  try {
    const latest = await client.getBlockNumber();
    if (!state.lastBlock) {
      state.lastBlock = process.env.START_BLOCK ? Number(process.env.START_BLOCK) - 1 : Number(latest);
      saveState(state);
      console.log(`[alerts] primed at block ${state.lastBlock}`);
      return;
    }
    if (BigInt(state.lastBlock) >= latest) return;

    const logs = await client.getLogs({
      address: REGISTRY,
      event: AGENT_REGISTERED,
      fromBlock: BigInt(state.lastBlock) + 1n,
      toBlock: latest,
    });

    for (const log of logs) {
      const { agentId, token, curve, creator } = log.args;
      const msg =
        `🚀 <b>New agent launched on Arc</b>\n` +
        `• id: <code>${agentId}</code>\n` +
        `• token: <a href="${EXPLORER}/address/${token}">${token}</a>\n` +
        `• curve: <a href="${EXPLORER}/address/${curve}">${curve}</a>\n` +
        `• creator: <code>${creator}</code>\n` +
        `<a href="https://launchpad-neon-chi.vercel.app">Open Launchpad →</a>`;
      console.log(`[alert] agent ${agentId} token ${token}`);
      const sent = await notify(msg);
      if (sent.length) console.log("[alerts] →", sent.join(", "));
    }
    state.lastBlock = Number(latest);
    saveState(state);
  } catch (e) {
    console.error("[alerts]", e.message);
  } finally {
    setTimeout(tick, POLL_MS);
  }
}

const targets = [TG_TOKEN && TG_CHAT ? "telegram" : null, DISCORD ? "discord" : null].filter(Boolean);
console.log(`[alerts] registry ${REGISTRY} on ${RPC} · targets: ${targets.join(", ") || "NONE (configure " + ENV_FILE + ")"}`);
console.log(
  `[alerts] low-gas monitor: mainnet=${KEEPER ? "on" : "off"} testnet=${KEEPER_TESTNET ? "on" : "off"} (every ${CHECK_MS / 60000}min)`,
);
void tick();
if (KEEPER || KEEPER_TESTNET) void balanceTick();
