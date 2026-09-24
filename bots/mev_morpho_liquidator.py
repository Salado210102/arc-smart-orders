#!/usr/bin/env python3
"""Arc MEV — Morpho Blue liquidation monitor (MULTI-MARKET) — Arc mainnet, chain 5042.

Scans MULTIPLE Morpho Blue markets on Arc, discovers borrowers from `Borrow` logs (+ a WATCHLIST),
computes each Health Factor **off-chain** (position + market + oracle, Morpho math), and — when a borrower
is insolvent (HF < 1) — calls `ArcMorphoLiquidator.executeLiquidation` with a **PARTIAL** repayment capped
at `MAX_DEBT_USDC` (so large underwater positions qualify too).

MONITOR-ONLY unless KEEPER_PK + MORPHO_EXECUTOR are set. Telegram alerts reuse `ops/launchpad-alerts.env`.

Env (see bots/.env.example):
  ARC_RPC, MORPHO, USDC, MARKETS (comma-separated market ids; empty = auto from Morpho API),
  WATCHLIST, DISCOVER_BORROWERS, LOOKBACK_BLOCKS, HF_THRESHOLD, MAX_DEBT_USDC, MIN_PROFIT_USDC,
  SWAP_FEE, REPAY_PCT (unused when partial), POLL_SECONDS, HISTORY_FILE,
  MORPHO_EXECUTOR, MORPHO_KEEPER, KEEPER_PK, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
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
LOAN_TOKENS = [a.strip().lower() for a in os.getenv("LOAN_TOKENS", USDC).split(",") if a.strip()]
# Known Arc USDC-loan Morpho markets (used when MARKETS is not set).
DEFAULT_MARKETS = [
    "0xc2db905f174e5defcce01d321b09f15f78856a36a21b90cc7e1abbc29225815d",  # USDC/cirBTC (main)
    "0xabd1763943714b96b6590238d484a240019b4b842eb67fbcff7d96c081b7b566",  # USDC/cirBTC
    "0x9bd953647610205cd0869118035ca1b021ed5d7654b8a9a013032b549d0abe12",  # USDC/PST
    "0x43b04ce1e2fb3120a792515af1c1271175343512deeb4232c5347f1db6378e8a",  # USDC/PST
    "0x20f431a88b5e1d9e3cd83c50ff26612d100359a41f32787f6c6bf7a1ad5ed9ab",  # USDC/PST
    "0x2f192dcd77943c7771aea0aedacb957844cf53a4a5218da4b04037bd2c759b75",  # USDC/WETH
    "0x28b684e2283b59170abacad24b15484c2606339183fe37d8fd7cf96478c9b684",  # USDC/syrupUSDC
    "0x126759c350bb65bf782cf9fbfe09fb9cbd32c5a39d26c2194994049ddb3b7e5c",  # USDC/sUSDai
    "0x6cbae29b4f0905c393c01cc91f5d439b64928cc7664eb906f1e67e8d6c4cb993",  # USDC/XAUM
]
MARKETS = [m.strip().lower() for m in os.getenv("MARKETS", ",".join(DEFAULT_MARKETS)).split(",") if m.strip()]
SWAP_FEE = int(os.getenv("SWAP_FEE", "3000"))
HF_THRESHOLD = float(os.getenv("HF_THRESHOLD", "1.0"))
MAX_DEBT = int(float(os.getenv("MAX_DEBT_USDC", "50")) * 1e6)  # partial-liquidation cap
MIN_PROFIT = int(float(os.getenv("MIN_PROFIT_USDC", "0.05")) * 1e6)
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "4"))
DISCOVER = os.getenv("DISCOVER_BORROWERS", "1") == "1"
LOOKBACK_BLOCKS = int(os.getenv("LOOKBACK_BLOCKS", "2000"))
HISTORY_FILE = os.getenv("HISTORY_FILE", "bots/morpho_liq_history.json")
KEEPER_PK = os.getenv("KEEPER_PK", "")
EXECUTOR = os.getenv("MORPHO_EXECUTOR", "")
MORPHO_KEEPER = os.getenv("MORPHO_KEEPER", "")
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
ORACLE_SCALE = 10**36

MORPHO_ABI = [
    {"name": "position", "type": "function", "stateMutability": "view", "inputs": [
        {"name": "id", "type": "bytes32"}, {"name": "user", "type": "address"}],
     "outputs": [{"name": "supplyShares", "type": "uint256"}, {"name": "borrowShares", "type": "uint128"}, {"name": "collateral", "type": "uint128"}]},
    {"name": "market", "type": "function", "stateMutability": "view", "inputs": [{"name": "id", "type": "bytes32"}],
     "outputs": [{"name": "totalSupplyAssets", "type": "uint128"}, {"name": "totalSupplyShares", "type": "uint128"},
                 {"name": "totalBorrowAssets", "type": "uint128"}, {"name": "totalBorrowShares", "type": "uint128"},
                 {"name": "lastUpdate", "type": "uint128"}, {"name": "fee", "type": "uint128"}]},
    {"name": "idToMarketParams", "type": "function", "stateMutability": "view", "inputs": [{"name": "id", "type": "bytes32"}],
     "outputs": [{"name": "loanToken", "type": "address"}, {"name": "collateralToken", "type": "address"},
                 {"name": "oracle", "type": "address"}, {"name": "irm", "type": "address"}, {"name": "lltv", "type": "uint256"}]},
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
_market_cache: dict[str, dict] = {}
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


def to_assets_up(shares: int, total_assets: int, total_shares: int) -> int:
    num = shares * (total_assets + VIRTUAL_ASSETS)
    den = total_shares + VIRTUAL_SHARES
    return (num + den - 1) // den


def to_shares_up(assets: int, total_assets: int, total_shares: int) -> int:
    num = assets * (total_shares + VIRTUAL_SHARES)
    den = total_assets + VIRTUAL_ASSETS
    return (num + den - 1) // den


async def market_params(mid: str) -> dict:
    if mid in _market_cache:
        return _market_cache[mid]
    m = w3.eth.contract(address=AsyncWeb3.to_checksum_address(MORPHO), abi=MORPHO_ABI)
    mp = await m.functions.idToMarketParams(bytes.fromhex(mid[2:])).call()
    info = {"id": mid, "loan": mp[0], "collateral": mp[1], "oracle": mp[2], "irm": mp[3], "lltv": int(mp[4])}
    _market_cache[mid] = info
    return info


async def watchlist() -> set[str]:
    out: set[str] = set()
    for a in os.getenv("WATCHLIST", "").split(","):
        a = a.strip().lower()
        if a.startswith("0x") and len(a) == 42:
            out.add(AsyncWeb3.to_checksum_address(a))
    return out


async def discover_borrowers(mid: str) -> set[str]:
    out: set[str] = set()
    if not DISCOVER:
        return out
    try:
        latest = await w3.eth.block_number
        frm = latest - LOOKBACK_BLOCKS if latest > LOOKBACK_BLOCKS else 0
        logs = await w3.eth.get_logs({
            "address": AsyncWeb3.to_checksum_address(MORPHO),
            "fromBlock": frm, "toBlock": latest,
            "topics": [BORROW_TOPIC, "0x" + mid[2:]],
        })
        for lg in logs:
            if len(lg["topics"]) >= 3:
                out.add(AsyncWeb3.to_checksum_address("0x" + lg["topics"][2].hex()[-40:]))
    except Exception as e:  # noqa: BLE001
        _log(f"discover({mid[:10]}): {e}")
    return out


async def health_factor(info: dict, borrower: str) -> tuple[int, int, int, int, int, int]:
    m = w3.eth.contract(address=AsyncWeb3.to_checksum_address(MORPHO), abi=MORPHO_ABI)
    mid = bytes.fromhex(info["id"][2:])
    pos = await m.functions.position(mid, AsyncWeb3.to_checksum_address(borrower)).call()
    mkt = await m.functions.market(mid).call()
    o = w3.eth.contract(address=AsyncWeb3.to_checksum_address(info["oracle"]), abi=ORACLE_ABI)
    price = int(await o.functions.price().call())
    borrow_shares = int(pos[1])
    collateral = int(pos[2])
    tba, tbs = int(mkt[2]), int(mkt[3])
    if borrow_shares == 0 or collateral == 0:
        return (10**30, 0, collateral, 0, tba, tbs)
    borrow_assets = to_assets_up(borrow_shares, tba, tbs)
    collateral_value = (collateral * price) // ORACLE_SCALE
    hf = (collateral_value * info["lltv"]) // borrow_assets if borrow_assets else 10**30
    return (hf, borrow_assets, collateral, borrow_shares, tba, tbs)


async def check(info: dict, borrower: str) -> None:
    hf, borrow_assets, collateral, borrow_shares, tba, tbs = await health_factor(info, borrower)
    if borrow_assets == 0:
        return
    hf_f = hf / 1e18
    if hf_f >= HF_THRESHOLD:
        return
    key = f"{info['id'][:10]}:{borrower.lower()}"
    if time.time() - _last.get(key, 0) < 900:
        return
    _last[key] = time.time()

    repay_assets = min(borrow_assets, MAX_DEBT)  # PARTIAL liquidation
    repaid_shares = to_shares_up(repay_assets, tba, tbs)
    _log(f"AT RISK {borrower} market={info['id'][:10]} HF={hf_f:.4f} debt={borrow_assets / 1e6:.4f} → partial {repay_assets / 1e6:.4f}")

    msg = (
        f"🎯 <b>Morpho position liquidatable</b>\n"
        f"• market <code>{info['id'][:12]}…</code>\n"
        f"• borrower <code>{borrower}</code>\n"
        f"• HF <b>{hf_f:.4f}</b> · debt <b>{borrow_assets / 1e6:.4f} USDC</b>\n"
        f"• partial repay <b>{repay_assets / 1e6:.4f} USDC</b> (cap {MAX_DEBT / 1e6:.2f})"
    )
    if not EXECUTOR or not KEEPER_PK:
        await notify(msg + "\n🔒 monitor-only (set MORPHO_EXECUTOR + KEEPER_PK to execute)")
        return

    ex = w3.eth.contract(address=AsyncWeb3.to_checksum_address(EXECUTOR), abi=EXECUTOR_ABI)
    owner = await ex.functions.owner().call()
    p = (AsyncWeb3.to_checksum_address(info["collateral"]), AsyncWeb3.to_checksum_address(info["oracle"]),
         AsyncWeb3.to_checksum_address(info["irm"]), info["lltv"], AsyncWeb3.to_checksum_address(borrower),
         0, repaid_shares, SWAP_FEE, MIN_PROFIT)
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
        _append({"ts": int(time.time()), "market": info["id"], "borrower": borrower, "hf": hf_f, "repaid": repay_assets, "profit": profit, "tx": h.hex(), "status": rcpt.status})
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
    wl = await watchlist()
    for mid in MARKETS:
        try:
            info = await market_params(mid)
            if info["loan"].lower() not in LOAN_TOKENS:
                continue
            users = wl | set(await discover_borrowers(mid))
            for u in users:
                try:
                    await check(info, u)
                except Exception as e:  # noqa: BLE001
                    _log(f"{mid[:10]}/{u}: {e}")
        except Exception as e:  # noqa: BLE001
            _log(f"market {mid[:10]}: {e}")


async def main() -> None:
    _log(f"Arc Morpho liquidator (multi-market) · RPC={RPC} · morpho={MORPHO} · markets={len(MARKETS)}")
    _log("mode: " + ("LIVE (sends liquidations)" if (KEEPER_PK and EXECUTOR) else "MONITOR-ONLY"))
    if not MARKETS:
        await _idle(["MARKETS"])
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
