# Alerts bot — Arc Launchpad (Telegram / Discord)

Watches `AgentRegistry.AgentRegistered` on **Arc mainnet** and posts a message for every new agent launch.

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
