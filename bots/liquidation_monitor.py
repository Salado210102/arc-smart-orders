#!/usr/bin/env python3
"""Arc MEV — liquidation monitor (Arc mainnet, chain 5042).

Watches lending positions, flags insolvent ones (Health Factor < 1.0), and — when profitable — calls
`ArcLiquidationKeeper.executeLiquidation`, which borrows USDC via a flash loan, liquidates, swaps the
collateral on Uniswap v3 and keeps the net profit. **No upfront capital** is required: if the tx is not
profitable it reverts.

Safety first:
  * Builds and *simulates* the tx with `eth_call` before sending (never sends a reverting tx).
  * If `KEEPER_PK` is not set, it runs **monitor-only** (alerts, no sending).
  * Telegram alerts on risk detection and on successful liquidations.

Env (see bots/.env.example):
  ARC_RPC, LENDING_POOL, EXECUTOR, USDC, KEEPER_PK (optional),
  WATCHLIST (comma-separated) or WATCHLIST_FILE, DISCOVER_BORROWERS (0/1), LOOKBACK_BLOCKS,
  HF_THRESHOLD (default 1.0), MIN_PROFIT_USDC (default 0.01), COLLATERAL_ASSET, SWAP_FEE,
  POLL_SECONDS, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from typing import Iterable

import aiohttp
from eth_account import Account
from web3 import AsyncWeb3
try:
    from web3 import AsyncHTTPProvider  # web3 >= 7
except ImportError:  # web3 6.x
    from web3.providers.async_rpc import AsyncHTTPProvider

# ----------------------------------------------------------------------------- env
def load_env(path: str = "bots/.env") -> None:
    """Minimal .env loader (no dependency)."""
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


load_env()

RPC = os.getenv("ARC_RPC", "https://rpc.mainnet.arc.io")
LENDING_POOL = os.getenv("LENDING_POOL", "")
EXECUTOR = os.getenv("EXECUTOR", "")
USDC = os.getenv("USDC", "0x3600000000000000000000000000000000000000")
KEEPER_PK = os.getenv("KEEPER_PK", "")
COLLATERAL_ASSET = os.getenv("COLLATERAL_ASSET", "")
SWAP_FEE = int(os.getenv("SWAP_FEE", "500"))
HF_THRESHOLD = float(os.getenv("HF_THRESHOLD", "1.0"))
MIN_PROFIT = int(float(os.getenv("MIN_PROFIT_USDC", "0.01")) * 1e6)
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "30"))
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")
DISCOVER = os.getenv("DISCOVER_BORROWERS", "1") == "1"
LOOKBACK_BLOCKS = int(os.getenv("LOOKBACK_BLOCKS", "50000"))

# Aave-v3-style pool: read health factor. Works for any pool exposing getUserAccountData.
POOL_ABI = [
    {
        "name": "getUserAccountData",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "user", "type": "address"}],
        "outputs": [
            {"name": "totalCollateralBase", "type": "uint256"},
            {"name": "totalDebtBase", "type": "uint256"},
            {"name": "availableBorrowsBase", "type": "uint256"},
            {"name": "currentLiquidationThreshold", "type": "uint256"},
            {"name": "ltv", "type": "uint256"},
            {"name": "healthFactor", "type": "uint256"},
        ],
    }
]

KEEPER_ABI = [
    {
        "name": "executeLiquidation",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {
                "name": "p",
                "type": "tuple",
                "components": [
                    {"name": "collateralAsset", "type": "address"},
                    {"name": "debtAsset", "type": "address"},
                    {"name": "user", "type": "address"},
                    {"name": "debtToCover", "type": "uint256"},
                    {"name": "swapFee", "type": "uint24"},
                    {"name": "minProfit", "type": "uint256"},
                    {"name": "flashLoanFeeBps", "type": "uint256"},
                ],
            },
            {"name": "flashAmount", "type": "uint256"},
        ],
        "outputs": [],
    }
]

# Aave v3 Borrow(address indexed reserve, address indexed user, address indexed onBehalfOf, uint256 amount,
#              uint8 interestRateMode, uint256 borrowRate, uint16 referralCode)
BORROW_TOPIC = AsyncWeb3.keccak(text="Borrow(address,address,address,uint256,uint8,uint256,uint16)").hex()
BORROW_EVENT_ABI = [
    {
        "name": "Borrow",
        "type": "event",
        "anonymous": False,
        "inputs": [
            {"name": "reserve", "type": "address", "indexed": True},
            {"name": "user", "type": "address", "indexed": True},
            {"name": "onBehalfOf", "type": "address", "indexed": True},
            {"name": "amount", "type": "uint256", "indexed": False},
            {"name": "interestRateMode", "type": "uint8", "indexed": False},
            {"name": "borrowRate", "type": "uint256", "indexed": False},
            {"name": "referralCode", "type": "uint16", "indexed": False},
        ],
    }
]

w3 = AsyncWeb3(AsyncHTTPProvider(RPC))
_already_alerted: dict[str, float] = {}


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


async def _idle(missing: list[str]) -> None:
    """Stay alive (PM2 online) while required config is missing — avoids a restart loop."""
    _log("⏸ idle — missing: " + ", ".join(missing) + " (fill bots/.env and `pm2 restart <name>`)")
    while True:
        await asyncio.sleep(3600)


async def notify(text: str) -> None:
    if not (TG_TOKEN and TG_CHAT):
        _log(f"(no telegram) {text}")
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": TG_CHAT, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
                timeout=aiohttp.ClientTimeout(total=15),
            )
    except Exception as e:  # noqa: BLE001
        _log(f"telegram error: {e}")


# ----------------------------------------------------------------------------- accounts
async def watchlist() -> set[str]:
    addrs: set[str] = set()
    raw = os.getenv("WATCHLIST", "")
    for a in raw.split(","):
        a = a.strip().lower()
        if a.startswith("0x") and len(a) == 42:
            addrs.add(AsyncWeb3.to_checksum_address(a))
    file = os.getenv("WATCHLIST_FILE", "")
    if file and os.path.exists(file):
        for line in open(file, encoding="utf-8"):
            a = line.strip().lower()
            if a.startswith("0x") and len(a) == 42:
                addrs.add(AsyncWeb3.to_checksum_address(a))
    return addrs


async def discover_borrowers() -> set[str]:
    """Find recent borrowers from the pool's `Borrow` logs (best-effort)."""
    out: set[str] = set()
    if not (DISCOVER and LENDING_POOL):
        return out
    try:
        latest = await w3.eth.block_number
        frm = latest - LOOKBACK_BLOCKS if latest > LOOKBACK_BLOCKS else 0
        logs = await w3.eth.get_logs(
            {"address": AsyncWeb3.to_checksum_address(LENDING_POOL), "fromBlock": frm, "toBlock": latest, "topics": [BORROW_TOPIC]}
        )
        contract = w3.eth.contract(abi=BORROW_EVENT_ABI)
        for lg in logs:
            ev = contract.events.Borrow().process_log(lg)
            out.add(ev["args"]["onBehalfOf"])
    except Exception as e:  # noqa: BLE001
        _log(f"discover_borrowers: {e}")
    return out


