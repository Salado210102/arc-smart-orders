# Audit submission email (corrected) — `pre-audit-v2`

> ⚠️ **Correction applied:** the Safe address in the original draft
> (`0x0FBFAF72ef2fFA3C1EE5DCA53e9Eeb7fFef07e93`) **has no contract code** — it is wrong.
> The real, on-chain-verified 2/2 Safe is **`0x0FBFAF7069B45Dd9c16AdD8a04Bf556046EA7e93`**
> (Arc mainnet: `getThreshold()=2`, `getOwners()=[0x3df3…c977, 0xE34A…1279]`).
> **Use the address below.** Do not send the draft as-is.

---

**Subject:** Arc Agentic Launchpad & Smart Orders — Official Audit Package Submission (pre-audit-v2)

Dear Review & Grants Team,

We are pleased to submit the finalized audit package for our DApp protocol on Circle's Arc Network. The
codebase is frozen, deterministically compiled, and verified under Solc 0.8.26 (EVM: Cancun, `via_ir: true`).

**Key Submission Links & References:**
- Frozen Release Tag (v2): https://github.com/Salado210102/arc-smart-orders/releases/tag/pre-audit-v2
- Public Repository: https://github.com/Salado210102/arc-smart-orders
- Master Audit Package: https://github.com/Salado210102/arc-smart-orders/blob/pre-audit-v2/docs/AUDIT_PACKAGE.md
- Audit Scope: https://github.com/Salado210102/arc-smart-orders/blob/pre-audit-v2/docs/AUDIT_SCOPE.md

**Protocol Testing & Bytecode Verification Metrics:**
- Test Coverage: 34/34 passing unit/integration tests (Orders: 17, Launchpad: 8, Graduation: 3, Staking: 5, Revenue-Wiring: 1).
- Mainnet Dry-Run: 1/1 passing Arc Mainnet Fork test validating full deployment invariants.
- Deterministic Safe Governance: 0x0FBFAF7069B45Dd9c16AdD8a04Bf556046EA7e93
- Bytecode Constraints: Maximum size is AgentFactory at 12,971 B (11.6 kB buffer below the 24,576 B EVM limit). All other contracts measure < 6,000 B.

All operational risk considerations, system invariants, failure modes, and dependency requirements
(ERC-8004 / ERC-8183 registries) are fully detailed in AUDIT_PACKAGE.md.

We look forward to your review and next steps regarding the UFSF audit process.

Best regards,
Vicente — Lead Quantitative Engineer

---

## Before sending — checklist

- [ ] **Safe address corrected** to `0x0FBFAF7069B45Dd9c16AdD8a04Bf556046EA7e93` (done above).
- [ ] **UFSF eligibility:** the UFSF portal requires the applicant to be a **registered legal entity**
      (LLC/corp) + KYB. As an independent builder with no entity yet, target **Circle / Arc ecosystem
      grants** (or the Arc Discord route in `ARC_DISCORD_POST.md`) rather than the UFSF form.
- [ ] Consider adding the **live UI** link (`https://launchpad-neon-chi.vercel.app`) and the **Arc-mainnet
      blocker** note (ERC-8004/8183 not deployed on mainnet yet) so reviewers understand the dependency.

## Notes / alternatives

- The **Safe above lives on Arc mainnet**. Verify it on
  `https://explorer.arc.io/address/0x0FBFAF7069B45Dd9c16AdD8a04Bf556046EA7e93`.
- If the contact is **Circle** (not UFSF), drop the final "regarding the UFSF audit process" line and say
  "regarding an audit / ecosystem support".
