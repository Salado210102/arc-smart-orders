// Launchpad alerts bot — posts new-agent launches to Telegram and/or Discord.
// Plain Node (ESM) using the repo's viem.
//
//   node ops/launchpad-alerts.mjs         # run the watcher (24/7)
//   node ops/launchpad-alerts.mjs test     # send a one-off test message and exit
//
// Config: loaded from ops/launchpad-alerts.env (override path with ALERTS_ENV), else process env.
//   ARC_RPC, REGISTRY, POLL_MS, START_BLOCK, STATE_FILE
//   TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID      (from @BotFather)
//   DISCORD_WEBHOOK_URL                        (channel webhook)
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

const client = createPublicClient({ transport: http(RPC) });

const AGENT_REGISTERED = parseAbiItem(
  "event AgentRegistered(uint256 indexed agentId, address indexed token, address indexed curve, address creator, string metadataURI)",
);

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
  const sent = await notify("✅ <b>Arc launchpad alerts</b> — test message. Watching AgentRegistry on Arc mainnet.");
  console.log("[alerts] test →", sent.join(", "));
  process.exit(0);
}

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
console.log(`[alerts] watching ${REGISTRY} on ${RPC} · targets: ${targets.join(", ") || "NONE (configure " + ENV_FILE + ")"}`);
if (targets.length === 0) {
  console.log("[alerts] ⚠️  no targets yet — add TELEGRAM_* or DISCORD_WEBHOOK_URL to ops/launchpad-alerts.env, then: pm2 restart arc-alerts");
}
void tick();
