# Arc AI / SNIPER IA — Security Remediation Report (Blocks A, B, C)

**Project:** Arc AI / SNIPER IA — `arc-intel` (Telegram risk bot + Mini App + custodial wallet + V2/V3 executor)
**Repo:** https://github.com/Salado210102/arc-smart-orders
**Networks:** Arc mainnet `5042` · testnet `5042002`
**Date:** 2026-09-28
**Prepared for:** independent security auditor
**Ask:** review the remediations below and advise on the **open questions** (§6).

---

## 0. Artifacts & references

| Ref | Value |
|---|---|
| Block A commit | `9cc2a60` |
| Block B commits | `35f9466`, `970758c` (+ docs `d6cea42`) |
| Block C commit | `9f34297` |
| Frozen V1 tag | `arc-intel-executor-v1` (untouched) |
| **New pre-audit tag** | **`arc-intel-executor-v3-pre-audit`** (V2/V3 + signer/custody scope) |
| Deployed testnet executor (live) | `0xBD1a802da39cf7FcF8437F23e0F63f13BD6e678d` (owner=relayer, `isTestnet=true`, `allowAllPools=true`) |
| Service | `https://app.basepump.dev` (sign server + bot; Arc **testnet**) |

Detail docs: `ARC_AI_AUDIT_BLOCK_A_REPORT.md`, `ARC_AI_AUDIT_BLOCK_B_CONTRACTS_REVIEW.md`,
`ARC_AI_EXECUTOR_V2V3_SLITHER_TRIAGE.md`, `ARC_AI_EXECUTOR_V3_AUDIT_SCOPE.md`, `ARC_AI_SESSION_KEYS.md`.

**Test evidence (final):** Python **422 passed / 0 failed** · Foundry **57 passed / 0 failed / 1 skipped**
(unit + invariant campaigns V1/V2/V3 at **5000×100**).

---

## 1. Executive summary

| Block | Area | Status |
|---|---|---|
| **A** | Custody & Mini App hardening (5 findings) | **Fixed + tested + deployed** |
| **B** | V2/V3 contracts review (B1–B4) + invariants + Slither | **Fixed + tested** (testnet redeployed) |
| **C** | Cleanup (research isolation, hermetic tests, contest anti-wash, README) | **Done** (C3 partially wired) |

No **applicable High/Medium** issues remain open from Slither. The remaining items (§6) are either
**best-practice** (unchecked ERC20 transfer → SafeERC20) or **product/operational** decisions (key
management, KYC/AML for custody, mainnet plan, anti-wash wiring).

---

## 2. Block A — Custody & Mini App

### A1 — Withdrawal brakes (critical)
- **Freshness:** `initData` `max_age = 300 s` on `/custody/{create,withdraw,buy,sell,address,totp}` and
  `/session/authorize`; reads stay 24 h.
- **TOTP 2FA** (RFC 6238, no deps) required to register an address and to withdraw; secret stored
  **encrypted**.
- **Registered withdrawal addresses** with **24 h delay** before usable; Telegram notice on add.
- **Daily withdrawal cap** per user (default 50 USDC, `ARC_INTEL_WITHDRAW_DAILY_USDC`).
- **Freeze:** Telegram notice + **"🛑 No fui yo"** button on every withdraw/address-add → freezes the
  account; unlock with **`/unfreeze <TOTP>`**.
- **Global kill-switch** `/pause_custody` / `/resume_custody` (stops custody trading + withdrawals).
- **Rate limit** 20 req/60 s per user on `/custody/*`.
- **Evidence:** `test_sign_server.py` (private_key rejected; no key leak; **stale initData → 401**;
  not-allowlisted → 403; paused → 423), `test_totp.py` (RFC vectors), `test_custody_security.py`,
  `test_commands.py::test_security_enroll_and_addaddr`.

### A2 — No private-key import
- `/custody/create` **rejects** `private_key` (`private_key_not_allowed`); only bot-generated wallets.
- **Evidence:** HTTP test asserts no `private_key` in the creation response.

### A3 — Mini App XSS / CSP
- `security/urls.py` (`safe_url`, `sanitize_dex`): **only absolute `https://`**; rejects `javascript:`,
  `data:`, `http:`, malformed; applied **server** (`bot/miniapp_data.py`) **and client** (`httpsUrl`).
