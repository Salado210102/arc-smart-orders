# Production checklist — MEV suite

> Steps to move the MEV modules from **Draft/Testnet** to **Mainnet Live** on Arc (5042), once Arc/Circle
> expose the required venue, oracle and flash-loan infrastructure. Nothing here should run before the
> **hard gates** (§1) are all green.

---

## 1 · Hard gates (do NOT go live until every box is checked)

### 1.1 · Security
- [ ] **Independent audit** of `src/mev/*` completed; all Critical/High findings fixed.
- [ ] Owner is the **Safe 2/2** `0x0FBFAF7069B45Dd9c16AdD8a04Bf556046EA7e93` (not an EOA).
- [ ] Keeper hot key is **separate**, low-balance, and can only call `execute*` (owner-only) via an
      approved role; compromised keeper cannot withdraw (owner-only `emergencyWithdraw`).
- [ ] `emergencyWithdraw` runbook tested on a fork.
- [ ] Rate-limits / caps: max `debtToCover`, max `amountIn`, max JIT capital, per-day notional.
- [ ] Monitoring + a **kill switch** (pause by revoking the keeper role / draining via `emergencyWithdraw`).

### 1.2 · Protocol dependencies (per module)
| Module | Needs | Verify |
|---|---|---|
| Liquidations | A **flash-loan provider** exposing a Balancer-V2-style ABI (a Morpho Blue adapter counts) | `flashLoan(...)` callable, fee known |
| Liquidations | A **lending pool** exposing `getUserAccountData` + `liquidationCall` | HF readable, liquidation bonus > flash fee + swap slippage |
| Oracle arb | A Uniswap v3 **pool with liquidity** + **SwapRouter02** | pool exists, route has depth, fee known |
| Oracle arb | A **live oracle** (Pyth/Chainlink) with a reliable feed | `latestAnswer`/update cadence < block time |
| JIT | **NonfungiblePositionManager** + pools with volume | NFPM mint/burn works, `tickSpacing` known |
| JIT | A **bundler / ordering path** (mint+swap+burn atomic) | otherwise JIT is not viable |

### 1.3 · Real-contract fork tests
- [ ] Add **mainnet-fork tests** (like `test/DeployMainnetFork.t.sol`) hitting the real provider, pool, oracle
      and NFPM before any live tx. Keep them behind env flags so CI stays green.

---

## 2 · Production environment (`bots/.env`, chmod 600)

```ini
ARC_RPC=https://rpc.mainnet.arc.io
USDC=0x3600000000000000000000000000000000000000

# --- shared ---
KEEPER_PK=0x...                      # hot key (onlyOwner on the modules); low balance
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...

# --- module 1: liquidations ---
LENDING_POOL=0x...                   # Aave-v3/Morpho-style pool
EXECUTOR=0x...                       # ArcLiquidationKeeper
COLLATERAL_ASSET=0x...               # e.g. cirBTC
SWAP_FEE=500
DISCOVER_BORROWERS=1
LOOKBACK_BLOCKS=50000
HF_THRESHOLD=1.0
MIN_PROFIT_USDC=0.10
POLL_SECONDS=15

# --- module 2: oracle arbitrage ---
ARB_EXECUTOR=0x...                   # ArcOracleArbitrage
ORACLE=0x...                         # Pyth/Chainlink feed
POOL=0x...                           # Uniswap v3 pool (shared)
TOKEN_MID=0x...                      # e.g. WETH
FEE_A=500
FEE_B=500
THRESHOLD_BPS=50
MIN_INPUT_USDC=1
MAX_INPUT_USDC=5000

# --- module 3: JIT ---
JIT_EXECUTOR=0x...                   # ArcJITLiquidity
TICK_SPACING=10
MIN_SWAP_USD=100000
PRICE_TOKEN1_IN_TOKEN0=2500
GAS_COST_USD=1
MIN_PROFIT_USD=10
CAPITAL0=50000
CAPITAL1=20
```

> Never commit `.env`. Keys live only on the VPS (`chmod 600`) or in a secrets manager.

