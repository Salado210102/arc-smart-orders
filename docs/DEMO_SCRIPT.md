# 60-second demo script — Arc Smart Orders + Agent Launchpad

Goal: a tight ~60s clip showing the DApp flow **and** the Telegram alert firing in real time.

## Prep (before recording)
- Wallet on **Arc mainnet (5042)** with a little **USDC** (gas + the buy).
- **Telegram** open on your phone (or a second screen) with your alerts bot chat — so the alert is captured live.
- Screen recorder: **Xbox Game Bar** (`Win + G`) or **OBS**. Record at **1920×1080**.
- Two windows side by side: (1) the DApp, (2) Telegram.
- Pre-fill the Create form (name/ticker), and dismiss any popups.

## Timeline

| Time | On screen | Action / narration |
|---|---|---|
| **0:00–0:05** | DApp **Dashboard** (health badges visible) | *"Arc Smart Orders + Agent Launchpad — live on Arc mainnet."* Point at **RPC: Connected · ~300ms**, **Finality ~0.48s**, **Keeper: standby**. |
| **0:05–0:12** | Click **Connect Wallet** | Connect; show **Arc Mainnet · 5042** and USDC balance. |
| **0:12–0:30** | **Create** tab | Type name/ticker → **Launch**. Show the tx confirming. *"Launching an agent deploys its own USDC bonding curve — non-custodial."* |
| **0:30–0:45** | **Agents** → open the new agent → **Trade** | Do a small **Buy** on the curve; show the quote and the confirmation. |
| **0:45–0:55** | Cut to **Telegram** | The alert **"🚀 New agent launched on Arc"** arrives **live** (it fires on the launch). Highlight it. |
| **0:55–1:00** | Back to DApp **Dashboard** | *"Open source (MIT), 34/34 tests, Safe-owned. Links in bio."* End card: repo + DApp URLs. |

## Edit tips
- Add **captions** for each step (many watch muted).
- Speed-ramp the waiting (tx confirmations) to stay under 60s.
- End card (2s): `arc.basepump.dev` · `github.com/Salado210102/arc-smart-orders`.
- Export as **MP4 (1080p)**; for X, also a **GIF** of the 0:45–0:55 alert moment.

## Shot list (files)
1. Dashboard (health badges) — `arc-launchpad.png` is a good still.
2. Create form filled.
3. Agents list with the new agent.
4. Trade/buy confirmation.
5. Telegram alert (the money shot — proves the 24/7 bot works).