- `rel="noopener noreferrer"` on external links; inline `onerror` handlers removed.
- **Strict CSP** with the inline-script **SHA-256 hash**: `default-src 'self'`, `script-src` only
  `'self'`/telegram.org/esm.sh + hash, `frame-ancestors` restricted to Telegram, `object-src 'none'`;
  plus `X-Content-Type-Options`, `Referrer-Policy`.
- **Evidence:** `test_urls.py` (`javascript:alert(1)`, `data:text/html`, `"><img onerror=…>`,
  `sanitize_dex`, `_csp`).

### A4 — Centralized key handling
- **`execution/signer.py`** is the **only** module that decrypts; all call sites migrated
  (`sign_server`, `telegram`, `autoprotect`, `copy_keeper`, `session_keeper`).
- **MultiFernet** (rotation) with keys from `ARC_INTEL_SESSION_ENC_KEYS` / `ARC_INTEL_ENC_KEY_FILE`
  (600, outside repo/DB); appended **append-only audit** (`key_audit`: uid/reason/caller/ts; never key
  material). **Per-wallet caps**: max balance / per-trade / per-day. **Custody creation allowlist.**
- **Evidence:** `test_signer_only.py` (**fails if any other module references `decrypt_secret`**),
  `SignerTests` (audit, MultiFernet rotation, error leaks no material).

### A5 — Network/origin
- `ARC_INTEL_ALLOWED_ORIGIN` **no default** → **no CORS** unless explicitly set.
- `execution/custody.py` **requires** `ARC_RPC` and `ARC_INTEL_CHAIN_ID` and calls **`verify_chain()`**
  (RPC `eth_chainId` must match config; **refuses to sign** otherwise), invoked per tx.

---

## 3. Block B — Executor V2/V3

### B1 — Invariants + Slither + coverage
- **Invariants** (`ArcIntelExecutorV2/V3.invariants.t.sol`, **5000 runs × depth 100**): `spent ≤ maxTotal`;
  revoked/expired session never fills; `recipient == user`; session only touches its `poolId`/`tokenIn`;
  single-use nonce; executor holds 0; `pause` absolute. **Pass.**
- **Slither** (`ARC_AI_EXECUTOR_V2V3_SLITHER_TRIAGE.md`): 102 detectors, 14 results each — detectors:
  `reentrancy-balance` (High), `unchecked-transfer` (High), `unused-return` (Medium), `timestamp` (Low),
  `assembly`/`cyclomatic-complexity`/`naming-convention` (Info). **No applicable High/Medium**
  (`reentrancy-balance` = by-design false positive; `unchecked-transfer` = fail-safe).
- **V3 coverage** raised **4 → 11** tests (allowedHooks, allowAll, revoked hook, foreign hook, **hostile
  allowed hook contained**, zero recipient, deadline witness, mainnet gate).

### B2 — `allowAllPools`
- **On-chain gate:** V3 stores `isTestnet`; `setAllowAllPools(true)` **reverts** `AllowAllNotAllowed`
  when `!isTestnet`. **Deploy script `DeployV3.s.sol` requires** `!isTestnet && !allowAllPools &&
  owner==Safe` (fails otherwise).
- **On-chain state (read-only, testnet):**

| Executor | owner | paused | allowAllPools | isTestnet |
|---|---|---|---|---|
| V2 `0xb6393A…53B56` | Safe `0xe911D6…86b7` | false | — (V2) | — |
| V3 `0xC9E5d1…9Afd2` | Safe `0xe911D6…86b7` | false | **false** | — (old bytecode) |
| V3 old `0x5e938A…55E9c14` | relayer `0x5ce3F7…7A98f` | false | **true** | — (obsolete) |
| **V3 new `0xBD1a80…6e678d`** | relayer `0x5ce3F7…7A98f` | false | **true** | **true** |

`allowedHooks` for known pool hooks on the live V3 = **false** (allowAll is on).

### B3 — Session key risk
- Documented in `ARC_AI_SESSION_KEYS.md`: **max loss = `maxTotal` at the worst price allowed by
  `minOutFloor`**; output always goes to `user`.
