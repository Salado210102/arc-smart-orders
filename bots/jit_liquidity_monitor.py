#!/usr/bin/env python3
"""Arc MEV — JIT liquidity monitor (Arc mainnet, chain 5042).

Detects large swaps on a Uniswap v3 pool, computes the optimal 1-tick range around the current price for
the upcoming order, simulates `ArcJITLiquidity.executeJIT` (`eth_call` + `estimate_gas`) and — when the
KEEPER_PK is set — sends the atomic mint->swap->collect->burn transaction. Alerts to Telegram and logs a
JSON history.

Env (see bots/.env.example):
  ARC_RPC, JIT_EXECUTOR, USDC, TOKEN1, POOL, TICK_SPACING, FEE, MIN_SWAP_USD, PRICE_TOKEN1_IN_TOKEN0,
  GAS_COST_USD, MIN_PROFIT_USD, CAPITAL0, CAPITAL1, POLL_SECONDS, HISTORY_FILE,
  KEEPER_PK, OWNER (optional), TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import time

import aiohttp
from eth_account import Account
from web3 import AsyncWeb3
from web3.providers.async_rpc import AsyncHTTPProvider

# ----------------------------------------------------------------------------- env
def load_env(path: str = "bots/.env") -> None:
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
JIT = os.getenv("JIT_EXECUTOR", "")
USDC = os.getenv("USDC", "0x3600000000000000000000000000000000000000")
TOKEN1 = os.getenv("TOKEN1", "")
POOL = os.getenv("POOL", "")
TICK_SPACING = int(os.getenv("TICK_SPACING", "10"))
FEE = int(os.getenv("FEE", "500"))
MIN_SWAP_USD = float(os.getenv("MIN_SWAP_USD", "100000"))  # only target whale swaps
PRICE = int(float(os.getenv("PRICE_TOKEN1_IN_TOKEN0", "2500")) * 1e6)  # USDC (6-dec) per token1
GAS_COST = int(float(os.getenv("GAS_COST_USD", "1")) * 1e6)
MIN_PROFIT = int(float(os.getenv("MIN_PROFIT_USD", "10")) * 1e6)
CAPITAL0 = int(float(os.getenv("CAPITAL0", "50000")) * 1e6)  # USDC to deploy
CAPITAL1 = int(float(os.getenv("CAPITAL1", "20")) * 1e18)  # token1 to deploy
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "12"))
HISTORY_FILE = os.getenv("HISTORY_FILE", "bots/jit_history.json")
KEEPER_PK = os.getenv("KEEPER_PK", "")
OWNER_ENV = os.getenv("OWNER", "")
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")

POOL_ABI = [
    {"name": "slot0", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [
        {"name": "sqrtPriceX96", "type": "uint160"}, {"name": "tick", "type": "int24"},
        {"name": "a", "type": "uint16"}, {"name": "b", "type": "uint16"}, {"name": "c", "type": "uint16"},
        {"name": "d", "type": "uint8"}, {"name": "e", "type": "bool"}]},
    {"name": "token0", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address"}]},
    {"name": "liquidity", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint128"}]},
]
JIT_ABI = [
    {"name": "owner", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address"}]},
    {"name": "executeJIT", "type": "function", "stateMutability": "nonpayable", "inputs": [
        {"name": "p", "type": "tuple", "components": [
            {"name": "pool", "type": "address"}, {"name": "nfpm", "type": "address"}, {"name": "token1", "type": "address"},
            {"name": "poolFee", "type": "uint24"}, {"name": "tickLower", "type": "int24"}, {"name": "tickUpper", "type": "int24"},
            {"name": "amount0Desired", "type": "uint256"}, {"name": "amount1Desired", "type": "uint256"},
            {"name": "amount0Min", "type": "uint256"}, {"name": "amount1Min", "type": "uint256"},
            {"name": "swapTarget", "type": "address"}, {"name": "swapData", "type": "bytes"},
            {"name": "priceToken1InToken0", "type": "uint256"}, {"name": "gasCost", "type": "uint256"},
            {"name": "minProfit", "type": "uint256"}, {"name": "deadline", "type": "uint256"}]}],
     "outputs": [{"name": "profit", "type": "uint256"}]},
]
SWAP_TOPIC = AsyncWeb3.keccak(text="Swap(address,address,int256,int256,uint160,uint128,int24)").hex()
SWAP_EVENT_ABI = [
    {"name": "Swap", "type": "event", "anonymous": False, "inputs": [
        {"name": "sender", "type": "address", "indexed": True}, {"name": "recipient", "type": "address", "indexed": True},
        {"name": "amount0", "type": "int256", "indexed": False}, {"name": "amount1", "type": "int256", "indexed": False},
        {"name": "sqrtPriceX96", "type": "uint160", "indexed": False}, {"name": "liquidity", "type": "uint128", "indexed": False},
        {"name": "tick", "type": "int24", "indexed": False}]},
]

w3 = AsyncWeb3(AsyncHTTPProvider(RPC))
_last: dict[str, float] = {}
_last_block = 0


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


async def _idle(missing: list[str]) -> None:
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


def price_to_tick(price_token1_in_token0_human: float) -> int:
    return int(math.log(price_token1_in_token0_human) / math.log(1.0001))


def align_tick(tick: int, spacing: int) -> int:
    return (tick // spacing) * spacing


def optimal_range(order_usd: float, pool_liquidity: int, current_tick: int) -> tuple[int, int]:
    """1-tick-wide range centred on the current price (JIT). For a large order the price crosses the tick,
    so the position captures the full fee of the crossing leg."""
    lower = align_tick(current_tick, TICK_SPACING)
    upper = lower + TICK_SPACING
    if current_tick >= upper:  # centre the range on the current tick
        lower = align_tick(current_tick, TICK_SPACING)
        upper = lower + TICK_SPACING
    return lower, upper


async def pool_state() -> tuple[int, int]:
    pool = w3.eth.contract(address=AsyncWeb3.to_checksum_address(POOL), abi=POOL_ABI)
    slot0 = await pool.functions.slot0().call()
    liq = await pool.functions.liquidity().call()
    return int(slot0[1]), int(liq)  # (tick, liquidity)


async def sim_jit(lower: int, upper: int) -> int:
    jit = w3.eth.contract(address=AsyncWeb3.to_checksum_address(JIT), abi=JIT_ABI)
    owner = OWNER_ENV or await jit.functions.owner().call()
    p = (
        AsyncWeb3.to_checksum_address(POOL), AsyncWeb3.ZERO_ADDRESS, AsyncWeb3.to_checksum_address(TOKEN1),
        FEE, lower, upper, CAPITAL0, CAPITAL1, 0, 0, AsyncWeb3.ZERO_ADDRESS, b"",
        PRICE, GAS_COST, MIN_PROFIT, int(time.time()) + 600,
    )
    try:
        return int(await jit.functions.executeJIT(p).call({"from": owner}))
    except Exception as e:  # noqa: BLE001
        _log(f"sim revert: {str(e)[:80]}")
        return -1


async def handle_whale(amount_usd: float) -> None:
    current_tick, liq = await pool_state()
    if not JIT:
        await notify(f"🌊 <b>Whale swap detected</b>\n≈ <b>${amount_usd:,.0f}</b> on the pool (monitor-only — set JIT_EXECUTOR to simulate/execute)")
        return
    lower, upper = optimal_range(amount_usd, liq, current_tick)
    profit = await sim_jit(lower, upper)
    if profit <= MIN_PROFIT:
        _log(f"whale {amount_usd:,.0f} USD but sim profit {profit / 1e6:.4f} <= min")
        return
    await notify(
        f"🌊 <b>JIT opportunity</b>\n"
        f"target swap ≈ <b>${amount_usd:,.0f}</b>\n"
        f"range ticks <b>[{lower}, {upper})</b> · tick {current_tick}\n"
        f"sim profit <b>{profit / 1e6:.4f} USDC</b>"
        + ("\n⏳ sending…" if KEEPER_PK else "\n🔒 monitor-only (no KEEPER_PK)")
    )
    if not KEEPER_PK:
        return
    jit = w3.eth.contract(address=AsyncWeb3.to_checksum_address(JIT), abi=JIT_ABI)
    p = (
        AsyncWeb3.to_checksum_address(POOL), AsyncWeb3.ZERO_ADDRESS, AsyncWeb3.to_checksum_address(TOKEN1),
        FEE, lower, upper, CAPITAL0, CAPITAL1, 0, 0, AsyncWeb3.ZERO_ADDRESS, b"",
        PRICE, GAS_COST, MIN_PROFIT, int(time.time()) + 600,
    )
    try:
        acct = Account.from_key(KEEPER_PK)
        tx = await jit.functions.executeJIT(p).build_transaction(
            {"from": acct.address, "nonce": await w3.eth.get_transaction_count(acct.address), "value": 0}
        )
        gas = await w3.eth.estimate_gas(tx)
        base = await w3.eth.gas_price
        tx.update({"gas": int(gas * 12 // 10), "maxFeePerGas": base * 2 + 1_000_000_000, "maxPriorityFeePerGas": 1_000_000_000, "chainId": await w3.eth.chain_id, "type": 2})
        signed = acct.sign_transaction(tx)
        raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
        h = await w3.eth.send_raw_transaction(raw)
        rcpt = await w3.eth.wait_for_transaction_receipt(h, timeout=60)
        await notify(f"✅ <b>JIT executed</b>\ntx <code>{h.hex()}</code> · status {rcpt.status} · profit ≈ {profit / 1e6:.4f} USDC")
        _append({"ts": int(time.time()), "swap_usd": amount_usd, "lower": lower, "upper": upper, "profit": profit, "tx": h.hex(), "status": rcpt.status})
    except Exception as e:  # noqa: BLE001
        await notify(f"❌ <b>JIT failed</b>\n{str(e)[:160]}")


def _append(entry: dict) -> None:
    try:
        data = json.load(open(HISTORY_FILE, encoding="utf-8")) if os.path.exists(HISTORY_FILE) else []
        data.append(entry)
        json.dump(data[-500:], open(HISTORY_FILE, "w", encoding="utf-8"), indent=2)
    except Exception as e:  # noqa: BLE001
        _log(f"history error: {e}")


async def scan() -> None:
    global _last_block
    latest = await w3.eth.block_number
    if _last_block == 0:
        _last_block = latest
        return
    if latest <= _last_block:
        return
    logs = await w3.eth.get_logs(
        {"address": AsyncWeb3.to_checksum_address(POOL), "fromBlock": _last_block + 1, "toBlock": latest, "topics": [SWAP_TOPIC]}
    )
    _last_block = latest
    contract = w3.eth.contract(abi=SWAP_EVENT_ABI)
    for lg in logs:
        ev = contract.events.Swap().process_log(lg)
        a0 = abs(int(ev["args"]["amount0"]))  # USDC (6-dec) if token0 = USDC
        usd = a0 / 1e6
        if usd < MIN_SWAP_USD:
            continue
        key = f"{usd:.0f}"
        if time.time() - _last.get(key, 0) < 30:
            continue
        _last[key] = time.time()
        _log(f"whale swap {usd:,.0f} USDC in block {latest}")
        await handle_whale(usd)


async def main() -> None:
    _log(f"Arc JIT monitor · RPC={RPC} · pool={POOL or '—'} · jit={JIT or '—'}")
    _log("mode: " + ("LIVE (sends JIT)" if KEEPER_PK else "MONITOR-ONLY (no KEEPER_PK)"))
    missing = [r for r in ("POOL", "TOKEN1") if not os.getenv(r)]
    if missing:
        await _idle(missing)
        return
    while True:
        try:
            await scan()
        except Exception as e:  # noqa: BLE001
            _log(f"error: {e}")
        await asyncio.sleep(POLL_SECONDS)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        _log("stopped")
