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
const EXECUTOR = (process.env.EXECUTOR ?? "0x5E9dCd592B37fda481Fc203756DA4D990cE438bA") as `0x${string}`;
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
const feeAbi = [
  { type: "function", name: "feeBps", stateMutability: "view", inputs: [], outputs: [{ type: "uint256" }] },
  { type: "function", name: "feeRecipient", stateMutability: "view", inputs: [], outputs: [{ type: "address" }] },
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

  // 0) Ensure B and C are funded (only top up if low, to save A's USDC)
  console.log("── Step 0: Ensure B and C are funded ──");
  const balAbi = [{ type: "function", name: "balanceOf", stateMutability: "view", inputs: [{ name: "a", type: "address" }], outputs: [{ type: "uint256" }] }] as const;
  for (const [label, to] of [["B", B.address], ["C", C.address]] as const) {
    const bal = (await pc.readContract({ address: USDC, abi: balAbi, functionName: "balanceOf", args: [to] })) as bigint;
    if (bal < parseUnits("1", 6)) {
      const h = await wcA.writeContract({ account: A, address: USDC, abi: erc20Abi, functionName: "transfer", args: [to, parseUnits("2", 6)], maxFeePerGas: await gas() });
      await pc.waitForTransactionReceipt({ hash: h });
      log(`fund ${label}`, h);
    } else {
      console.log(`  ${label} already funded (${Number(bal) / 1e6} USDC)`);
    }
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
  const nonce = BigInt(Date.now()); // unordered Permit2 nonce — unique per run
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

  // 7) B executes the fill via OrderExecutor (keeper) — WITH platform fee (input-side)
  console.log("── Step 7: B fills the order (OrderExecutor.executeOrder + fee) ──");
  const feeBps = (await pc.readContract({ address: EXECUTOR, abi: feeAbi, functionName: "feeBps" })) as bigint;
  const feeRecipient = (await pc.readContract({ address: EXECUTOR, abi: feeAbi, functionName: "feeRecipient" })) as `0x${string}`;
  const fee = (amountIn * feeBps) / 10_000n;
  const swapAmount = amountIn - fee;
  console.log(`  feeBps=${feeBps} (${Number(feeBps) / 100}%) · fee=${fee} wei (${Number(fee) / 1e6} USDC) · swapAmount=${swapAmount} (${Number(swapAmount) / 1e6} USDC)`);
  console.log(`  treasury (feeRecipient) = ${feeRecipient}`);
  let fillHash: `0x${string}`;
  {
    // The keeper builds the swap for the NET amount (gross - fee).
    const swapData = encodeFunctionData({ abi: routerAbi, functionName: "swap", args: [USDC, swapAmount, EURC.testnet as `0x${string}`, A.address, minOut] });
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
    const balAbi = [{ type: "function", name: "balanceOf", stateMutability: "view", inputs: [{ name: "a", type: "address" }], outputs: [{ type: "uint256" }] }] as const;
    const tBal = (await pc.readContract({ address: USDC, abi: balAbi, functionName: "balanceOf", args: [feeRecipient] })) as bigint;
    console.log(`  ➜ treasury USDC = ${tBal} (${Number(tBal) / 1e6} USDC) · fee received = ${Number(tBal) / 1e6} USDC`);
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
