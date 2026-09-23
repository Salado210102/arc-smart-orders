# Arc Smart Orders — Agentic, non-custodial order infrastructure on Arc

> **Live on Arc testnet.** Limit & TWAP orders for stablecoin FX (USDC ⇄ EURC) that are
> **non-custodial**, **agent-native** (ERC-8004 identity + ERC-8183 job escrow), and settle with
> **gas in USDC** under **sub-second finality**.

- Repo: https://github.com/Salado210102/arc-smart-orders
- Deployments & tx tree: [`DEPLOYMENTS.md`](../DEPLOYMENTS.md)
- Executor: [`contracts/src/OrderExecutor.sol`](../contracts/src/OrderExecutor.sol) · SDK: [`sdk/src/index.ts`](../sdk/src/index.ts) · Keeper: [`keeper/src/index.ts`](../keeper/src/index.ts)

---

## 1. The problem

On-chain "orders" usually mean one of two bad options: a **custodial bot** holding your funds, or a
**plain permit/approval** that only commits *how much* a spender may move — not *what* it is
exchanged for, nor at what price. When a keeper is compromised or buggy, it can swap to a worthless
token or fill at a terrible rate.

## 2. The thesis: enforce the intent, not the operator

Arc Smart Orders makes the **order intent** the source of truth:

- The user (or an **AI agent**) signs an order **off-chain** (EIP-712).
- A **keeper** executes it on-chain through a verified **`OrderExecutor`** that **recomputes the
  signed commitment** and reverts if the outcome doesn't match.
- Funds never leave the wallet until the fill, and any leftover is refunded.
- **Agents are first-class**: the keeper is an **ERC-8004** identity, and execution is paid for via
  **ERC-8183** job escrow — so an AI agent can *hire* execution and *build reputation* trustlessly.

Why Arc: **USDC is the gas token** (~$0.001/tx), **finality is instant/deterministic**, and the
canonical **ERC-8004 / ERC-8183 / Permit2** contracts are already deployed.

---

## 3. Architecture flow

```
        ┌──────────────┐    sign order (EIP-712, off-chain)   ┌──────────────────┐
        │  CLIENT /    │ ───────────────────────────────────► │   Order store    │
        │  AGENT (A)   │    • LIMIT  = Permit2 + witness       │  (API / file)    │
        │  ERC-8004 id │    • TWAP   = PermitSingle + intent   └────────┬─────────┘
        └──────┬───────┘                                                │ poll
               │ createJob(provider=B, evaluator=C)                     ▼
               │ fund escrow (USDC)                          ┌──────────────────┐
               ▼                                             │  KEEPER (B)      │  ERC-8004 agent
        ┌──────────────┐   beforeAction/afterAction (opt.)    │  • picks route   │
        │  ERC-8183    │ ◄─────────────────────────────────► │  • builds calldata│
        │ Agentic      │                                     └────────┬─────────┘
        │ Commerce     │                                              │ executeOrder / executeDca
        │ (job escrow) │                                              ▼
        └──────┬───────┘                                     ┌──────────────────────────┐
               │ complete → pay B                            │  OrderExecutor (Arc)     │
               ▼                                             │  1) Permit2 pull (exact) │
        ┌──────────────┐    giveFeedback (ERC-8004)           │  2) call whitelisted DEX │
        │ VALIDATOR /  │ ───────────────────────────────────► │  3) refund leftover      │
        │ EVALUATOR (C)│    checks deliverable == keccak256(fillTx)  4) verify minOut/rate│
        └──────────────┘                                     └──────────────────────────┘
```

**End-to-end roles (3 separate wallets — collusion-resistant):**
- **A · Client/Agent** — signs the intent, creates the ERC-8183 job, funds escrow.
- **B · Keeper/Executor Agent** — registered on ERC-8004; fills the order and submits the deliverable.
- **C · Validator/Evaluator** — verifies the proof, releases escrow, records ERC-8004 reputation.

---

## 4. ERC-8004 + ERC-8183 integration spec

### 4.1 Signing flows (the "intent")

| Order | Permit2 flow | Commits (enforced on-chain) |
|---|---|---|
| **LIMIT** (one-shot) | `permitWitnessTransferFrom` + **witness** | `OrderIntent(tokenOut, minOut)` |
| **TWAP** (recurring) | `AllowanceTransfer` (`PermitSingle`) + **signed intent** | `DcaIntent(owner, tokenIn, tokenOut, maxAmountIn, minRate, deadline)` |

For LIMIT, the executor **recomputes the witness** from the actual `tokenOut`/`minOut` it is about to
execute → a keeper cannot redirect or under-fill. For TWAP, the `DcaIntent` (domain
`name="ArcSmartOrders", version="1"`) is verified on **every** part.

### 4.2 Identity & payment (agent-native execution)

