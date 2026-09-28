"""Single signing/decryption module — the ONLY place that imports `decrypt_secret`.

Everyone else asks this module to perform custody operations (withdraw, approve, swap, sign session
orders). Every decryption is recorded in an append-only audit log (uid, reason, caller, ts) — never
any key material.

Encryption key material is read from the process environment ONLY:
- `ARC_INTEL_SESSION_ENC_KEYS` (comma-separated; first = primary, used to encrypt; the rest decrypt).
- or `ARC_INTEL_ENC_KEY_FILE` (a file with the same comma-separated keys; should be mode 600, OUTSIDE
  the repo and the DB folder — e.g. `/etc/arc-intel/enc.keys` or a systemd credential).
- `ARC_INTEL_SESSION_ENC_KEY` (single key) is still accepted for back-compat.

Rotation: add a NEW key first (start encrypting with it); keep the old key(s) after it so existing
ciphertexts still decrypt. Once everything is re-encrypted, drop the old key(s).
"""
from __future__ import annotations

import os
import time


def _key_list() -> list[str]:
    multi = os.environ.get("ARC_INTEL_SESSION_ENC_KEYS")
    if multi:
        return [k.strip() for k in multi.split(",") if k.strip()]
    path = os.environ.get("ARC_INTEL_ENC_KEY_FILE")
    if path:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return [k.strip() for k in fh.read().replace("\n", ",").split(",") if k.strip()]
        except OSError:
            return []
    single = os.environ.get("ARC_INTEL_SESSION_ENC_KEY")
    return [single.strip()] if single else []


def _fernet():
    from cryptography.fernet import Fernet, MultiFernet
    keys = _key_list()
    if not keys:
        raise RuntimeError("no_enc_key")
    return MultiFernet([Fernet(k.encode()) for k in keys])


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def _decrypt_token(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


def _caller() -> str:
    import inspect
    for fr in inspect.stack()[2:]:
        mod = fr.frame.f_globals.get("__name__", "")
        if mod and mod.split(".")[-1] != "signer":
            return f"{mod}:{fr.function}"
    return "unknown"


def _audit(uid, reason: str) -> None:
    try:
        from bot.store import SubscriptionStore
        s = SubscriptionStore(os.environ.get("ARC_INTEL_DB", "/root/arc-intel/bot_subs.db"))
        try:
            s.log_key_audit(uid, reason, _caller(), int(time.time()))
        finally:
            s.close()
    except Exception:
        pass


def decrypt(chat, enc_secret: str, reason: str = "custody") -> str:
    """Decrypt a stored secret for `chat`, recording the access (never the material)."""
    _audit(chat, reason)
    return _decrypt_token(enc_secret)


# --- operation wrappers (callers never see a private key) ---------------------------------------

def withdraw(chat, enc_secret, token, to, amount_raw, rpc=None) -> str:
    from execution import custody as C
    return C.withdraw(decrypt(chat, enc_secret, "withdraw"), token, to, amount_raw, rpc=rpc)


def withdraw_native(chat, enc_secret, to, amount_wei, rpc=None) -> str:
    from execution import custody as C
    return C.withdraw_native(decrypt(chat, enc_secret, "withdraw_native"), to, amount_wei, rpc=rpc)


def ensure_approval(chat, enc_secret, token, rpc=None):
    from execution import custody as C
    return C.ensure_permit2_approval(decrypt(chat, enc_secret, "approve"), token, rpc=rpc)


def swap(chat, enc_secret, *, pool, token_in, amount_in, min_out, recipient, order_nonce,
         deadline=None, permit_nonce=None, rpc=None) -> str:
    from execution import custody as C
    pk = decrypt(chat, enc_secret, "swap")
    return C.swap(pk, pool=pool, token_in=token_in, amount_in=amount_in, min_out=min_out,
                  recipient=recipient, order_nonce=order_nonce,
                  deadline=int(deadline if deadline is not None else time.time() + 600),
                  permit_nonce=permit_nonce, rpc=rpc)


def sign_session_order(chat, enc_secret, typed_data) -> str:
    from execution.sessions import sign_session_order as _sign
    return _sign(decrypt(chat, enc_secret, "session"), typed_data)
