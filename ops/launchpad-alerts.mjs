// Launchpad alerts bot — posts new-agent launches (and graduation) to Telegram and/or Discord.
// Plain Node (ESM) using the repo's viem. Run:  node ops/launchpad-alerts.mjs
//
// Env (at least one target required):
//   ARC_RPC               default https://rpc.mainnet.arc.io
//   REGISTRY              default 0x8aE509565397C62a585c74aA44f7E3bFEab3Bb01 (Arc mainnet)
//   POLL_MS               default 30000
//   START_BLOCK           optional; default = current block (no historical backfill)
//   STATE_FILE            default ops/.alerts-state.json
//   TELEGRAM_BOT_TOKEN    from @BotFather
//   TELEGRAM_CHAT_ID      channel/group id (e.g. -1001234567890)
//   DISCORD_WEBHOOK_URL   channel webhook
import { createPublicClient, http, parseAbiItem } from "viem";
import { readFileSync, writeFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";

const RPC = process.env.ARC_RPC ?? "https://rpc.mainnet.arc.io";
const REGISTRY = (process.env.REGISTRY ?? "0x8aE509565397C62a585c74aA44f7E3bFEab3Bb01");
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
  if (TG_TOKEN && TG_CHAT) {
    try {
      await fetch(`https://api.telegram.org/bot${TG_TOKEN}/sendMessage`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ chat_id: TG_CHAT, text, parse_mode: "HTML", disable_web_page_preview: true }),
      });
    } catch (e) {
      console.error("telegram error:", e.message);
    }
  }
  if (DISCORD) {
    try {
      await fetch(DISCORD, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ content: text.replace(/<[^>]+>/g, "") }),
      });
    } catch (e) {
      console.error("discord error:", e.message);
    }
  }
}

async function tick() {
  const state = loadState();
  try {
    const latest = await client.getBlockNumber();
    if (!state.lastBlock) {
      state.lastBlock = process.env.START_BLOCK ? Number(process.env.START_BLOCK) - 1 : Number(latest);
      saveState(state);
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
      await notify(msg);
    }
    state.lastBlock = Number(latest);
    saveState(state);
  } catch (e) {
    console.error("[alerts]", e.message);
  } finally {
    setTimeout(tick, POLL_MS);
  }
}

console.log(
  `[alerts] watching ${REGISTRY} on ${RPC} · targets: ${[TG_TOKEN && TG_CHAT ? "telegram" : null, DISCORD ? "discord" : null].filter(Boolean).join(", ") || "NONE (set TELEGRAM_* or DISCORD_WEBHOOK_URL)"}`,
);
void tick();