| Standard | Contract (Arc testnet) | Role |
|---|---|---|
| ERC-8004 | IdentityRegistry `0x8004A818…BD9e` | `register(metadataURI)` → agent NFT; `ownerOf` |
| ERC-8004 | ReputationRegistry `0x8004B663…8713` | `giveFeedback(agentId, score, …)` (owner can't self-deal) |
| ERC-8004 | ValidationRegistry `0x8004Cb1B…4272` | `validationRequest` / `validationResponse` |
| ERC-8183 | AgenticCommerce `0x0747EEf0…4583` | job escrow: create → fund → submit → complete |

### 4.3 Deliverable verification pattern

ERC-8183 hooks require **admin whitelisting**, so we use the **non-hooked path** and link the job to
the order **off-chain, verifiably**:

```
provider.submit(jobId, deliverable = keccak256(fillTxHash))
```

The evaluator independently checks that the on-chain fill matches the signed intent (tokenOut, minOut,
amount), then `complete(jobId, reason)` releases escrow to the keeper. No whitelist, no custody.

### 4.4 Verified on-chain (Arc testnet — see `DEPLOYMENTS.md`)

| Step | Tx |
|---|---|
| ERC-8004 `register` (agent **896807**) | `0xf6a2aeff…f8a5` |
| ERC-8183 `createJob` (job **186648**) | `0xda8de4bd…b4cb` |
| **`executeOrder` fill** | `0x4a1f3dd8…c714` |
| `submit(keccak256(fillTx))` | `0x97019d04…67a2` |
| `complete` → escrow to keeper | `0xafabb974…8475` |
| ERC-8004 `giveFeedback` | `0x7c171ad1…24e3` |

Result: **job 186648 = Completed**, escrow released to the keeper, agent reputation recorded.

---

## 5. SDK quickstart

### 5.1 TypeScript (this repo)

```ts
import { createWalletClient, http } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { arcTestnet } from "viem/chains";
import { signLimitOrder, signTwapOrder, ensurePermit2Approval, USDC, EURC, ARC_TESTNET_CHAIN_ID } from "@arc-smart-orders/sdk";

const account = privateKeyToAccount(process.env.PK as `0x${string}`);
const wallet = createWalletClient({ account, chain: arcTestnet, transport: http() });
const EXECUTOR = "0x…"; // your OrderExecutor

// one-time: approve Permit2 for USDC (6-dec ERC-20 interface)
// await ensurePermit2Approval(publicClient, wallet, USDC);

// LIMIT: 1 USDC -> minOut 0.90 EURC
const signature = await signLimitOrder(wallet, {
  tokenIn: USDC, tokenOut: EURC.testnet, amountIn: 1_000_000n, minOut: 900_000n,
  spender: EXECUTOR, nonce: 1n, deadline: BigInt(Math.floor(Date.now()/1000) + 3600), chainId: ARC_TESTNET_CHAIN_ID,
});
// pass { amountIn, minOut, nonce, deadline, signature, ... } to your keeper / order store
```

### 5.2 Python

```python
from eth_account import Account  # pip install eth-account

domain = {"name": "Permit2", "chainId": 5042002, "verifyingContract": "0x000000000022D473030F116dDEE9F6B43aC78BA3"}
types = {
  "PermitWitnessTransferFrom": [
    {"name": "permitted", "type": "TokenPermissions"}, {"name": "spender", "type": "address"},
    {"name": "nonce", "type": "uint256"}, {"name": "deadline", "type": "uint256"},
    {"name": "witness", "type": "OrderIntent"}],
  "TokenPermissions": [{"name": "token", "type": "address"}, {"name": "amount", "type": "uint256"}],
  "OrderIntent": [{"name": "tokenOut", "type": "address"}, {"name": "minOut", "type": "uint256"}],
}
message = {"permitted": {"token": "0x3600000000000000000000000000000000000000", "amount": 1_000_000},
           "spender": "0x…", "nonce": 2, "deadline": 1_790_000_000,
           "witness": {"tokenOut": "0x89B50855Aa3bE2F677cD6303Cec089B5F319D72a", "minOut": 900_000}}

sig = Account.sign_typed_data(PK, full_message={
  "types": types, "primaryType": "PermitWitnessTransferFrom", "domain": domain, "message": message})
print("0x" + sig.signature.hex())
```

> The Python recipe produces the **exact same signature** as the TS SDK (verified). Full runnable
> example: [`examples/python/sign_limit_order.py`](../examples/python/sign_limit_order.py).

---

## 6. Guarantees & limits

- **Non-custodial**: Permit2 pull of the exact signed amount; leftover refunded; no funds at rest.
- **onlyKeeper / onlyOwner**; **whitelisted swap targets** (defense in depth).
- **Agent-native**: identity (ERC-8004), paid execution (ERC-8183), reputation.
- **Input-side platform fee**: `feeBps` (default 30 = 0.30%) + `feeRecipient` (your Safe), capped at
  10%, taken from `tokenIn` **before** the swap → paid in USDC/EURC (no price risk). The signed
  `minOut`/`minRate` is measured on the **net**, so a fee bump can't silently under-fill a user.
- **Open item:** the real swap venue (App Kit Swap router / StableFX `FxEscrow`) is pluggable via
  `setAllowedTarget`; testnet uses a fixed-rate mock router.
- **Not audited. Testnet first.**

## 7. Roadmap

1. Wire the production swap venue on Arc.
2. Off-chain price readiness (oracle / App Kit quote) vs the signed `minOut` / `minRate`.
3. Rich agent tooling: ERC-8004 reputation-aware policies, ERC-8183 bidding hooks.
4. SDK packages published to npm / PyPI.

## License

MIT