- **Conservative defaults** (maxTotal 50 / maxPerOrder 25 / ttl 6 h) + **`minOutFloor` from a live quote**
  at max slippage (50%). Mini App shows caps + **revoke** button.

### B4 — Audit package
- `ARC_AI_EXECUTOR_V3_AUDIT_SCOPE.md`: scope = **V2, V3, interfaces + signer + custody + eip712 +
  preorders + sessions**; **SHA-256 manifest**; tag **`arc-intel-executor-v3-pre-audit`**.

### B1–B4 findings fixed
| # | Finding | Severity | Status |
|---|---|---|---|
| B1 | `execute` (v1) accepted `recipient == 0` | Low | **Fixed + test** |
| B2 | `deadline` not signed in v1 witness | Low | **Fixed + test** |
| B3 | `allowAllPools` bypasses pool+hook policy | Medium (operational) | **Fixed** (`isTestnet` gate) |
| B4 | static `DOMAIN_SEPARATOR` (fork) | Low | **Fixed** (dynamic) |

---

## 4. Block C — Cleanup

- **C1:** `indexer/smart_money.py` → **`research/smart_money.py`** (+ `research/README.md` warning);
  `tests/test_no_research_imports.py` **fails if `bot/`/`execution/` import research code**.
- **C2:** `test_serves_miniapp_page` made **hermetic** (repo-relative path) → Python suite **100% green**.
- **C3:** `monetization/antiwash.py` + `store.contest_volume_between/_referred_volume_between`, wired into
  `/contest` and `publish_round`. **Prize payout behind a feature flag**, **off by default**
  (`ARC_INTEL_PRIZE_PAYOUT` / `store.set_prize_payout`).
- **C4:** `README.md` updated with the real `arc-intel` architecture + "not connected" list.

---

## 5. Test evidence

- **Python:** `python -m pytest -q` → **422 passed / 0 failed.**
- **Foundry:** `forge test` (unit + invariants V1/V2/V3, **5000×100**) → **57 passed / 0 failed / 1 skipped**.
- **Slither:** V2/V3 → no applicable High/Medium.

---

## 6. Open items / questions for the auditor

1. **`unchecked-transfer` (Low).** `_settle`/refund ignore ERC20 `transfer` return; we argue it is
   fail-safe (flash-accounting reverts; dust stays in the executor). Fix = **SafeERC20/`require`**, which
   **changes V2/V3 bytecode** → **we did not apply it (awaiting your call).** Recommend? 
2. **`reentrancy-balance` (High FP).** Confirm the by-design false positive (nonReentrant + recipient
   balance delta; a decrease only fails `minOut`).
3. **`allowAllPools` on testnet.** Acceptable for testnet only? Any residual concern with `allowedHooks`
   (a whitelisted but malicious hook) on mainnet — we added a hostile-hook containment test.
4. **Custody key management.** Single signer + MultiFernet, keys from env/600 file. Is this sufficient for
   mainnet, or do you require an HSM/KMS/MPC + systemd credentials + key ceremony?
5. **Custody legal.** Handling third-party funds ⇒ **KYC/AML** and liability review (flagged; not done).
6. **Session keys (Option 3).** Kept but **deprecated** in favour of custody for speed. Audit them, or
   drop them from scope?
7. **Mainnet deploy plan.** `owner = Safe`, `isTestnet=false`, **no `allowAllPools`**, policy by
   `allowedPools`/`allowedHooks`. Review the plan before we deploy?
8. **C3 anti-wash.** `min_notional` + round-trips are **live**; **own-token**, **same-funding** and
   **thin-market ("no real market")** are **implemented + tested as pure functions but not yet wired** to
   the on-chain creator/funding maps. Priority?

---

## 7. Non-goals / known limitations (for context)

- **Fees are not collected yet** ⇒ referrals (30%), the contest pozo and fee tiers are **informational**.
- **Data is mainnet; executor/wallet/relayer are testnet** ⇒ copy-trading runs in **dry-run**; no mainnet
  token trades on testnet.
- **V1 executor frozen** (`ArcIntelExecutor.sol`, tag `arc-intel-executor-v1`) — **not modified**.
