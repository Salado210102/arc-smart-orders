# ARC AI — Phase 5: Real Execution Architecture (DESIGN ONLY)

> Status: **design document**. No signing code, no key handling, no funds touched. This
> describes what would change to move from the Phase-4 **[PAPER]** flow to real execution,
> what must be true before production, and what an independent audit must cover.

## 1. Objective & scope

Turn the validated notification + paper product into a **non-custodial execution** product:
the user can act on an alert with one tap, **without the bot ever holding keys or funds**.

Out of scope here: writing execution/signing code, deploying contracts, moving funds.

Hard invariant carried from the whole project: **the LLM never signs, never holds keys, and
never has an execution code path.** It proposes; a deterministic, user-authorized path executes.

## 2. From PAPER (Phase 4) to REAL — what changes

| Concern | PAPER (today) | REAL (Phase 5) |
|---|---|---|
| Trigger | alert/`/approve` in bot | same |
| Approval engine | persisted approvals, cancel window, simulated 2FA | same + **real** 2FA, real deadlines |
| "Fill" | simulated at price(alert+delay), outcome vs hold | **on-chain** swap signed by the **user's** wallet |
| Key custody | none | **none** — user signs; bot/keeper hold nothing |
| Execution venue | — | Arc DEX (Uniswap v4 PoolManager, or the venue adapter) |
| Idempotency | dedup by (chat,kind,block) | **one signed intent → at most one fill**, on-chain enforced |
| Failure handling | retry next cycle | reconciliation + explicit recovery (no loss/duplication) |

## 3. Non-custodial execution flow

```
alert → bot proposes (Phase 4 approval: token, side, size, minOut, deadline)
      → user reviews; CANCEL WINDOW (revocable)
      → user CONFIRMS (real 2FA above threshold)
      → USER SIGNS an intent (EIP-712 + Permit2 witness) from their own wallet
      → EXECUTOR (keeper) submits the signed intent to the on-chain executor
      → contract enforces the signed minOut / deadline / nonce
      → fill emitted → bot monitors + reconciles → (paper-style) outcome recorded
```

The user's funds **never leave their wallet** until the fill; the executor can only fill
within the signed terms. This mirrors the existing `OrderExecutor` pattern (see §4).

## 4. Execution mechanism — reuse, don't rebuild

**Recommendation: reuse the Smart Orders non-custodial intent mechanism** (already live on Arc):
- User signs an off-chain intent (**EIP-712 `DcaIntent` + Permit2 witness**).
- A **keeper** submits it; the contract (`OrderExecutor.sol`) **enforces the signed `minOut`**
  — the keeper cannot redirect output or under-fill.
- Funds stay in the user's wallet until the fill.

**Audit status of the reused component (critical):** `OrderExecutor.sol` is **NOT independently
audited**. The repo contains only an *audit scope package* (`docs/AUDIT_SCOPE.md`, frozen at tag
`pre-audit-v2`) and a submission email; `docs/LAUNCH.md` states "**Not audited. Testnet first.**".
Therefore, reusing it does **not** lower the audit bar: either the audit must explicitly cover the
reused executor, or we fork a dedicated, separately-audited instance. This is recorded as an
audit-gating item (see §7.0).

What still has to be decided/proven for arc-intel:
1. **Venue = Uniswap v4 directly (decision, no adapter).** Almost all real Arc activity is v4
   pools (Argus and the rest), so an abstraction layer now is speculative complexity (same lesson
   as the launchpad ranking). The executor must support **v4 settlement** for launchpad tokens; a
   v3/v4 adapter is deferred until a second DEX shows real volume.
2. **Dedicated keeper instance (operational isolation).** Reuse the *contract mechanism*, but run a
   **separate keeper/worker for arc-intel** — never share the Smart Orders production keeper
   process, so an incident or product-specific bug in one cannot drag the other.
3. **minOut source**: the paper counterfactual shows large, fast moves right after an alert
   (delay matters). Real `minOut` must be computed from the live pool price at signing time
   with an explicit slippage cap; never an "ideal" price.
4. **Deadline**: short (e.g. seconds–minutes) to prevent stale fills in volatile pools.

## 5. What needs a real user signature (and only the user)

