#!/usr/bin/env python3
"""Arc MEV — oracle arbitrage monitor (Arc mainnet, chain 5042).

Watches an oracle feed (Pyth/Chainlink) and a Uniswap v3 pool. When the pool price lags the oracle by
more than `THRESHOLD_BPS`, it:
  1) estimates the **optimal input size** by ternary-searching `ArcOracleArbitrage.executeArbitrage`
     through `eth_call` (the contract returns the profit),
  2) re-simulates and `estimate_gas` before sending anything,
  3) optionally sends the tx (if `KEEPER_PK` is set) and reports to Telegram.

No upfront capital: the arbitrage uses a Uniswap v3 flash loan; if it is not profitable the tx reverts.

Env (see bots/.env.example):
  ARC_RPC, ARB_EXECUTOR, USDC, ORACLE, ORACLE_EVENT_SIG, ORACLE_SCALE, POOL, POOL_TOKEN0_DECIMALS,
  POOL_TOKEN1_DECIMALS, TOKEN_MID, FEE_A, FEE_B, THRESHOLD_BPS, MIN_PROFIT_USDC, MIN_INPUT_USDC,
  MAX_INPUT_USDC, POLL_SECONDS, HISTORY_FILE, KEEPER_PK, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""
from __future__ import annotations

import asyncio
import json
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
ARB = os.getenv("ARB_EXECUTOR", "")
USDC = os.getenv("USDC", "0x3600000000000000000000000000000000000000")
ORACLE = os.getenv("ORACLE", "")
ORACLE_EVENT_SIG = os.getenv("ORACLE_EVENT_SIG", "PriceFeedUpdate(bytes32,uint64,int64,uint64)")
ORACLE_SCALE = float(os.getenv("ORACLE_SCALE", "1e8"))  # oracle price units per 1.0
POOL = os.getenv("POOL", "")
D0 = int(os.getenv("POOL_TOKEN0_DECIMALS", "6"))
D1 = int(os.getenv("POOL_TOKEN1_DECIMALS", "18"))
TOKEN_MID = os.getenv("TOKEN_MID", "")
FEE_A = int(os.getenv("FEE_A", "500"))
FEE_B = int(os.getenv("FEE_B", "500"))
THRESHOLD_BPS = float(os.getenv("THRESHOLD_BPS", "50"))  # 0.50%
MIN_PROFIT = int(float(os.getenv("MIN_PROFIT_USDC", "0.01")) * 1e6)
MIN_INPUT = int(float(os.getenv("MIN_INPUT_USDC", "1")) * 1e6)
MAX_INPUT = int(float(os.getenv("MAX_INPUT_USDC", "5000")) * 1e6)
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "15"))
HISTORY_FILE = os.getenv("HISTORY_FILE", "bots/oracle_arb_history.json")
KEEPER_PK = os.getenv("KEEPER_PK", "")
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")

POOL_ABI = [
    {"name": "slot0", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [
        {"name": "sqrtPriceX96", "type": "uint160"}, {"name": "tick", "type": "int24"},
        {"name": "observationIndex", "type": "uint16"}, {"name": "observationCardinality", "type": "uint16"},
        {"name": "observationCardinalityNext", "type": "uint16"}, {"name": "feeProtocol", "type": "uint8"},
        {"name": "unlocked", "type": "bool"}]},
    {"name": "token0", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address"}]},
]
ARB_ABI = [
    {"name": "owner", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address"}]},
    {"name": "executeArbitrage", "type": "function", "stateMutability": "nonpayable", "inputs": [
        {"name": "p", "type": "tuple", "components": [
            {"name": "flashPool", "type": "address"}, {"name": "path", "type": "bytes"},
            {"name": "amountIn", "type": "uint256"}, {"name": "minProfit", "type": "uint256"}]}],
     "outputs": [{"name": "profit", "type": "uint256"}]},
]
ORACLE_ABI = [
    {"name": "latestAnswer", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "int256"}]},
]

w3 = AsyncWeb3(AsyncHTTPProvider(RPC))
_last_alert: dict[str, float] = {}


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


def pack_path(tokens: list[str], fees: list[int]) -> bytes:
    """Pack a SwapRouter02 path: token(20) + fee(3) + token(20) + fee(3) + token(20) …"""
    out = b""
    for i, t in enumerate(tokens):
        out += bytes.fromhex(t[2:].lower())
        if i < len(fees):
            out += fees[i].to_bytes(3, "big")
    return out


async def pool_price() -> float:
    """token1 per token0 (human units), from sqrtPriceX96."""
    pool = w3.eth.contract(address=AsyncWeb3.to_checksum_address(POOL), abi=POOL_ABI)
    slot0 = await pool.functions.slot0().call()
    sqrt = int(slot0[0])
    raw = (sqrt / (2 ** 96)) ** 2  # token1_raw per token0_raw
    return raw * (10 ** (D0 - D1))


async def oracle_price() -> float:
    o = w3.eth.contract(address=AsyncWeb3.to_checksum_address(ORACLE), abi=ORACLE_ABI)
    ans = await o.functions.latestAnswer().call()
    return int(ans) / ORACLE_SCALE


async def sim_profit(amount_in: int) -> int:
    """eth_call executeArbitrage; returns the profit (or -1 if it reverts)."""
    arb = w3.eth.contract(address=AsyncWeb3.to_checksum_address(ARB), abi=ARB_ABI)
    owner = await arb.functions.owner().call()
    path = pack_path([USDC, TOKEN_MID, USDC], [FEE_A, FEE_B])
    p = (AsyncWeb3.to_checksum_address(POOL), path, amount_in, MIN_PROFIT)
    try:
        return int(await arb.functions.executeArbitrage(p).call({"from": owner}))
    except Exception:  # noqa: BLE001
        return -1


async def optimal_size() -> tuple[int, int]:
    """Ternary search the input size that maximises simulated profit. Returns (amount, profit)."""
    lo, hi = MIN_INPUT, MAX_INPUT
    for _ in range(14):  # ~log_1.5(MAX/MIN) iterations is plenty
        if hi - lo < lo // 100:
            break
        m1 = lo + (hi - lo) // 3
        m2 = hi - (hi - lo) // 3
        f1 = await sim_profit(m1)
        f2 = await sim_profit(m2)
        if f1 < f2:
            lo = m1
        else:
            hi = m2
    best = lo
    best_p = await sim_profit(best)
    return best, best_p


def append_history(entry: dict) -> None:
    try:
        data = []
        if os.path.exists(HISTORY_FILE):
            data = json.load(open(HISTORY_FILE, encoding="utf-8"))
        data.append(entry)
        os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True) if os.path.dirname(HISTORY_FILE) else None
        json.dump(data[-500:], open(HISTORY_FILE, "w", encoding="utf-8"), indent=2)
    except Exception as e:  # noqa: BLE001
        _log(f"history error: {e}")


async def evaluate() -> None:
    pp = await pool_price()
    op = await oracle_price()
    if op <= 0:
        return
    disc_bps = (pp / op - 1.0) * 10_000  # >0 => pool above oracle => sell on pool / buy oracle side
    _log(f"pool={pp:.6f} oracle={op:.6f} disc={disc_bps:+.1f} bps")
    if abs(disc_bps) < THRESHOLD_BPS:
        return

    key = f"{round(disc_bps)}"
    if time.time() - _last_alert.get(key, 0) < 60:
        return
    _last_alert[key] = time.time()

    if not ARB:
        await notify(
            f"🔀 <b>Oracle divergence</b>\npool vs oracle: <b>{disc_bps:+.1f} bps</b> (monitor-only — set ARB_EXECUTOR to simulate/execute)"
        )
        return

    amount, profit = await optimal_size()
    if profit <= MIN_PROFIT:
        _log(f"opportunity {disc_bps:+.1f} bps but optimal profit {profit} <= min")
        return

    await notify(
        f"🔀 <b>Oracle arb opportunity</b>\n"
        f"pool vs oracle: <b>{disc_bps:+.1f} bps</b>\n"
        f"optimal in: <b>{amount / 1e6:.4f} USDC</b> · est. profit <b>{profit / 1e6:.4f} USDC</b>"
        + ("\n⏳ sending…" if KEEPER_PK else "\n🔒 monitor-only (no KEEPER_PK)")
    )
    if not KEEPER_PK:
        return

    arb = w3.eth.contract(address=AsyncWeb3.to_checksum_address(ARB), abi=ARB_ABI)
    path = pack_path([USDC, TOKEN_MID, USDC], [FEE_A, FEE_B])
    p = (AsyncWeb3.to_checksum_address(POOL), path, amount, MIN_PROFIT)
    try:
        acct = Account.from_key(KEEPER_PK)
        tx = await arb.functions.executeArbitrage(p).build_transaction(
            {"from": acct.address, "nonce": await w3.eth.get_transaction_count(acct.address), "value": 0}
        )
        gas = await w3.eth.estimate_gas(tx)
        base = await w3.eth.gas_price
        tx.update({"gas": int(gas * 12 // 10), "maxFeePerGas": base * 2 + 1_000_000_000, "maxPriorityFeePerGas": 1_000_000_000, "chainId": await w3.eth.chain_id, "type": 2})
        signed = acct.sign_transaction(tx)
        raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
        h = await w3.eth.send_raw_transaction(raw)
        rcpt = await w3.eth.wait_for_transaction_receipt(h, timeout=60)
        await notify(f"✅ <b>Arbitrage executed</b>\ntx <code>{h.hex()}</code> · status {rcpt.status} · profit ≈ {profit / 1e6:.4f} USDC")
        append_history({"ts": int(time.time()), "disc_bps": disc_bps, "amount_in": amount, "profit": profit, "tx": h.hex(), "status": rcpt.status})
    except Exception as e:  # noqa: BLE001
        await notify(f"❌ <b>Arbitrage failed</b>\n{str(e)[:160]}")
        _log(f"arb error: {e}")


async def main() -> None:
    _log(f"Arc oracle-arb monitor · RPC={RPC} · pool={POOL or '—'} · arb={ARB or '—'} · oracle={ORACLE or '—'}")
    _log("mode: " + ("LIVE (sends arbitrage)" if KEEPER_PK else "MONITOR-ONLY (no KEEPER_PK)"))
    missing = [r for r in ("POOL", "ORACLE", "TOKEN_MID") if not os.getenv(r)]
    if missing:
        await _idle(missing)
        return
    while True:
        try:
            await evaluate()
        except Exception as e:  # noqa: BLE001
            _log(f"error: {e}")
        await asyncio.sleep(POLL_SECONDS)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        _log("stopped")
