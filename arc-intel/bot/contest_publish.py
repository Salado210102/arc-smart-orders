"""Publish the closed contest round's winners as a flashy poster (image + HTML caption) to the
official channel AND to bot subscribers. Best-effort, once per round.

Dormant unless a channel/broadcast target exists. A round settles `PUBLISH_DELAY_S` (1h) after it
closes; a failed send is retried next cycle (the round is only marked once at least one send went out).
"""
from __future__ import annotations

from monetization import contest as CT


def display_name(store, user: str) -> str:
    name = store.get_state(f"name:{user}", "")
    return name or CT.mask_user(user)


def _results(store, prev):
    trader_v = store.volume_by_user_between(prev["start"], prev["end"])
    aff_v = store.referred_volume_between(prev["start"], prev["end"])
    s = CT.settle(trader_v, aff_v)

    def row(w, prize):
        return None if not w else {"user": display_name(store, w["user"]),
                                   "volume": w["volume"], "prize": prize}
    return s, row(s["trader"], s["prize"]["trader"]), row(s["affiliate"], s["prize"]["affiliate"])


def _send(transport, chat, png, caption, html) -> bool:
    if png and hasattr(transport, "send_photo_bytes"):
        try:
            transport.send_photo_bytes(chat, png, caption=caption, parse_mode="HTML")
            return True
        except Exception:
            pass
    transport.send(chat, html, parse_mode="HTML")
    return True


def publish_round(store, transport, now, channel, *, logger=None, round_hours: int = CT.ROUND_HOURS,
                  delay_s: int = CT.PUBLISH_DELAY_S, broadcast: bool = True, link: str = "") -> dict | None:
    prev = CT.previous_round(now, round_hours)
    if now < prev["end"] + delay_s:
        return None
    if store.contest_round_published(prev["id"]):
        return None
    s, trader, aff = _results(store, prev)
    from . import poster as P
    png = None
    if P.pillow_available():
        try:
            png = P.render_contest_poster(label=P.round_label(prev["start"], round_hours),
                                          pozo=s["pozo"], trader=trader, affiliate=aff)
        except Exception:
            png = None
    caption = P.poster_caption(s["pozo"], trader, aff, link)
    targets = []
    if channel:
        targets.append(channel)
    if broadcast:
        targets += [sub["chat_id"] for sub in store.list()]
    if not targets:
        return None
    sent = 0
    for chat in targets:
        try:
            _send(transport, chat, png, caption, caption)
            sent += 1
        except Exception as e:
            if logger:
                logger({"contest_send_failed": {"chat": str(chat), "err": str(e)[:100]}})
    if sent == 0:
        return None                      # nothing sent -> retry next cycle
    store.mark_contest_round(prev["id"], int(now))
    for cat, w in (("trader", trader), ("affiliate", aff)):
        if w:
            store.record_contest_winner(prev["id"], cat, w["user"], w["volume"], w["prize"])
    winners = (1 if trader else 0) + (1 if aff else 0)
    if logger:
        logger({"contest_published": prev["id"], "sent": sent, "winners": winners})
    return {"round": prev["id"], "pozo": s["pozo"], "sent": sent, "winners": winners}


def _preview_png():
    import time
    from . import poster as P
    label = P.round_label((int(time.time()) // (CT.ROUND_HOURS * 3600)) * CT.ROUND_HOURS * 3600)
    trader = {"user": "@whale", "volume": 250000.0, "prize": 617.28}
    aff = {"user": "@degen", "volume": 180000.0, "prize": 617.28}
    return P.render_contest_poster(label=label, pozo=1234.56, trader=trader, affiliate=aff), trader, aff


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Contest poster preview")
    ap.add_argument("--out", default="", help="write a sample poster PNG to this path")
    ap.add_argument("--preview", default="", help="chat id to send the sample poster to")
    ap.add_argument("--token", default="", help="bot token (default: env ARC_INTEL_BOT_TOKEN)")
    args = ap.parse_args()
    png, trader, aff = _preview_png()
    if args.out:
        with open(args.out, "wb") as fh:
            fh.write(png)
        print("wrote", args.out, len(png), "bytes")
    if args.preview:
        import os
        from . import poster as P
        from .telegram import TelegramTransport, load_token
        tok = args.token or os.environ.get("ARC_INTEL_BOT_TOKEN") or load_token() or ""
        if not tok:
            print("no bot token")
            return
        TelegramTransport(tok).send_photo_bytes(
            args.preview, png, caption=P.poster_caption(1234.56, trader, aff, ""), parse_mode="HTML")
        print("sent preview to", args.preview)


if __name__ == "__main__":
    main()
