// Agentic E2E demo on Arc testnet — 3 separate roles:
//   A = client/agent (signs the limit order, creates the ERC-8183 job, funds escrow)
//   B = keeper/executor agent (registered on ERC-8004, fills the order, submits deliverable)
//   C = validator/evaluator (releases escrow, records ERC-8004 reputation)
//
// Run: npx tsx src/agentic-demo.ts
import { readFileSync } from "node:fs";
import { createPublicClient, createWalletClient, http, defineChain, encodeFunctionData, keccak256, toHex, parseUnits } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { signLimitOrder, USDC, EURC, ARC_TESTNET_CHAIN_ID } from "../../sdk/src/index.ts";
import {
  registerAgent, createJob, setBudget, fundJob, submitDeliverable, completeJob, giveReputation, getJob, STATUS_NAMES,
} from "./agentic.ts";

const RPC = "https://rpc.testnet.arc.io";
const EXECUTOR = "0x9cb011A46A1127202Bc92F48f70Bf7010F1f9B6C" as const;
const ROUTER = "0xcDeA0D5BcD78dB86D7A5f4E976976400a5b4dffc" as const;
const EXPLORER = "https://explorer.testnet.arc.io/tx/";

const chain = defineChain({
  id: ARC_TESTNET_CHAIN_ID,
  name: "Arc Testnet",
  nativeCurrency: { name: "USDC", symbol: "USDC", decimals: 18 },
  rpcUrls: { default: { http: [RPC] } },
});
const pc = createPublicClient({ chain, transport: http(RPC) });

const load = (p: string) => privateKeyToAccount(JSON.parse(readFileSync(p, "utf8")).privateKey as `0x${string}`);
const A = load("../.secrets/arc-deployer.json"); // client/agent
const B = load("../.secrets/arc-keeper-b.json"); // keeper/executor
const C = load("../.secrets/arc-validator-c.json"); // validator/evaluator
const wcA = createWalletClient({ account: A, chain, transport: http(RPC) });
const wcB = createWalletClient({ account: B, chain, transport: http(RPC) });
const wcC = createWalletClient({ account: C, chain, transport: http(RPC) });

const gas = async () => {
  const floor = 20n * 10n ** 9n;
  const s = await pc.getGasPrice().catch(() => floor);
  return s > floor ? s : floor;
};

const erc20Abi = [
  { type: "function", name: "transfer", stateMutability: "nonpayable", inputs: [{ name: "to", type: "address" }, { name: "amount", type: "uint256" }], outputs: [{ type: "bool" }] },
] as const;
const executorAbi = [
  { type: "function", name: "setKeeper", stateMutability: "nonpayable", inputs: [{ name: "k", type: "address" }], outputs: [] },
  {
    type: "function", name: "executeOrder", stateMutability: "nonpayable",
    inputs: [
      { name: "permit", type: "tuple", components: [{ name: "permitted", type: "tuple", components: [{ name: "token", type: "address" }, { name: "amount", type: "uint256" }] }, { name: "nonce", type: "uint256" }, { name: "deadline", type: "uint256" }] },
      { name: "orderOwner", type: "address" }, { name: "permitSignature", type: "bytes" },
      { name: "swapTarget", type: "address" }, { name: "swapData", type: "bytes" },
      { name: "tokenOut", type: "address" }, { name: "minOut", type: "uint256" },
    ], outputs: [],
  },
] as const;
const routerAbi = [
  { type: "function", name: "swap", stateMutability: "nonpayable", inputs: [{ name: "tokenIn", type: "address" }, { name: "amountIn", type: "uint256" }, { name: "tokenOut", type: "address" }, { name: "recipient", type: "address" }, { name: "minOut", type: "uint256" }], outputs: [{ type: "uint256" }] },
] as const;

const txmap: Record<string, string> = {};
const log = (step: string, hash: string) => {
  txmap[step] = hash;
  console.log(`  ${step}: ${EXPLORER}${hash}`);
};

