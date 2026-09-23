# Keeper — deployment on the VPS (same box as BasePump)

The Arc Smart Orders keeper runs a **Fastify HTTP API** (`POST /v1/orders`, `/health`, WebSocket) and a
**worker loop** that fills signed orders through the mainnet `OrderExecutor`. It is **stateless-adjacent**
(SQLite at `keeper/data/orders.db`) and coexists with BasePump on the same VPS — BasePump uses Docker under
`/opt/basepump`; the keeper uses PM2/systemd in `/var/www/arc-keeper`, listening on **port 8788** (no clash).

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
sudo mkdir -p /var/www/arc-keeper
sudo chown "$USER" /var/www/arc-keeper
git clone https://github.com/Salado210102/arc-smart-orders.git /var/www/arc-keeper
cd /var/www/arc-keeper
# npm workspaces (sdk + keeper + apps). Install at the root:
npm install
```

## 3. Configure `.env` (mainnet)

```bash
cd /var/www/arc-keeper/keeper
cp .env.example .env
chmod 600 .env
```

Fill `keeper/.env`:

```ini
ARC_RPC=https://rpc.mainnet.arc.io
CHAIN_ID=5042
KEEPER_PK=0x...          # the keeper hot wallet (B, 0x327f…50bC) — must be funded with USDC on Arc mainnet
EXECUTOR=0x9b3a990d1a31Ff5E01ddB8702e10F2529811FDb7
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
cd /var/www/arc-keeper
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
sudo cp /var/www/arc-keeper/keeper/arc-keeper.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now arc-keeper
journalctl -u arc-keeper -f
```
The unit already points to `/var/www/arc-keeper/keeper` and reads `.env` there.

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

## 8. Fund the keeper on Arc mainnet (gas)

On Arc, **gas is paid in the native USDC** (18-decimal accounting). The keeper hot wallet
**B = `0x327fF705C1De5Ffd071bDF7E43069398507E50bC`** must hold a small native-USDC balance before you
set `DRY=0`, otherwise it cannot broadcast fills. Funding signer **A** must hold mainnet USDC.

### Option A — helper script
```bash
cd /var/www/arc-keeper
# KEY_FILE defaults to /root/.arc-deployer.json (signer A); AMOUNT defaults to 2ether (=2 USDC gas)
AMOUNT=1ether bash ops/fund-keeper.sh
```

### Option B — plain `cast`
```bash
RPC=https://rpc.mainnet.arc.io
B=0x327fF705C1De5Ffd071bDF7E43069398507E50bC

# 1) current gas balance (wei, 18 dec → /1e18 = USDC)
cast balance $B --rpc-url $RPC

# 2) send 2 USDC of gas from A (reads the key without echoing it)
export A_PK="$(jq -r .privateKey /root/.arc-deployer.json)"
cast send $B --value 2ether --private-key "$A_PK" --rpc-url $RPC

# 3) confirm
cast balance $B --rpc-url $RPC
```

> The ERC-20 USDC interface (`0x3600…0000`, 6 dec) is **not** the gas token — fund the **native**
> balance with `--value`. Verify from the DApp/metrics with `node ops/keeper-metrics-bot.mjs print`
> (look at the **Keeper** gas line).

Checklist:
- [ ] `cast balance <B>` > 0 (native USDC).
- [ ] `ops/keeper-metrics-bot.mjs print` shows the keeper gas.
- [ ] only then set `DRY=0` and `pm2 restart arc-keeper`.

## Security notes
- The keeper key is **hot + low-privilege** (`onlyKeeper`): it can fill orders but **cannot** change
  fee/keeper/targets — those are `onlyOwner` (the Safe `0x0FBFAF…7e93`).
- Never commit `keeper/.env` (gitignored). `.secrets/` is also gitignored.
- BasePump and the Arc keeper are independent processes; do not share ports.
