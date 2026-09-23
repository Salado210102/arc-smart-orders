// ERC-8004 (agent identity/reputation) + ERC-8183 (Agentic Commerce jobs) integration.
// We do NOT deploy these — Arc already has them. This module calls the deployed contracts.
//
// Flow (Agentic Smart Orders):
//   1. registerAgent()               -> ERC-8004 IdentityRegistry.register(metadataURI)
//   2. createJob()                   -> ERC-8183 createJob(provider=keeper, evaluator=client, ...)
//   3. setBudget()                   -> provider proposes the execution fee (USDC)
//   4. fundJob()                     -> client approves + funds escrow
//   5. submitDeliverable()           -> keeper submits keccak256(fillTxHash) after executing
//   6. completeJob()                 -> evaluator releases escrow to the keeper
//   7. giveReputation()              -> ERC-8004 ReputationRegistry (a validator, not the owner)
import { type Account, type Address, type Chain, type Hex, type PublicClient, type Transport, type WalletClient, decodeEventLog } from "viem";

// A wallet client with concrete generics so `writeContract` doesn't require an explicit chain.
type Wallet = WalletClient<Transport, Chain, Account>;

// Arc testnet
export const IDENTITY_REGISTRY = "0x8004A818BFB912233c491871b3d84c89A494BD9e" as const;
export const REPUTATION_REGISTRY = "0x8004B663056A597Dffe9eCcC1965A193B7388713" as const;
export const VALIDATION_REGISTRY = "0x8004Cb1BF31DAf7788923b405b754f57acEB4272" as const;
export const AGENTIC_COMMERCE = "0x0747EEf0706327138c69792bF28Cd525089e4583" as const;
export const USDC = "0x3600000000000000000000000000000000000000" as const;

export const identityAbi = [
  { type: "function", name: "register", stateMutability: "nonpayable", inputs: [{ name: "metadataURI", type: "string" }], outputs: [] },
  { type: "function", name: "ownerOf", stateMutability: "view", inputs: [{ name: "tokenId", type: "uint256" }], outputs: [{ type: "address" }] },
  { type: "function", name: "tokenURI", stateMutability: "view", inputs: [{ name: "tokenId", type: "uint256" }], outputs: [{ type: "string" }] },
  { type: "event", name: "Transfer", inputs: [{ indexed: true, name: "from", type: "address" }, { indexed: true, name: "to", type: "address" }, { indexed: true, name: "tokenId", type: "uint256" }] },
] as const;

export const reputationAbi = [
  {
    type: "function",
    name: "giveFeedback",
    stateMutability: "nonpayable",
    inputs: [
      { name: "agentId", type: "uint256" },
      { name: "score", type: "int128" },
      { name: "feedbackType", type: "uint8" },
      { name: "tag", type: "string" },
      { name: "evidenceURI", type: "string" },
      { name: "context", type: "string" },
      { name: "extra", type: "string" },
      { name: "feedbackHash", type: "bytes32" },
    ],
    outputs: [],
  },
] as const;

export const acpAbi = [
  { type: "function", name: "createJob", stateMutability: "nonpayable", inputs: [{ name: "provider", type: "address" }, { name: "evaluator", type: "address" }, { name: "expiredAt", type: "uint256" }, { name: "description", type: "string" }, { name: "hook", type: "address" }], outputs: [{ name: "jobId", type: "uint256" }] },
  { type: "function", name: "setBudget", stateMutability: "nonpayable", inputs: [{ name: "jobId", type: "uint256" }, { name: "amount", type: "uint256" }, { name: "optParams", type: "bytes" }], outputs: [] },
  { type: "function", name: "fund", stateMutability: "nonpayable", inputs: [{ name: "jobId", type: "uint256" }, { name: "optParams", type: "bytes" }], outputs: [] },
  { type: "function", name: "submit", stateMutability: "nonpayable", inputs: [{ name: "jobId", type: "uint256" }, { name: "deliverable", type: "bytes32" }, { name: "optParams", type: "bytes" }], outputs: [] },
  { type: "function", name: "complete", stateMutability: "nonpayable", inputs: [{ name: "jobId", type: "uint256" }, { name: "reason", type: "bytes32" }, { name: "optParams", type: "bytes" }], outputs: [] },
  { type: "function", name: "getJob", stateMutability: "view", inputs: [{ name: "jobId", type: "uint256" }], outputs: [{ type: "tuple", components: [{ name: "id", type: "uint256" }, { name: "client", type: "address" }, { name: "provider", type: "address" }, { name: "evaluator", type: "address" }, { name: "description", type: "string" }, { name: "budget", type: "uint256" }, { name: "expiredAt", type: "uint256" }, { name: "status", type: "uint8" }, { name: "hook", type: "address" }] }] },
  { type: "event", name: "JobCreated", inputs: [{ indexed: true, name: "jobId", type: "uint256" }, { indexed: true, name: "client", type: "address" }, { indexed: true, name: "provider", type: "address" }, { indexed: false, name: "evaluator", type: "address" }, { indexed: false, name: "expiredAt", type: "uint256" }, { indexed: false, name: "hook", type: "address" }] },
] as const;