async function main() {
  console.log(`A client : ${A.address}`);
  console.log(`B keeper : ${B.address}`);
  console.log(`C validator: ${C.address}\n`);

  // 0) Fund B and C from A (gas + roles)
  console.log("── Step 0: Fund B and C from A (3 USDC each) ──");
  for (const [label, to] of [["B", B.address], ["C", C.address]] as const) {
    const h = await wcA.writeContract({ account: A, address: USDC, abi: erc20Abi, functionName: "transfer", args: [to, parseUnits("3", 6)], maxFeePerGas: await gas() });
    await pc.waitForTransactionReceipt({ hash: h });
    log(`fund ${label}`, h);
  }

  // 1) A (owner) makes B the OrderExecutor keeper
  console.log("── Step 1: A sets keeper = B on OrderExecutor (owner) ──");
  {
    const h = await wcA.writeContract({ account: A, address: EXECUTOR, abi: executorAbi, functionName: "setKeeper", args: [B.address], maxFeePerGas: await gas() });
    await pc.waitForTransactionReceipt({ hash: h });
    log("setKeeper(B)", h);
  }

  // 2) B registers its agent identity (ERC-8004)
  console.log("── Step 2: B registers agent identity (ERC-8004) ──");
  const metadataURI = "ipfs://bafkreibdi6623n3xpf7ymk62ckb4bo75o3qemwkpfvp5i25j66itxvsoei";
  const agentId = await registerAgent(pc, wcB, metadataURI);
  console.log(`  agentId (B) = ${agentId}`);

  // 3) A signs the LIMIT order intent
  console.log("── Step 3: A signs LIMIT order (1 USDC -> minOut 0.90 EURC) ──");
  const now = Math.floor(Date.now() / 1000);
  const amountIn = parseUnits("1", 6);
  const minOut = parseUnits("0.90", 6);
  const deadline = BigInt(now + 3600);
  const nonce = 2n;
  const permitSignature = await signLimitOrder(wcA, {
    tokenIn: USDC, tokenOut: EURC.testnet as `0x${string}`, amountIn, minOut, spender: EXECUTOR, nonce, deadline, chainId: ARC_TESTNET_CHAIN_ID,
  });
  console.log("  intent signed ✓");

  // 4) A creates the ERC-8183 job (provider=B, evaluator=C)
  console.log("── Step 4: A creates ERC-8183 job ──");
  const jobId = await createJob(pc, wcA, { provider: B.address, evaluator: C.address, expiredAt: BigInt(now + 3600), description: "Arc Smart Order: fill LIMIT 1 USDC -> EURC" });
  console.log(`  jobId = ${jobId}`);

  // 5) B proposes the execution fee
  console.log("── Step 5: B sets budget (0.10 USDC) ──");
  {
    const rc = await setBudget(pc, wcB, jobId, parseUnits("0.10", 6));
    log("setBudget", rc.transactionHash);
  }

  // 6) A approves + funds escrow
  console.log("── Step 6: A funds escrow (0.10 USDC) ──");
  {
    const rc = await fundJob(pc, wcA, jobId, parseUnits("0.10", 6));
    log("fund escrow", rc.transactionHash);
  }

  // 7) B executes the fill via OrderExecutor (keeper)
  console.log("── Step 7: B fills the order (OrderExecutor.executeOrder) ──");
  let fillHash: `0x${string}`;
  {
    const swapData = encodeFunctionData({ abi: routerAbi, functionName: "swap", args: [USDC, amountIn, EURC.testnet as `0x${string}`, A.address, minOut] });
    const data = encodeFunctionData({
      abi: executorAbi, functionName: "executeOrder",
      args: [
        { permitted: { token: USDC, amount: amountIn }, nonce, deadline },
        A.address, permitSignature, ROUTER, swapData, EURC.testnet as `0x${string}`, minOut,
      ],
    });
    fillHash = await wcB.sendTransaction({ to: EXECUTOR, data, maxFeePerGas: await gas() });
    const rc = await pc.waitForTransactionReceipt({ hash: fillHash });
    if (rc.status !== "success") throw new Error("fill reverted");
    log("fill", fillHash);
  }

  // 8) B submits the deliverable = keccak256(fillTxHash)
  console.log("── Step 8: B submits deliverable = keccak256(fillTxHash) ──");
  const deliverable = keccak256(toHex(fillHash));
  {
    const rc = await submitDeliverable(pc, wcB, jobId, deliverable);
    log("submit deliverable", rc.transactionHash);
  }

  // 9) C completes the job (evaluator) -> escrow to B
  console.log("── Step 9: C completes the job (escrow -> B) ──");
  {
    const rc = await completeJob(pc, wcC, jobId, keccak256(toHex("deliverable-approved")));
    log("complete", rc.transactionHash);
  }

  // 10) C records reputation for agent B (ERC-8004)
  console.log("── Step 10: C gives reputation feedback (ERC-8004) ──");
  {
    const rc = await giveReputation(pc, wcC, agentId, 95, "successful_fill", keccak256(toHex("arc-smart-orders-fill")));
    log("reputation", rc.transactionHash);
  }

  // Final state
  const job = await getJob(pc, jobId);
  console.log(`\nJOB ${jobId} status = ${STATUS_NAMES[Number((job as { status: number }).status)]}`);
  console.log(`agentId (B) = ${agentId}`);
  console.log("\n=== TX TREE ===");
  for (const [k, v] of Object.entries(txmap)) console.log(`${k.padEnd(18)} ${EXPLORER}${v}`);
}

main().catch((e) => {
  console.error("ERROR:", e.shortMessage ?? e.message ?? e);
  process.exit(1);
});
