// Execute a transaction from the Arc Safe 2/2 (owners A + C) — used for owner-only calls
// after a Safe-owned deployment (e.g. AgentRegistry.setFactory, OrderExecutor.setFee/setKeeper).
//
// Usage (PowerShell):
//   $env:RPC="https://rpc.mainnet.arc.io"
//   $env:SAFE="0x0FBFAF7069B45Dd9c16AdD8a04Bf556046EA7e93"
//   $env:SAFE_TO="0x<target>"
//   $env:SAFE_DATA="0x<calldata>"      # e.g. cast calldata "setFactory(address)" 0x<factory>
//   node ops/safe-exec.mjs
//
// Env: RPC, SAFE (required), SAFE_TO (required), SAFE_DATA (required), SAFE_VALUE (optional),
//      SAFE_SIGNER_1 / SAFE_SIGNER_2 (secret json paths, default the two A/C files).
import { createPublicClient, createWalletClient, http } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { readFileSync } from "node:fs";

const rpc = process.env.RPC ?? "https://rpc.testnet.arc.io";
const safe = process.env.SAFE;
const to = process.env.SAFE_TO;
const data = process.env.SAFE_DATA;
const value = BigInt(process.env.SAFE_VALUE ?? "0");
const owner1Path = process.env.SAFE_SIGNER_1 ?? "C:/Users/vicen/arc-smart-orders/.secrets/arc-deployer.json";
const owner2Path = process.env.SAFE_SIGNER_2 ?? "C:/Users/vicen/arc-smart-orders/.secrets/arc-validator-c.json";

if (!safe || !to || !data) {
  console.error("Missing SAFE / SAFE_TO / SAFE_DATA");
  process.exit(1);
}

const acctA = privateKeyToAccount(JSON.parse(readFileSync(owner1Path, "utf8")).privateKey);
const acctC = privateKeyToAccount(JSON.parse(readFileSync(owner2Path, "utf8")).privateKey);

const pub = createPublicClient({ transport: http(rpc) });
const wallet = createWalletClient({ account: acctA, transport: http(rpc) });

const nonce = await pub.readContract({
  address: safe,
  abi: [{ type: "function", name: "nonce", stateMutability: "view", inputs: [], outputs: [{ type: "uint256" }] }],
  functionName: "nonce",
});

const chainId = await pub.getChainId();
const domain = { chainId, verifyingContract: safe };
const types = {
  SafeTx: [
    { name: "to", type: "address" }, { name: "value", type: "uint256" }, { name: "data", type: "bytes" },
    { name: "operation", type: "uint8" }, { name: "safeTxGas", type: "uint256" }, { name: "baseGas", type: "uint256" },
    { name: "gasPrice", type: "uint256" }, { name: "gasToken", type: "address" }, { name: "refundReceiver", type: "address" },
    { name: "nonce", type: "uint256" },
  ],
};
const message = {
  to, value, data, operation: 0, safeTxGas: 0n, baseGas: 0n, gasPrice: 0n,
  gasToken: "0x0000000000000000000000000000000000000000", refundReceiver: "0x0000000000000000000000000000000000000000", nonce,
};

const sigs = [
  { addr: acctA.address.toLowerCase(), sig: await acctA.signTypedData({ domain, types, primaryType: "SafeTx", message }) },
  { addr: acctC.address.toLowerCase(), sig: await acctC.signTypedData({ domain, types, primaryType: "SafeTx", message }) },
].sort((x, y) => (x.addr < y.addr ? -1 : 1));
const signatures = "0x" + sigs.map((s) => s.sig.slice(2)).join("");

const hash = await wallet.writeContract({
  account: acctA, chain: null, address: safe,
  abi: [{ type: "function", name: "execTransaction", stateMutability: "nonpayable", inputs: [
    { name: "to", type: "address" }, { name: "value", type: "uint256" }, { name: "data", type: "bytes" },
    { name: "operation", type: "uint8" }, { name: "safeTxGas", type: "uint256" }, { name: "baseGas", type: "uint256" },
    { name: "gasPrice", type: "uint256" }, { name: "gasToken", type: "address" }, { name: "refundReceiver", type: "address" },
    { name: "signatures", type: "bytes" }], outputs: [{ type: "bool" }] }],
  functionName: "execTransaction",
  args: [to, value, data, 0, 0n, 0n, 0n, "0x0000000000000000000000000000000000000000", "0x0000000000000000000000000000000000000000", signatures],
});
console.log("execTransaction:", hash);
const rcpt = await pub.waitForTransactionReceipt({ hash });
console.log("status:", rcpt.status);