# ----------------------------------------------------------------------------- core
async def health_factor(user: str) -> tuple[int, int]:
    pool = w3.eth.contract(address=AsyncWeb3.to_checksum_address(LENDING_POOL), abi=POOL_ABI)
    data = await pool.functions.getUserAccountData(user).call()
    return int(data[1]), int(data[5])  # (totalDebt, healthFactor scaled 1e18)


def build_calldata(user: str, debt_to_cover: int) -> str:
    keeper = w3.eth.contract(address=AsyncWeb3.to_checksum_address(EXECUTOR), abi=KEEPER_ABI)
    p = (
        AsyncWeb3.to_checksum_address(COLLATERAL_ASSET),
        AsyncWeb3.to_checksum_address(USDC),
        AsyncWeb3.to_checksum_address(user),
        debt_to_cover,
        SWAP_FEE,
        MIN_PROFIT,
        0,  # flashLoanFeeBps (provider-reported fee is used if > 0)
    )
    return keeper.functions.executeLiquidation(p, debt_to_cover).build_transaction({"gas": 0, "gasPrice": 0})["data"]


async def try_liquidate(user: str, debt: int) -> None:
    key = user.lower()
    if not EXECUTOR or not COLLATERAL_ASSET:
        await notify(f"⚠️ <b>At-risk position</b>\n<code>{user}</code>\nHF &lt; 1.0 (debt {debt / 1e6:.4f})\n<code>EXECUTOR/COLLATERAL_ASSET</code> not set — monitor only.")
        return

    data = build_calldata(user, debt)
    frm = keeper_addr = None
    try:
        keeper_addr = Account.from_key(KEEPER_PK).address if KEEPER_PK else AsyncWeb3.to_checksum_address(EXECUTOR)
    except Exception:  # noqa: BLE001
        keeper_addr = AsyncWeb3.to_checksum_address(EXECUTOR)

    tx = {"from": keeper_addr, "to": AsyncWeb3.to_checksum_address(EXECUTOR), "data": data}
    try:
        await w3.eth.call(tx)  # simulate: reverts if not profitable
    except Exception as e:  # noqa: BLE001
        _log(f"{user}: simulation reverted ({str(e)[:80]}) — not profitable")
        return

    await notify(
        f"🎯 <b>Liquidatable & profitable</b>\n<code>{user}</code>\nHF &lt; 1.0 · debt {debt / 1e6:.4f} USDC\n"
        + ("⏳ sending…" if KEEPER_PK else "🔒 monitor-only (no KEEPER_PK)")
    )
    if not KEEPER_PK:
        return

    try:
        acct = Account.from_key(KEEPER_PK)
        nonce = await w3.eth.get_transaction_count(acct.address)
        gas = await w3.eth.estimate_gas({"from": acct.address, "to": AsyncWeb3.to_checksum_address(EXECUTOR), "data": data})
        base = await w3.eth.gas_price
        signed = acct.sign_transaction(
            {
                "to": AsyncWeb3.to_checksum_address(EXECUTOR),
                "data": data,
                "value": 0,
                "nonce": nonce,
                "gas": int(gas * 12 // 10),
                "maxFeePerGas": base * 2 + 1_000_000_000,
                "maxPriorityFeePerGas": 1_000_000_000,
                "chainId": await w3.eth.chain_id,
                "type": 2,
            }
        )
        raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
        h = await w3.eth.send_raw_transaction(raw)
        rcpt = await w3.eth.wait_for_transaction_receipt(h, timeout=60)
        await notify(f"✅ <b>Liquidation executed</b>\n<code>{user}</code>\ntx <code>{h.hex()}</code> · status {rcpt.status}")
        _log(f"liquidation {h.hex()} status={rcpt.status}")
    except Exception as e:  # noqa: BLE001
        await notify(f"❌ <b>Liquidation failed</b>\n<code>{user}</code>\n{str(e)[:160]}")
        _log(f"liquidation error: {e}")


async def scan_once() -> None:
    users = await watchlist() | await discover_borrowers()
    _log(f"scanning {len(users)} accounts…")
    for user in users:
        try:
            debt, hf = await health_factor(user)
            if debt == 0:
                continue
            hf_f = hf / 1e18
            if hf_f < HF_THRESHOLD:
                last = _already_alerted.get(user.lower(), 0)
                if time.time() - last < 900:  # 15-min cooldown per user
                    continue
                _already_alerted[user.lower()] = time.time()
                _log(f"AT RISK {user} HF={hf_f:.4f} debt={debt / 1e6:.4f}")
                await try_liquidate(user, debt)
        except Exception as e:  # noqa: BLE001
            _log(f"{user}: {e}")


async def main() -> None:
    _log(f"Arc liquidation monitor · RPC={RPC} · pool={LENDING_POOL or '—'} · executor={EXECUTOR or '—'}")
    _log("mode: " + ("LIVE (sends liquidations)" if KEEPER_PK else "MONITOR-ONLY (no KEEPER_PK)"))
    if not LENDING_POOL:
        await _idle(["LENDING_POOL"])
        return
    while True:
        try:
            await scan_once()
        except Exception as e:  # noqa: BLE001
            _log(f"scan error: {e}")
        await asyncio.sleep(POLL_SECONDS)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        _log("stopped")
