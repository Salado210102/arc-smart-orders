# Keeper — deployment on the VPS (same box as BasePump)

The Arc Smart Orders keeper runs a **Fastify HTTP API** (`POST /v1/orders`, `/health`, WebSocket) and a
**worker loop** that fills signed orders through the mainnet `OrderExecutor`. It is **stateless-adjacent**
(SQLite at `keeper/data/orders.db`) and coexists with BasePump on the same VPS — BasePump uses Docker under
`/opt/basepump`; the keeper uses PM2/systemd in `/opt/arc-smart-orders`, listening on **port 8788** (no clash).

> ⚠️ **Current mainnet state:** the `OrderExecutor` is live and the keeper is configured, but the **swap
> venue is still pending** (StableFX `sales@circle.com` request in flight; no public AMM on Arc). Until a
> fillable venue is wired, run the keeper with **`DRY=1`** (API up + worker logs, no on-chain fills).

---

## 1. Prerequisites (Ubuntu)

```bash
# Node 22+ (BasePump likely already has it) + PM2
node -v
npm i -g pm2
```

## 2. Get the code (main branch)

```bash
sudo mkdir -p /opt/arc-smart-orders
sudo chown "$USER" /opt/arc-smart-orders
git clone https://github.com/Salado210102/arc-smart-orders.git /opt/arc-smart-orders
cd /opt/arc-smart-orders
# npm workspaces (sdk + keeper + apps). Install at the root:
npm install
```

## 3. Configure `.env` (mainnet)

```bash
cd /opt/arc-smart-orders/keeper
cp .env.example .env
chmod 600 .env
```

Fill `keeper/.env`:

```ini
ARC_RPC=https://rpc.mainnet.arc.io
CHAIN_ID=5042
KEEPER_PK=0x...          # the keeper hot wallet (B, 0x327f…50bC) — must be funded with USDC on Arc mainnet
EXECUTOR=0x9b3A990D1a31ff5E01DdB8702E10F2529811Fdb7
ROUTER=0x0000000000000000000000000000000000000000   # venue pending -> DRY=1
MIN_FEE_GWEI=20
LOOP_MS=8000
DRY=1
PORT=8788
DB_PATH=data/orders.db
```

- **`KEEPER_PK`** must match the `OrderExecutor.keeper()` = `0x327fF705C1De5Ffd071bDF7E43069398507E50bC`
  (the `arc-keeper-b.json` key). It pays gas in **USDC** — fund it on Arc mainnet before going live.
- Keep `DRY=1` until the venue is wired; set `DRY=0` to enable real fills.

## 4. Run with PM2 (recommended)

```bash
cd /opt/arc-smart-orders
pm2 start keeper/ecosystem.config.cjs
pm2 save
pm2 startup   # follow the printed command to enable on boot
pm2 status    # arc-keeper  online
```

Logs:
```bash
pm2 logs arc-keeper
```

## 5. (Alternative) systemd

```bash
sudo cp /opt/arc-smart-orders/keeper/arc-keeper.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now arc-keeper
journalctl -u arc-keeper -f
```
The unit already points to `/opt/arc-smart-orders/keeper` and reads `.env` there.

## 6. Verify

```bash
curl -s http://localhost:8788/health
# {"ok":true,"chainId":5042,"executor":"0x9b3A…1Fdb7"}
```

## 7. Go live checklist (when the venue exists)

- [ ] `DRY=0` in `keeper/.env`.
- [ ] `ROUTER` = the real swap venue (StableFX `FxEscrow` `0xe2E5F173…DFe6` once permissioned, or a public AMM).
- [ ] `KEEPER_PK` wallet funded with USDC on Arc mainnet (gas).
- [ ] `pm2 restart arc-keeper` and watch `pm2 logs arc-keeper` for `FILLED`.

## Security notes

- The keeper key is **hot + low-privilege** (`onlyKeeper`): it can fill orders but **cannot** change
  fee/keeper/targets — those are `onlyOwner` (the Safe `0x0FBFAF…7e93`).
- Never commit `keeper/.env` (gitignored). `.secrets/` is also gitignored.
- BasePump and the Arc keeper are independent processes; do not share ports.
