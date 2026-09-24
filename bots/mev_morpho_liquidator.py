#!/usr/bin/env python3
"""Arc MEV — Morpho Blue liquidation monitor (Arc mainnet, chain 5042).

Watches Morpho Blue positions on Arc, computes the Health Factor **off-chain** from
`position(marketId, borrower)`, `market(marketId)` and the Morpho oracle, and — when a borrower is
insolvent (HF < 1) and the simulated liquidation is profitable — calls
`ArcMorphoLiquidator.executeLiquidation` (flash loan + liquidate, fee-free on Morpho).

MONITOR-ONLY by default (no KEEPER_PK). Telegram alerts reuse `ops/launchpad-alerts.env` (and bots/.env).

Env (see bots/.env.example):
  ARC_RPC, MORPHO, USDC, COLLATERAL_TOKEN, ORACLE, IRM, LLTV (e.g. 0.86), SWAP_FEE,
  REPAY_PCT (0-100), MIN_PROFIT_USDC, HF_THRESHOLD, WATCHLIST, DISCOVER_BORROWERS, LOOKBACK_BLOCKS,
  POLL_SECONDS, HISTORY_FILE, KEEPER_PK, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""
from __future__ import annotations

import asyncio
import json
import os
import time

import aiohttp
from eth_abi import encode as abi_encode
from eth_account import Account
from web3 import AsyncWeb3

try:
    from web3 import AsyncHTTPProvider  # web3 >= 7
except ImportError:  # web3 6.x
    from web3.providers.async_rpc import AsyncHTTPProvider

# ----------------------------------------------------------------------------- env
def load_env(path: str) -> None:
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


load_env("bots/.env")
load_env("ops/launchpad-alerts.env")  # Telegram fallback

RPC = os.getenv("ARC_RPC", "https://rpc.mainnet.arc.io")
MORPHO = os.getenv("MORPHO", "0x34CD04070dD72b14E241112F6d83812Df5Af7fCD")  # Arc mainnet
USDC = os.getenv("USDC", "0x3600000000000000000000000000000000000000")
COLLATERAL = os.getenv("COLLATERAL_TOKEN", "")
ORACLE = os.getenv("ORACLE", "")
IRM = os.getenv("IRM", "")
LLTV = float(os.getenv("LLTV", "0.86"))
SWAP_FEE = int(os.getenv("SWAP_FEE", "500"))
REPAY_PCT = float(os.getenv("REPAY_PCT", "50"))
MIN_PROFIT = int(float(os.getenv("MIN_PROFIT_USDC", "0.05")) * 1e6)
MAX_DEBT = int(float(os.getenv("MAX_DEBT_USDC", "5")) * 1e6)  # pilot cap: only liquidate debts <= this
HF_THRESHOLD = float(os.getenv("HF_THRESHOLD", "1.0"))
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "20"))
DISCOVER = os.getenv("DISCOVER_BORROWERS", "1") == "1"
LOOKBACK_BLOCKS = int(os.getenv("LOOKBACK_BLOCKS", "50000"))
HISTORY_FILE = os.getenv("HISTORY_FILE", "bots/morpho_liq_history.json")
KEEPER_PK = os.getenv("KEEPER_PK", "")
EXECUTOR = os.getenv("MORPHO_EXECUTOR", "")  # ArcMorphoLiquidator (optional until deployed)
MORPHO_KEEPER = os.getenv("MORPHO_KEEPER", "")  # the contract's keeper hot key (for sim when no PK)
try:
    KEEPER_ADDR = (
        AsyncWeb3.to_checksum_address(MORPHO_KEEPER)
        if MORPHO_KEEPER
        else (Account.from_key(KEEPER_PK).address if KEEPER_PK else None)
    )
except Exception:  # noqa: BLE001
    KEEPER_ADDR = None
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")

VIRTUAL_SHARES = 1_000_000
VIRTUAL_ASSETS = 1
WAD = 10**18
ORACLE_SCALE = 10**36

MORPHO_ABI = [
    {"name": "position", "type": "function", "stateMutability": "view", "inputs": [
        {"name": "id", "type": "bytes32"}, {"name": "user", "type": "address"}],
     "outputs": [{"name": "supplyShares", "type": "uint256"}, {"name": "borrowShares", "type": "uint128"}, {"name": "collateral", "type": "uint128"}]},
    {"name": "market", "type": "function", "stateMutability": "view", "inputs": [{"name": "id", "type": "bytes32"}],
     "outputs": [{"name": "totalSupplyAssets", "type": "uint128"}, {"name": "totalSupplyShares", "type": "uint128"},
                 {"name": "totalBorrowAssets", "type": "uint128"}, {"name": "totalBorrowShares", "type": "uint128"},
                 {"name": "lastUpdate", "type": "uint128"}, {"name": "fee", "type": "uint128"}]},
]
ORACLE_ABI = [{"name": "price", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]}]
EXECUTOR_ABI = [
    {"name": "owner", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address"}]},
    {"name": "executeLiquidation", "type": "function", "stateMutability": "nonpayable", "inputs": [
        {"name": "p", "type": "tuple", "components": [
            {"name": "collateralToken", "type": "address"}, {"name": "oracle", "type": "address"}, {"name": "irm", "type": "address"},
            {"name": "lltv", "type": "uint256"}, {"name": "borrower", "type": "address"}, {"name": "seizedAssets", "type": "uint256"},
            {"name": "repaidShares", "type": "uint256"}, {"name": "swapFee", "type": "uint24"}, {"name": "minProfit", "type": "uint256"}]},
        {"name": "flashAmount", "type": "uint256"}], "outputs": [{"name": "profit", "type": "uint256"}]},
]
BORROW_TOPIC = AsyncWeb3.keccak(text="Borrow(bytes32,address,address,uint256,uint256)").hex()

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


def market_id() -> bytes:
    """Morpho market id = keccak256(abi.encode(loanToken, collateralToken, oracle, irm, lltv))."""
    encoded = abi_encode(
        ["address", "address", "address", "address", "uint256"],
        [USDC, COLLATERAL, ORACLE, IRM, int(LLTV * 1e18)],
    )
    return bytes(AsyncWeb3.keccak(encoded))


def to_assets_up(shares: int, total_assets: int, total_shares: int) -> int:
    """Morpho SharesMathLib.toAssetsUp: shares*(totalAssets+VIRTUAL_ASSETS)/(totalShares+VIRTUAL_SHARES)."""
    num = shares * (total_assets + VIRTUAL_ASSETS)
    den = total_shares + VIRTUAL_SHARES
    return (num + den - 1) // den


def to_shares_up(assets: int, total_assets: int, total_shares: int) -> int:
    """Morpho SharesMathLib.toSharesUp: assets*(totalShares+VIRTUAL_SHARES)/(totalAssets+VIRTUAL_ASSETS)."""
    num = assets * (total_shares + VIRTUAL_SHARES)
    den = total_assets + VIRTUAL_ASSETS
    return (num + den - 1) // den


async def health_factor(borrower: str) -> tuple[int, int, int, int, int, int]:
    """Returns (hf_wad, borrow_assets, collateral, borrow_shares, total_borrow_assets, total_borrow_shares)."""
    m = w3.eth.contract(address=AsyncWeb3.to_checksum_address(MORPHO), abi=MORPHO_ABI)
    mid = market_id()
    pos = await m.functions.position(mid, AsyncWeb3.to_checksum_address(borrower)).call()
    mkt = await m.functions.market(mid).call()
    o = w3.eth.contract(address=AsyncWeb3.to_checksum_address(ORACLE), abi=ORACLE_ABI)
    price = int(await o.functions.price().call())
    borrow_shares = int(pos[1])
    collateral = int(pos[2])
    tba, tbs = int(mkt[2]), int(mkt[3])
    if borrow_shares == 0 or collateral == 0:
        return (10**30, 0, collateral, 0, tba, tbs)  # no debt -> healthy
    borrow_assets = to_assets_up(borrow_shares, tba, tbs)
    collateral_value = (collateral * price) // ORACLE_SCALE
    hf = (collateral_value * int(LLTV * 1e18)) // borrow_assets if borrow_assets else 10**30
    return (hf, borrow_assets, collateral, borrow_shares, tba, tbs)


async def watchlist() -> set[str]:
    addrs: set[str] = set()
    for a in os.getenv("WATCHLIST", "").split(","):
        a = a.strip().lower()
        if a.startswith("0x") and len(a) == 42:
            addrs.add(AsyncWeb3.to_checksum_address(a))
    return addrs


async def discover_borrowers() -> set[str]:
    if not DISCOVER or not COLLATERAL:
        return set()
    out: set[str] = set()
    try:
        latest = await w3.eth.block_number
        frm = latest - LOOKBACK_BLOCKS if latest > LOOKBACK_BLOCKS else 0
        logs = await w3.eth.get_logs({
            "address": AsyncWeb3.to_checksum_address(MORPHO),
            "fromBlock": frm, "toBlock": latest,
            "topics": [BORROW_TOPIC, market_id().hex()],
        })
        for lg in logs:
            # topics: [sig, id, caller, onBehalf] -> onBehalf is the 3rd topic (index 2 after sig)
            if len(lg["topics"]) >= 3:
                out.add(AsyncWeb3.to_checksum_address("0x" + lg["topics"][2].hex()[-40:]))
    except Exception as e:  # noqa: BLE001
        _log(f"discover_borrowers: {e}")
    return out


async def check(borrower: str) -> None:
    hf, borrow_assets, collateral, borrow_shares, tba, tbs = await health_factor(borrower)
    if borrow_assets == 0:
        return
    hf_f = hf / 1e18
    if hf_f >= HF_THRESHOLD:
        return
    if time.time() - _last.get(borrower.lower(), 0) < 900:
        return
    _last[borrower.lower()] = time.time()

    # PARTIAL liquidation: repay at most MAX_DEBT, so it works on large underwater positions too.
    repay_assets = min(borrow_assets, MAX_DEBT)
    repaid_shares = to_shares_up(repay_assets, tba, tbs)
    _log(f"AT RISK {borrower} HF={hf_f:.4f} debt={borrow_assets / 1e6:.4f} → partial repay {repay_assets / 1e6:.4f} USDC")

    msg = (
        f"🎯 <b>Morpho position liquidatable</b>\n"
        f"• borrower <code>{borrower}</code>\n"
        f"• HF <b>{hf_f:.4f}</b> · debt <b>{borrow_assets / 1e6:.4f} USDC</b>\n"
        f"• partial repay <b>{repay_assets / 1e6:.4f} USDC</b> (cap {MAX_DEBT / 1e6:.2f})"
    )
    if not EXECUTOR or not KEEPER_PK:
        await notify(msg + "\n🔒 monitor-only (set MORPHO_EXECUTOR + KEEPER_PK to execute)")
        return

    # simulate the (partial) liquidation — executeLiquidation returns the profit
    ex = w3.eth.contract(address=AsyncWeb3.to_checksum_address(EXECUTOR), abi=EXECUTOR_ABI)
    owner = await ex.functions.owner().call()
    p = (AsyncWeb3.to_checksum_address(COLLATERAL), AsyncWeb3.to_checksum_address(ORACLE), AsyncWeb3.to_checksum_address(IRM),
         int(LLTV * 1e18), AsyncWeb3.to_checksum_address(borrower), 0, repaid_shares, SWAP_FEE, MIN_PROFIT)
    try:
        profit = int(await ex.functions.executeLiquidation(p, repay_assets).call({"from": KEEPER_ADDR or owner}))
    except Exception as e:  # noqa: BLE001
        await notify(msg + f"\n⚠️ sim revertió: {str(e)[:120]}")
        return

    await notify(msg + f"\n💰 sim profit <b>{profit / 1e6:.4f} USDC</b>\n⏳ sending…")
    try:
        acct = Account.from_key(KEEPER_PK)
        tx = await ex.functions.executeLiquidation(p, repay_assets).build_transaction(
            {"from": acct.address, "nonce": await w3.eth.get_transaction_count(acct.address), "value": 0})
        gas = await w3.eth.estimate_gas(tx)
        base = await w3.eth.gas_price
        tx.update({"gas": int(gas * 12 // 10), "maxFeePerGas": base * 2 + 1_000_000_000, "maxPriorityFeePerGas": 1_000_000_000,
                   "chainId": await w3.eth.chain_id, "type": 2})
        signed = acct.sign_transaction(tx)
        raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
        h = await w3.eth.send_raw_transaction(raw)
        rcpt = await w3.eth.wait_for_transaction_receipt(h, timeout=60)
        await notify(f"✅ <b>Morpho liquidation executed</b>\n<code>{h.hex()}</code> · status {rcpt.status} · profit ≈ {profit / 1e6:.4f} USDC")
        _append({"ts": int(time.time()), "borrower": borrower, "hf": hf_f, "repaid": repay_assets, "profit": profit, "tx": h.hex(), "status": rcpt.status})
    except Exception as e:  # noqa: BLE001
        await notify(f"❌ <b>Morpho liquidation failed</b>\n{str(e)[:160]}")


def _append(entry: dict) -> None:
    try:
        data = json.load(open(HISTORY_FILE, encoding="utf-8")) if os.path.exists(HISTORY_FILE) else []
        data.append(entry)
        json.dump(data[-500:], open(HISTORY_FILE, "w", encoding="utf-8"), indent=2)
    except Exception as e:  # noqa: BLE001
        _log(f"history error: {e}")


async def scan() -> None:
    global _last_block
    users = await watchlist() | await discover_borrowers()
    for u in users:
        try:
            await check(u)
        except Exception as e:  # noqa: BLE001
            _log(f"{u}: {e}")


async def main() -> None:
    _log(f"Arc Morpho liquidator monitor · RPC={RPC} · morpho={MORPHO}")
    _log("mode: " + ("LIVE (sends liquidations)" if (KEEPER_PK and EXECUTOR) else "MONITOR-ONLY"))
    missing = [r for r in ("COLLATERAL_TOKEN", "ORACLE", "IRM") if not os.getenv(r)]
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
