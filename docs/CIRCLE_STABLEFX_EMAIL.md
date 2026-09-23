# Circle StableFX — access request (ready to send)

> Send to **sales@circle.com** (verified in the Circle StableFX docs: *"Reach out to your Circle
> representative"*). Attach nothing sensitive; the links are public.

---

**Subject:** StableFX API access — execution venue for a non-custodial USDC⇄EURC order engine on Arc

Dear Circle StableFX team,

I am an independent builder shipping **Arc Smart Orders + Agent Launchpad**, a non-custodial protocol on
**Arc** (USDC-native), and I would like to request **StableFX API access** to use it as the execution venue
for our FX order engine.

**What we built (live on Arc testnet, open source, MIT):**
- A non-custodial **limit / DCA order engine** for **USDC ⇄ EURC**. Users sign a Permit2
  `permitWitnessTransferFrom` (witness = `tokenOut,minOut`) or an EIP-712 `DcaIntent` off-chain; a keeper
  fills on-chain, and the executor **recomputes the commitment** so it can never redirect the output or
  under-fill. The swap leg is a **pluggable `swapTarget`**.
- An **Agent Launchpad**: an AI agent gets an ERC-8004 identity, a USDC bonding-curve token, ERC-8183 job
  escrow, locked LP, and an ERC-4626 vault that pays the agent's USDC revenue to stakers.

**The ask:** a **StableFX API key** (taker) for USDC⇄EURC on Arc, so our keeper can settle swaps through
StableFX's smart-contract escrow instead of a mock venue. We are also happy to explore the **maker** side
later. We already target the Arc **`FxEscrow`** (`0xe2E5F173576B513d994073CCbDaCBE027d43DFe6`) as the
settlement contract.

**Links:**
- Repo: https://github.com/Salado210102/arc-smart-orders (frozen tag `pre-audit-v2`)
- Audit package: https://github.com/Salado210102/arc-smart-orders/blob/pre-audit-v2/docs/AUDIT_PACKAGE.md
- Live UI (testnet): https://launchpad-neon-chi.vercel.app

Happy to complete any KYB/onboarding step required for StableFX access.

Best regards,
Vicente Gonzalez — BasePump · hello@basepump.dev · @Cryptofun2026

---

## Notes

- StableFX is **permissioned** (RFQ, institutional). Pending access, the order engine keeps using a
  whitelisted testnet router; the graduation venue is a separate open question (see `MAINNET_RUNBOOK.md` §2.3).
- `sales@circle.com` is a **sales** channel; if they point elsewhere for the Agent/Arc track, follow up there.
