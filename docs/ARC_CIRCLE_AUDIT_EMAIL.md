# Audit support email — Arc / Circle (short)

> Target recipients: **Circle / Arc ecosystem grants**, the **Arc team** (Discord/forum), or an
> audit-programme contact. Attach nothing sensitive: all links are public. Use the **Arc/Circle**
> proposal (`ARC_CIRCLE_AUDIT_PROPOSAL.md`), not the Uniswap one.

---

**Subject:** Audit support request — Arc Smart Orders + Agent Launchpad (live on Arc mainnet)

Hi [name / team],

I'm **Vicente Gonzalez**, an independent builder. I shipped **Arc Smart Orders + Agent Launchpad** on
**Arc mainnet** — a non-custodial smart-order engine (USDC ⇄ EURC) plus an AI-agent launchpad, all
**USDC-native** and using Circle's **ERC-8004 / ERC-8183** standards.

I'm requesting **support for an independent security audit** of the **fund-bearing core** (9 contracts,
~1,411 SLOC; `OrderExecutor`, `AgentBondingCurve`, `AgentStakingVault`, …). It's ready to audit today:

- **Live**: https://arc.basepump.dev · API (HTTPS) https://api.basepump.dev/arc-keeper/health
- **Code (MIT, frozen `pre-audit-v2`)**: https://github.com/Salado210102/arc-smart-orders
- **Audit package / scope**: `docs/AUDIT_PACKAGE.md` · `docs/AUDIT_SCOPE.md`
- **Maturity**: Foundry suite green (34/34 core + 30 more); full testnet E2E (agentic run + a fill to
  `FILLED`); persistent keeper 24/7; Safe 2/2 owns every contract.
- **Deployments & tx hashes**: `DEPLOYMENTS.md`

I'm happy to co-fund a portion, and open to a **competitive/community audit** (Code4rena / Cantina /
Sherlock / CodeHawks) if that fits your programme better. Proposal with scope and budget indication:
`docs/ARC_CIRCLE_AUDIT_PROPOSAL.md`.

Thanks for considering it — happy to jump on a call or provide any extra detail.

Best regards,
**Vicente Gonzalez**
hello@basepump.dev · X @VICENTEGon651262 · Telegram @Cryptofun2026
https://arc.basepump.dev · https://github.com/Salado210102/arc-smart-orders

---

## Before sending — checklist

- [ ] Replace `[name / team]` with the recipient.
- [ ] Pick the channel: Circle/Arc grants form · Arc Discord (`#builders`/`#showcase`) · direct contact.
- [ ] Verify links resolve (repo is public; tag `pre-audit-v2` exists).
- [ ] Keep it short if posting in Discord (drop the signature to one line).
- [ ] Do **not** claim "audited" — the code is **unaudited**; this is an audit *request*.
- [ ] If a programme requires a legal entity, route to one that accepts **individuals** (Arc/Circle).

## Notes

- Safe (Arc mainnet): `0x0FBFAF7069B45Dd9c16AdD8a04Bf556046EA7e93`
  (<https://explorer.arc.io/address/0x0FBFAF7069B45Dd9c16AdD8a04Bf556046EA7e93>).
- The **cross-chain** and **Phase-2 credit** modules are out of this audit scope (draft, no funds).

---

## Channels (if you can't write in Discord)

You don't need Discord. Use any of these:

1. **Reply to the Arc Microgrants email thread** you already have (fastest — same program, individuals
   accepted). Add a short paragraph asking whether the grant can be **earmarked for an audit**.
2. **Arc House** → <https://community.arc.io> — post the short version below (or reply to your approved
   post). This is where your launch post already got approved.
3. **X** → public reply/DM to **@arc** (and/or Circle) linking the proposal.
4. **Email** → if you know a grants/ecosystem contact, use it. Note: the only Circle address we have is
   `sales@circle.com`, which is **StableFX sales** — not grants.

### Arc House — short post (paste)

**Title:**
```
Looking for audit support — Arc Smart Orders + Agent Launchpad (live on mainnet)
```

**Body:**
```
Hi all — I'm Vicente, an independent builder. I shipped Arc Smart Orders + Agent Launchpad on Arc
mainnet: non-custodial smart orders (USDC ⇄ EURC) + an AI-agent launchpad using Circle's ERC-8004/8183.
DApp: https://arc.basepump.dev

The fund-bearing core is live and I'd like it independently audited (9 contracts, ~1.4k SLOC:
OrderExecutor, AgentBondingCurve, AgentStakingVault, …). I've prepared a full audit package and a short
proposal, and I'm looking for ecosystem audit support, introductions, or a pointer to the right program.
Open to a competitive/community audit too.

• Repo (MIT, frozen pre-audit-v2): https://github.com/Salado210102/arc-smart-orders
• Audit package: https://github.com/Salado210102/arc-smart-orders/blob/pre-audit-v2/docs/AUDIT_PACKAGE.md
• Scope: https://github.com/Salado210102/arc-smart-orders/blob/pre-audit-v2/docs/AUDIT_SCOPE.md
• Proposal: https://github.com/Salado210102/arc-smart-orders/blob/main/docs/ARC_CIRCLE_AUDIT_PROPOSAL.md

Thanks!
```

### Arc Microgrants — reply (paste into the existing thread)

**Subject:**
```
Re: Arc Microgrants — audit support for my submission
```

**Body:**
```
Hi Arc team,

Quick follow-up on my Arc Microgrants submission (Arc Smart Orders + Agent Launchpad).

The protocol is live on Arc mainnet and the fund-bearing core is ready to be independently audited —
9 contracts / ~1,411 SLOC (OrderExecutor, AgentBondingCurve, AgentStakingVault, …). Package & proposal:
- Repo (MIT, frozen pre-audit-v2): https://github.com/Salado210102/arc-smart-orders
- Audit package: https://github.com/Salado210102/arc-smart-orders/blob/pre-audit-v2/docs/AUDIT_PACKAGE.md
- Audit scope: https://github.com/Salado210102/arc-smart-orders/blob/pre-audit-v2/docs/AUDIT_SCOPE.md
- Proposal: https://github.com/Salado210102/arc-smart-orders/blob/main/docs/ARC_CIRCLE_AUDIT_PROPOSAL.md
- Deployments: https://github.com/Salado210102/arc-smart-orders/blob/main/DEPLOYMENTS.md

If the grant can be applied toward an audit — or if you can point me to the right audit program or
partner — I'd really appreciate it. I'm happy to share line-item quotes or run a competitive audit.

Thanks!
Vicente Gonzalez
hello@basepump.dev · https://arc.basepump.dev
```

