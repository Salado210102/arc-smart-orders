# Alerts bot — Arc Launchpad (Telegram / Discord)

Watches `AgentRegistry.AgentRegistered` on **Arc mainnet** and posts a message for every new agent launch.
It also watches **`OrderExecutor.OrderExecuted`** and posts a **Telegram alert for every smart-order fill**
(owner, tokens in/out, and the explorer tx link).

- **Runs on the VPS** (`root@2.29.24.106`), PM2 process **`arc-alerts`** (auto-restart + systemd boot).
- **Code:** `ops/launchpad-alerts.mjs` · **PM2 config:** `ops/launchpad-alerts.ecosystem.config.cjs`
- **Config (not committed):** `ops/launchpad-alerts.env` (`chmod 600`) — loaded automatically by the script.

## Env (in `ops/launchpad-alerts.env`)
```ini
ARC_RPC=https://rpc.mainnet.arc.io
REGISTRY=0x8aE509565397C62a585c74aA44f7E3bFEab3Bb01
POLL_MS=30000
TELEGRAM_BOT_TOKEN=...     # @BotFather
TELEGRAM_CHAT_ID=...       # e.g. 8789837533
# DISCORD_WEBHOOK_URL=...  # optional alternative
```

## Test (send a message now)
```bash
cd /var/www/arc-keeper && node ops/launchpad-alerts.mjs test
# → [alerts] test → telegram:ok
```

## Change credentials (secure — token never hits the shell history or a chat)
```bash
cd /var/www/arc-keeper && bash ops/set-alerts-creds.sh
# prompts hidden for the token, writes the .env, sends the test, restarts PM2
pm2 restart arc-alerts
pm2 logs arc-alerts --lines 8 --nostream
```

## Ops
```bash
pm2 status
pm2 logs arc-alerts
pm2 restart arc-alerts
```

## Notes
- The bot resumes from the last scanned block (`ops/.alerts-state.json`), so it does not replay old events.
- Message includes: agent id, token, curve, creator + a link to the DApp.
- Get the Chat ID: message your bot, then open `https://api.telegram.org/bot<TOKEN>/getUpdates` and read `chat.id`.

---

## Metrics bot (`arc-metrics`)

Realtime metrics over the **same** Telegram bot, computed from the executor's `OrderExecuted` logs +
the keeper DB.

- **Code:** `ops/keeper-metrics-bot.mjs` · **PM2 config:** `ops/keeper-metrics-bot.ecosystem.config.cjs`
- **Modes:** `print` (default) · `send` · `watch` · `serve` (`/metrics` replies) · **`daemon`** (24/7 = periodic push + `/metrics`)
- **Reports:** (a) `feeRecipient` USDC/EURC balance · (b) fills + cumulative volume + last fill · (c) keeper gas + RPC/order latency

### Start / restart (VPS `/var/www/arc-keeper`)
```bash
cd /var/www/arc-keeper
pm2 start   ops/keeper-metrics-bot.ecosystem.config.cjs   # first time (daemon mode)
pm2 restart arc-metrics                                   # after config/env/code changes
pm2 save                                                  # persist across reboots
pm2 logs arc-metrics --lines 20 --nostream
```

### Try it
```bash
node ops/keeper-metrics-bot.mjs print   # one-shot to stdout
node ops/keeper-metrics-bot.mjs send    # one-shot to Telegram
# then in Telegram:  /metrics
```

### Optional env (append to `ops/launchpad-alerts.env`)
```ini
METRICS_MS=3600000        # periodic push interval (0 = only reply on-demand /metrics)
METRICS_CHAT_ID=...       # restrict /metrics to this chat (defaults to TELEGRAM_CHAT_ID)
DB_PATH=keeper/data/orders.db   # keeper SQLite (relative to repo root) → order latency
```

> Only **one** process may long-poll `getUpdates` per bot token — keep a single `arc-metrics` in `daemon`/`serve`.