---

## 3 · Deploy the contracts (via the Safe + Foundry)

```bash
cd contracts
# Deploy each module with owner = Safe
export CONFIRM_MAINNET=1
forge script script/DeployMEV.s.sol --rpc-url https://rpc.mainnet.arc.io --broadcast
# Then, from the Safe (owners A+C), set the wiring:
#   - provider / lendingPool / swapRouter  (safe-exec.mjs)
#   - approve the keeper key as the allowed caller (or transfer ownership to a scoped role)
```
- [ ] `onlyOwner` wired to the Safe.
- [ ] `setConfig(...)` executed by the Safe for each module.
- [ ] One **dry-run** (`KEEPER_PK` unset) → monitor-only for 24–48 h.

---

## 4 · Run the bots 24/7 (VPS)

### 4.1 · Docker (recommended isolation)
`bots/Dockerfile`:
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY bots/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY bots/ ./
# one process per module; override CMD per service
CMD ["python", "liquidation_monitor.py"]
```
`bots/docker-compose.yml`:
```yaml
services:
  mev-liquidations:
    build: { context: .., dockerfile: bots/Dockerfile }
    command: ["python", "liquidation_monitor.py"]
    env_file: .env
    restart: unless-stopped
  mev-oracle-arb:
    build: { context: .., dockerfile: bots/Dockerfile }
    command: ["python", "oracle_arb_monitor.py"]
    env_file: .env
    restart: unless-stopped
  mev-jit:
    build: { context: .., dockerfile: bots/Dockerfile }
    command: ["python", "jit_liquidity_monitor.py"]
    env_file: .env
    restart: unless-stopped
```
```bash
cd bots && docker compose up -d --build
docker compose logs -f mev-liquidations
```

### 4.2 · PM2 (no Docker)
`bots/mev.ecosystem.config.cjs`:
```js
module.exports = { apps: [
  { name: "mev-liquidations", script: "bots/liquidation_monitor.py", interpreter: "python3", env_file: "bots/.env" },
  { name: "mev-oracle-arb",  script: "bots/oracle_arb_monitor.py",  interpreter: "python3", env_file: "bots/.env" },
  { name: "mev-jit",         script: "bots/jit_liquidity_monitor.py", interpreter: "python3", env_file: "bots/.env" },
]};
```
```bash
pm2 start bots/mev.ecosystem.config.cjs && pm2 save && pm2 startup
pm2 logs mev-liquidations
```

### 4.3 · systemd (one unit per module)
```ini
[Unit]
Description=Arc MEV liquidations
After=network-online.target
[Service]
WorkingDirectory=/var/www/arc-smart-orders
EnvironmentFile=/var/www/arc-smart-orders/bots/.env
ExecStart=/usr/bin/python3 bots/liquidation_monitor.py
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
```

---

## 5 · Go-live verification

- [ ] Bots run in **monitor-only** (no `KEEPER_PK`) and log sensible opportunities for 24–48 h.
- [ ] Enable `KEEPER_PK` for **one** module at a time; start with tiny caps.
- [ ] First live ops verified on the Arc explorer (tx succeeds, profit to the Safe, no residue).
- [ ] Telegram alerts firing on detection + success/failure.
- [ ] History files (`bots/*_history.json`) rotate/size-capped.

## 6 · Rollback / incident response
- [ ] Revoke the keeper (Safe tx to remove the allowed role / `setConfig` to a null provider).
- [ ] `emergencyWithdraw(token, Safe)` from each module for any residue.
- [ ] Stop the bot (`pm2 stop` / `docker compose stop`).

## 7 · What must exist first (ecosystem dependencies)
1. A **flash-loan provider** on Arc with a Balancer-style ABI (or a Morpho Blue adapter).
2. A **lending pool** (Aave v3 / Morpho) with liquidatable positions.
3. A **production oracle** feed with sub-block updates.
4. **Uniswap v3 pools** with enough depth for the collateral/route.
5. A **bundler / ordering path** for JIT (otherwise module 3 is not viable).
