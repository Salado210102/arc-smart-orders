"""Bridge helpers: guided USDC bridge to Arc + arrival detection.

The user bridges USDC from Base / Arbitrum / Solana to their **bot wallet** Arc address using an
official bridge (Circle CCTP — Arc is a Circle chain). We never move the source funds (no custody of
the user's external wallet): we (a) show the exact destination address + instructions and (b) detect
the deposit and notify. Detection polls the bot wallet's USDC balance and reports increases.
"""
from __future__ import annotations

SUPPORTED_SOURCES = ("Base", "Arbitrum", "Solana")
MIN_NOTIFY_USDC = 0.5


def deposit_delta(old_balance: float, new_balance: float) -> float:
    """Positive USDC deposit delta, else 0."""
    return max(0.0, float(new_balance or 0.0) - float(old_balance or 0.0))


def bridge_link(base_url: str | None, address: str) -> str:
    """Optional deep link to a bridge provider pre-filled with the destination address."""
    u = (base_url or "").strip()
    if not u or not address:
        return ""
    sep = "&" if "?" in u else "?"
    return f"{u}{sep}to={address}&token=USDC"


def poll_deposits(store, transport, throttle, *, balance_fn, logger=None) -> int:
    """Notify each custody user when their bot wallet's USDC balance increases (a bridge arrival).

    `balance_fn(address) -> float` (USDC). First sight of an address only sets the baseline (no
    false 'arrival'). Returns the number of notifications sent."""
    notified = 0
    for chat, addr in store.list_custody_addresses():
        try:
            bal = float(balance_fn(addr) or 0.0)
        except Exception:
            continue
        key = f"bridge_bal:{chat}"
        raw = store.get_state(key)
        if raw is None:                      # baseline only
            store.set_state(key, str(bal))
            continue
        d = deposit_delta(float(raw or 0.0), bal)
        store.set_state(key, str(bal))
        if d >= MIN_NOTIFY_USDC:
            try:
                throttle.wait(chat)
                transport.send(chat, f"\U0001F4B0 +${d:.2f} USDC llegaron a tu wallet del bot. "
                                     f"Ya puedes operar al instante.")
            except Exception:
                pass
            notified += 1
            if logger:
                logger({"bridge_arrival": {"chat": chat, "usdc": round(d, 4)}})
    return notified
