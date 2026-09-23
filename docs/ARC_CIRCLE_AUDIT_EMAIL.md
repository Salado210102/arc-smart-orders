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