export const erc20Abi = [
  { type: "function", name: "approve", stateMutability: "nonpayable", inputs: [{ name: "spender", type: "address" }, { name: "amount", type: "uint256" }], outputs: [{ type: "bool" }] },
] as const;

export const STATUS_NAMES = ["Open", "Funded", "Submitted", "Completed", "Rejected", "Expired"] as const;

/** Register an agent identity (ERC-8004) and return the agentId (parsed from the Transfer event). */
export async function registerAgent(pc: PublicClient, wc: Wallet, metadataURI: string): Promise<bigint> {
  if (!wc.account) throw new Error("wallet has no account");
  const hash = await wc.writeContract({ account: wc.account, address: IDENTITY_REGISTRY, abi: identityAbi, functionName: "register", args: [metadataURI] });
  const rc = await pc.waitForTransactionReceipt({ hash });
  for (const log of rc.logs) {
    try {
      const ev = decodeEventLog({ abi: identityAbi, data: log.data, topics: log.topics });
      if (ev.eventName === "Transfer") return (ev.args as { tokenId: bigint }).tokenId;
    } catch {
      /* not our event */
    }
  }
  throw new Error("agentId not found in receipt");
}

/** Record reputation for an agent (ERC-8004). Must NOT be called by the agent owner. */
export async function giveReputation(pc: PublicClient, validator: Wallet, agentId: bigint, score: number, tag: string, feedbackHash: Hex) {
  if (!validator.account) throw new Error("wallet has no account");
  const hash = await validator.writeContract({
    account: validator.account,
    address: REPUTATION_REGISTRY,
    abi: reputationAbi,
    functionName: "giveFeedback",
    args: [agentId, BigInt(score), 0, tag, "", "", "", feedbackHash],
  });
  return pc.waitForTransactionReceipt({ hash });
}

/** Create an ERC-8183 job (provider = keeper, evaluator = client/agent). Returns the jobId. */
export async function createJob(
  pc: PublicClient,
  client: Wallet,
  args: { provider: Address; evaluator: Address; expiredAt: bigint; description: string },
): Promise<bigint> {
  if (!client.account) throw new Error("wallet has no account");
  const hash = await client.writeContract({
    account: client.account,
    address: AGENTIC_COMMERCE,
    abi: acpAbi,
    functionName: "createJob",
    args: [args.provider, args.evaluator, args.expiredAt, args.description, "0x0000000000000000000000000000000000000000"],
  });
  const rc = await pc.waitForTransactionReceipt({ hash });
  for (const log of rc.logs) {
    try {
      const ev = decodeEventLog({ abi: acpAbi, data: log.data, topics: log.topics });
      if (ev.eventName === "JobCreated") return (ev.args as { jobId: bigint }).jobId;
    } catch {
      /* not our event */
    }
  }
  throw new Error("jobId not found in receipt");
}

export async function setBudget(pc: PublicClient, provider: Wallet, jobId: bigint, amount: bigint) {
  if (!provider.account) throw new Error("wallet has no account");
  const hash = await provider.writeContract({ account: provider.account, address: AGENTIC_COMMERCE, abi: acpAbi, functionName: "setBudget", args: [jobId, amount, "0x"] });
  return pc.waitForTransactionReceipt({ hash });
}

/** Client approves USDC and funds the job escrow. */
export async function fundJob(pc: PublicClient, client: Wallet, jobId: bigint, amount: bigint) {
  if (!client.account) throw new Error("wallet has no account");
  const a = await client.writeContract({ account: client.account, address: USDC, abi: erc20Abi, functionName: "approve", args: [AGENTIC_COMMERCE, amount] });
  await pc.waitForTransactionReceipt({ hash: a });
  const f = await client.writeContract({ account: client.account, address: AGENTIC_COMMERCE, abi: acpAbi, functionName: "fund", args: [jobId, "0x"] });
  return pc.waitForTransactionReceipt({ hash: f });
}

/** Provider submits the deliverable (e.g. keccak256 of the fill tx hash). */
export async function submitDeliverable(pc: PublicClient, provider: Wallet, jobId: bigint, deliverable: Hex) {
  if (!provider.account) throw new Error("wallet has no account");
  const hash = await provider.writeContract({ account: provider.account, address: AGENTIC_COMMERCE, abi: acpAbi, functionName: "submit", args: [jobId, deliverable, "0x"] });
  return pc.waitForTransactionReceipt({ hash });
}

/** Evaluator completes the job -> escrow released to the provider. */
export async function completeJob(pc: PublicClient, evaluator: Wallet, jobId: bigint, reason: Hex) {
  if (!evaluator.account) throw new Error("wallet has no account");
  const hash = await evaluator.writeContract({ account: evaluator.account, address: AGENTIC_COMMERCE, abi: acpAbi, functionName: "complete", args: [jobId, reason, "0x"] });
  return pc.waitForTransactionReceipt({ hash });
}

export async function getJob(pc: PublicClient, jobId: bigint) {
  return pc.readContract({ address: AGENTIC_COMMERCE, abi: acpAbi, functionName: "getJob", args: [jobId] });
}
