"""Admin CLI for the closed-beta allowlist (no manual DB edits).

Usage:
  python -m bot.admin --add <chat_id>
  python -m bot.admin --remove <chat_id>
  python -m bot.admin --list
  python -m bot.admin --requests
  python -m bot.admin --set-admin <chat_id>
"""
from __future__ import annotations

import argparse

from .store import SubscriptionStore


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="/root/arc-intel/bot_subs.db")
    ap.add_argument("--add", type=str)
    ap.add_argument("--remove", type=str)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--requests", action="store_true")
    ap.add_argument("--set-admin", type=str)
    args = ap.parse_args()
    st = SubscriptionStore(args.db)
    acted = False
    if args.set_admin:
        st.set_state("admin_chat", str(args.set_admin))
        print(f"admin_chat = {args.set_admin}")
        acted = True
    if args.add:
        st.add_allow(args.add)
        print(f"allowed {args.add}")
        acted = True
    if args.remove:
        print(("removed " if st.remove_allow(args.remove) else "not in allowlist ") + args.remove)
        acted = True
    if args.list:
        print("allowlist:", st.list_allow())
        acted = True
    if args.requests:
        print("requests:", st.list_requests())
        acted = True
    if not acted:
        print("admin_chat:", st.get_state("admin_chat"))
        print("allowlist:", st.list_allow())
        print("requests:", st.list_requests())
    st.close()


if __name__ == "__main__":
    main()
