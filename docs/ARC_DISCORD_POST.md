# Arc Discord / community — post draft

> Post in the Arc Discord (`discord.com/invite/buildonarc`) — best channel: `#builders` / `#showcase`
> (or `#grants` if one exists). Two versions below. Post from your own account.

---

## Short version (for `#showcase`)

> Hey Arc builders 👋
>
> I shipped **Arc Smart Orders + Agent Launchpad** (MIT): non-custodial **limit/stop/DCA/grid orders on USDC⇄EURC**
> using **Permit2 `permitWitnessTransferFrom`** (the witness is recomputed on-chain, so the keeper can never
> redirect or under-fill), plus a launchpad where a **launching AI agent gets an ERC-8004 identity, a USDC
> bonding-curve token, ERC-8183 job escrow, locked LP, and an ERC-4626 vault that pays the agent's USDC
> revenue to stakers**.
>
> Live on **Arc testnet** (deployed + verified, full agentic E2E with tx hashes) → UI: https://launchpad-neon-chi.vercel.app
> Code: https://github.com/Salado210102/arc-smart-orders
>
> Two questions for the team 👇
> 1. **When will ERC-8004 / ERC-8183 be live on Arc mainnet?** The registries exist on testnet but have
>    **no code on mainnet** yet, which blocks the launchpad from going live there.
> 2. Is there a **grants / ecosystem** channel or form for builders? I couldn't find one on arc.network /
>    docs.arc.io (the docs still say "Testnet only" 🙂).
>
> Also happy to use **App Kit Swap / StableFX** as the execution venue instead of a mock — anyone integrating it yet?

---

## Longer version (for `#builders`)

> **Arc Smart Orders + Agent Launchpad** — non-custodial FX orders + an AI-agent launchpad, built only on the
> Arc + Circle stack (USDC as gas, Permit2, ERC-8004, ERC-8183).
>
> **Orders:** users sign a Permit2 `permitWitnessTransferFrom` with an on-chain witness (`tokenOut`, `minOut`)
> or a `DcaIntent`; a keeper fills through a whitelisted venue and the executor **recomputes the commitment**,
> so fills can't be redirected/under-filled. Input-side 0.30% fee → a **Safe 2/2** treasury.
>
> **Launchpad:** launch an agent → ERC-8004 identity + a USDC bonding curve (`k=x·y`), graduation seeds LP
> (**locked 365d**), and an **ERC-4626 vault** that distributes the agent's USDC revenue 70/30 to
> stakers/treasury. The keeper submits fills as **ERC-8183** deliverables.
>
> **Status:** testnet deployed + verified, **34/34 tests**, live UI, persistent keeper (HTTP + WebSocket +
> SQLite). Mainnet deploy rehearsed with the **Safe 2/2** as owner/treasury (the Safe executed the owner-only
> wiring tx).
>
> **Asks:** (1) ERC-8004/8183 on **mainnet** ETA? (2) grants/ecosystem channel? (3) interest in App Kit
> Swap / StableFX as the production venue?
>
> Links: UI https://launchpad-neon-chi.vercel.app · code https://github.com/Salado210102/arc-smart-orders ·
> contact hello@basepump.dev

---

### Before posting
- [ ] Replace anything that changed (addresses/tests) — verify against `DEPLOYMENTS.md`.
- [ ] Attach 1 screenshot of the Agents tab (the redesigned UI).
- [ ] Don't paste secrets or the Safe signer addresses; the Safe address is public and fine.
