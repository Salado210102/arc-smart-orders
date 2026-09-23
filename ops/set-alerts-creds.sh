#!/usr/bin/env bash
# Interactive setup for the launchpad alerts bot (Telegram) on the VPS.
# The token is read hidden and written ONLY to ops/launchpad-alerts.env (chmod 600).
#
#   bash ops/set-alerts-creds.sh
set -euo pipefail
cd "$(dirname "$0")/.."
ENV=ops/launchpad-alerts.env

echo "== Arc launchpad alerts — Telegram setup =="
echo "Get a bot token from @BotFather (/newbot)."
read -rs -p "Bot Token: " TOKEN; echo
read -r  -p "Chat ID (e.g. -1001234567890, or your user id): " CHAT; echo

if [ -z "${TOKEN:-}" ] || [ -z "${CHAT:-}" ]; then
  echo "✗ token and chat id are required"; exit 1
fi

cat > "$ENV" <<EOF
ARC_RPC=https://rpc.mainnet.arc.io
REGISTRY=0x8aE509565397C62a585c74aA44f7E3bFEab3Bb01
POLL_MS=30000
TELEGRAM_BOT_TOKEN=$TOKEN
TELEGRAM_CHAT_ID=$CHAT
EOF
chmod 600 "$ENV"
echo "✅ saved $ENV (chmod 600)"

echo "→ sending test message…"
node ops/launchpad-alerts.mjs test

echo "→ restarting PM2…"
pm2 restart arc-alerts >/dev/null 2>&1 || pm2 start ops/launchpad-alerts.ecosystem.config.cjs >/dev/null 2>&1
sleep 2
pm2 logs arc-alerts --lines 6 --nostream