- The **intent** itself: `{token, side, amount, minOut, deadline, nonce, venue}` (EIP-712).
- **Permit2** authorization for the sold asset (if used).
- 2FA confirmation **above a spend threshold** (Phase-4 rule), now real instead of simulated.
  **2FA must use a channel genuinely separate from Telegram** (TOTP/authenticator, or email OTP):
  a second factor that also lives in Telegram is the same channel twice and is not a real factor.

The bot produces/attaches the intent structure and shows it; **only the user's wallet signs**.

## 6. Idempotency, failure modes & recovery (same standard as arc-intel)

Goal: **no execution is ever lost or duplicated**, even if the executor dies mid-operation.

- **Intent id / nonce**: each approval maps to exactly one intent with a unique `nonce`.
  On-chain executor rejects replays (nonce used once). Off-chain: approvals/deliveries are
  keyed and persisted (the pattern already used for `delivered`, `paper_alerts`).
- **Partial fill / revert**: if the tx reverts, the nonce stays unused on-chain; the bot
  reconciles status and either re-proposes or marks the intent failed — never silently retries
  with a different price without a new user signature.
- **Keeper crash mid-op**: no on-chain effect until the tx lands; the bot's reconciliation loop
  re-reads the tx/nonce and updates state. Idempotent because the chain is the source of truth.
- **Reorg**: track canonical block hashes (already a project rule) and re-verify; treat a
  reorged fill as unresolved until reconfirmed.
- **Reconciliation loop**: a job that, per intent, moves through
  `proposed → approved → signed → submitted → filled|failed|expired`, persisted, and never
  deletes history.

## 7. Independent-audit readiness checklist (before ANY production)

1. **Reused components** (§4): `OrderExecutor.sol` is **unaudited** ("Not audited. Testnet
   first."). The audit must either cover the reused contract in our flows, or cover a dedicated
   fork. Record this explicitly — do not assume inherited safety.
2. **Key custody**: prove the bot/keeper hold **no** user keys; signing is client-side; secrets
   only for read-only RPC/bot token. Threat-model the bot server (if compromised, no funds move).
2. **Approval handling**: cancel window enforced; expiry enforced; real 2FA threshold; no path
   where an approval executes without an explicit user signature; approval replay impossible.
3. **Executor contract**: `minOut`/`deadline`/`nonce` enforced on-chain; no owner can alter a
   pending user intent; access control (owner = Safe) reviewed; upgradeability (if any) reviewed.
4. **Failure points**: keeper down mid-op, RPC outage, nonce reuse, partial fill, price gap,
   gas spike, MEV/sandwich during fill — documented behavior + tests for each.
5. **No loss / no duplication**: fuzz/property tests for "one intent → at most one fill";
   reconciliation proves state converges; adversarial reorg tests.
6. **Venue correctness**: v4 settlement path (router/hook) reviewed; sticky/pool state read
   correctly; `minOut` computed against the real pool.
7. **Monitoring/alerts**: on-chain monitoring of executor + keeper liveness; a filled/among
   invariants; anomaly alerts (already have the alert infra).
8. **Operational**: rate limits, circuit breaker/pause, incident runbook, key rotation.

## 8. Decisions (resolved) & remaining items

Resolved:
- **Venue: Uniswap v4 directly** (no adapter until a second DEX shows real volume).
- **Reuse the contract mechanism, with a dedicated arc-intel keeper** (operational isolation).
- **2FA: separate channel** (TOTP/email), not Telegram-only.
- **Notional caps: conservative low default** at launch; the user must explicitly opt in to raise
  them, so max possible damage per user is bounded by design, not luck.

Remaining before implementation:
- Exact v4 settlement path (which router/periphery wrapper to whitelist as swap target).
- Client signing UX (Telegram WebApp needs HTTPS/domain; alternatives: deep-link to a wallet,
  or a small hosted signing page).
- Audit vendor + scope (covering the reused executor or a fork).

## 9. Non-goals / explicit safety

- No key custody by the bot. No autonomous execution. No "AI signs" path.
- No production until an **independent audit** signs off on §7.
- The **[PAPER]** flow and the live **notification** product remain the shipped value until then.
