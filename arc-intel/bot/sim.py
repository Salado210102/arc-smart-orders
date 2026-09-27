"""Local bot simulator — runnable, no Telegram token, no network.

Exercises the REAL modules end to end so you can test and find bugs:
  risk (anti-rug) -> bot messages -> execution intent -> permissions -> exit strategy.

Run:
    python -m bot.sim                # scripted demo (deterministic)
    python -m bot.sim --interactive  # poke commands manually
"""
from __future__ import annotations

import argparse

from indexer.risk import anti_rug_report, build_alerts
from bot.messages import format_alert, format_token_signal
from execution.intents import build_intent, min_out, is_expired
from execution.strategy import Position, ExitPlan, evaluate_exit
from security.permissions import create_approval, cancel, confirm, can_execute, mark_executed

SAMPLE_SCORE = {"wallet": "0xsmart", "win_rate": 0.73, "trades": 18, "avg_mult": 2.1,
                "entry_pct": 0.8, "confidence": "media"}


def _sample_legs():
    legs = []
    # noisy volume then a collapse, plus a creator sell and a smart wallet exit
    vals = [9, 10, 11, 10, 9, 10, 11, 10, 9, 10, 11, 10, 0]
    for i, v in enumerate(vals):
        legs.append({"wallet": "0xbuyer", "token": "0xtokdemo", "block": i * 1000,
                     "side": "buy", "stable_value": float(v)})
    legs.append({"wallet": "0xdev", "token": "0xtokdemo", "block": 5000, "side": "sell",
                 "stable_value": 1.0})
    legs.append({"wallet": "0xsmart", "token": "0xtokdemo", "block": 12000, "side": "sell",
                 "stable_value": 5.0})
    return legs


def demo_flow(now: int = 1_000_000) -> list[str]:
    out: list[str] = []
    rep = anti_rug_report(_sample_legs(), creators_by_token={"0xtokdemo": "0xdev"},
                          smart_wallets={"0xsmart"}, bucket_blocks=1000, z_threshold=-1.5)
    alerts = build_alerts(rep, min_severity="medium")
    out.append("== alerts ==")
    for a in alerts:
        out.append(format_alert(a, score=SAMPLE_SCORE))
    out.append(format_token_signal("0xtokdemo", SAMPLE_SCORE, rep["0xtokdemo"]["flags"]))

    out.append("== trade intent (non-custodial) ==")
    intent = build_intent("0xuser", "0xtokdemo", "buy", 10.0, now=now, limit_price=2.0,
                          max_slippage_bps=100, ttl_seconds=300)
    out.append(f"intent buy 10 @2.0 deadline={intent.deadline} min_out={min_out(intent):.3f}")
    out.append(f"expired? {is_expired(intent, now + 400)}")

    out.append("== permission gate ==")
    ap = create_approval("ap1", "0xuser", {"token": "0xtokdemo", "side": "buy"}, 20.0,
                         now=now, cancel_seconds=300, twofa_threshold=5.0)
    out.append(f"requires_2fa={ap.requires_2fa} cancel_until={ap.cancel_until}")
    out.append(f"cancel in window -> {cancel(ap, now + 100)}")
    _ok, reason = confirm(ap, now + 400, twofa_ok=True)
    out.append(f"confirm after window -> {reason}")
    ap2 = create_approval("ap2", "0xuser", {"token": "0xtokdemo", "side": "buy"}, 20.0,
                          now=now, cancel_seconds=300, twofa_threshold=5.0)
    out.append(f"confirm w/o 2FA -> {confirm(ap2, now + 400, twofa_ok=False)[1]}")
    ok, reason = confirm(ap2, now + 400, twofa_ok=True)
    out.append(f"confirm w/ 2FA -> {reason}; can_execute={can_execute(ap2, now + 500)}")
    out.append(f"mark_executed={mark_executed(ap2, now + 500)}")

    out.append("== exit plan ==")
    pos = Position(entry_price=2.0, size=10.0)
    plan = ExitPlan(take_profit_pct=0.5, stop_loss_pct=0.2, trailing_stop_pct=0.25)
    for price in (2.1, 3.2, 2.4, 1.5):
        r = evaluate_exit(pos, price, plan)
        out.append(f"price={price} -> {r['action']} ({r['reason']})")
    return out


COMMANDS = (
    "commands: signal | buy <amount> | approve | cancel | status | exit <price> | quit"
)


def interactive(now: int = 1_000_000) -> None:
    print("bot simulator (type 'help' for commands)")
    ap = None
    pos = Position(entry_price=2.0, size=10.0)
    plan = ExitPlan(take_profit_pct=0.5, stop_loss_pct=0.2, trailing_stop_pct=0.25)
    t = now
    while True:
        try:
            raw = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not raw:
            continue
        cmd, *rest = raw.split()
        t += 10
        if cmd in ("quit", "exit!"):
            break
        if cmd == "help":
            print(COMMANDS)
        elif cmd == "signal":
            for line in demo_flow(t)[:3]:
                print(line)
        elif cmd == "buy":
            amount = float(rest[0]) if rest else 10.0
            intent = build_intent("0xuser", "0xtokdemo", "buy", amount, now=t, limit_price=2.0,
                                  max_slippage_bps=100)
            ap = create_approval("ap", "0xuser", {"token": "0xtokdemo", "side": "buy"},
                                 amount * 2.0, now=t, cancel_seconds=30, twofa_threshold=5.0)
            print(f"intent min_out={min_out(intent):.3f}; approval requires_2fa={ap.requires_2fa}")
        elif cmd == "cancel":
            print("cancelled" if ap and cancel(ap, t) else "cannot cancel")
        elif cmd == "approve":
            if not ap:
                print("no approval; run 'buy <amount>'")
            else:
                ok, reason = confirm(ap, t, twofa_ok=True)
                print(f"{reason}; can_execute={can_execute(ap, t)}")
        elif cmd == "status":
            print(f"approval={ap.status if ap else None}")
        elif cmd == "exit":
            price = float(rest[0]) if rest else 2.0
            print(evaluate_exit(pos, price, plan))
        else:
            print("unknown; " + COMMANDS)


def live_alerts(dsn: str, limit: int = 200000) -> list[dict]:
    """Run Phase 3 on real indexed data (Postgres). VPS-only (needs psycopg2)."""
    from indexer.pg_storage import PostgresStorage
    from indexer.pnl import collect_legs_pg
    from indexer.scoring import load_insider_data_pg

    s = PostgresStorage(dsn)
    legs = collect_legs_pg(s, limit)
    creators, _dev = load_insider_data_pg(s)
    smart = {r["wallet"] for r in s.load_wallet_scores(0.0, 8)}
    s.close()
    rep = anti_rug_report(legs, creators_by_token=creators, smart_wallets=smart)
    return build_alerts(rep, min_severity="medium")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interactive", action="store_true")
    ap.add_argument("--dsn", type=str, help="run on real indexed data (Postgres)")
    ap.add_argument("--limit", type=int, default=200000)
    ap.add_argument("--top", type=int, default=10)
    args = ap.parse_args()
    if args.dsn:
        alerts = live_alerts(args.dsn, args.limit)
        for a in alerts[: args.top]:
            print(format_alert(a))
        print(f"(total alerts: {len(alerts)})")
        return
    if args.interactive:
        interactive()
    else:
        for line in demo_flow():
            print(line)


if __name__ == "__main__":
    main()
