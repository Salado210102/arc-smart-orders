import type { Address } from "viem";

//  Arc MAINNET (deployed 2026-09-23 — see DEPLOYMENTS.md)
export const ADDR = {
  factory: "0x4A80a4748A1d2AB37300780FcBC2FD28d2Ed393B",
  registry: "0x8aE509565397C62a585c74aA44f7E3bFEab3Bb01",
  module: "0x1B8CA122DFd1100C0873A517b4875611Ed9De792",
  locker: "0x9cb011A46A1127202Bc92F48f70Bf7010F1f9B6C",
  vault: "0x5E9dCd592B37fda481Fc203756DA4D990cE438bA", // demo agent staking vault (ERC-4626-ish)
  splitter: "0xE74A66928aa049C78D271d02427b10c37eC1C51b", // demo agent RevenueSplitter (70/30)
  vaultAsset: "0xD81d4A4e6e91977cEf71b81259BF0a627e3E60De", // demo agent token (staked asset)
  usdc: "0x3600000000000000000000000000000000000000",
  safe: "0x0FBFAF7069B45Dd9c16AdD8a04Bf556046EA7e93", // Safe 2/2 — owner / treasury / feeRecipient
} as const satisfies Record<string, Address>;

export const vaultAbi = [
  { type: "function", name: "deposit", stateMutability: "nonpayable", inputs: [{ name: "assets", type: "uint256" }, { name: "receiver", type: "address" }], outputs: [{ name: "shares", type: "uint256" }] },
  { type: "function", name: "withdraw", stateMutability: "nonpayable", inputs: [{ name: "assets", type: "uint256" }, { name: "receiver", type: "address" }, { name: "owner", type: "address" }], outputs: [{ name: "shares", type: "uint256" }] },
  { type: "function", name: "claim", stateMutability: "nonpayable", inputs: [], outputs: [{ name: "p", type: "uint256" }] },
  { type: "function", name: "pendingRewards", stateMutability: "view", inputs: [{ name: "user", type: "address" }], outputs: [{ type: "uint256" }] },
  { type: "function", name: "pool", stateMutability: "view", inputs: [], outputs: [{ type: "uint256" }] },
  { type: "function", name: "balanceOf", stateMutability: "view", inputs: [{ name: "a", type: "address" }], outputs: [{ type: "uint256" }] },
  { type: "function", name: "totalAssets", stateMutability: "view", inputs: [], outputs: [{ type: "uint256" }] },
  { type: "function", name: "totalSupply", stateMutability: "view", inputs: [], outputs: [{ type: "uint256" }] },
  { type: "function", name: "asset", stateMutability: "view", inputs: [], outputs: [{ type: "address" }] },
] as const;

export const factoryAbi = [
  {
    type: "function",
    name: "launch",
    stateMutability: "nonpayable",
    inputs: [
      { name: "name_", type: "string" },
      { name: "symbol_", type: "string" },
      { name: "supply_", type: "uint256" },
      { name: "x0_", type: "uint256" },
      { name: "graduationUsdc_", type: "uint256" },
      { name: "maxWallet_", type: "uint256" },
      { name: "maxTx_", type: "uint256" },
      { name: "metadataURI_", type: "string" },
    ],
    outputs: [
      { name: "tokenAddr", type: "address" },
      { name: "curveAddr", type: "address" },
    ],
  },
] as const;

export const registryAbi = [
  { type: "function", name: "count", stateMutability: "view", inputs: [], outputs: [{ type: "uint256" }] },
  {
    type: "function",
    name: "all",
    stateMutability: "view",
    inputs: [],
    outputs: [
      {
        type: "tuple[]",
        components: [
          { name: "agentId", type: "uint256" },
          { name: "token", type: "address" },
          { name: "curve", type: "address" },
          { name: "creator", type: "address" },
          { name: "metadataURI", type: "string" },
          { name: "createdAt", type: "uint64" },
        ],
      },
    ],
  },
] as const;

export const curveAbi = [
  { type: "function", name: "buy", stateMutability: "nonpayable", inputs: [{ name: "usdcIn", type: "uint256" }, { name: "minTokensOut", type: "uint256" }], outputs: [{ type: "uint256" }] },
  { type: "function", name: "sell", stateMutability: "nonpayable", inputs: [{ name: "tokensIn", type: "uint256" }, { name: "minUsdcOut", type: "uint256" }], outputs: [{ type: "uint256" }] },
  { type: "function", name: "buyQuote", stateMutability: "view", inputs: [{ name: "usdcIn", type: "uint256" }], outputs: [{ name: "tokensOut", type: "uint256" }, { name: "fee", type: "uint256" }] },
  { type: "function", name: "sellQuote", stateMutability: "view", inputs: [{ name: "tokensIn", type: "uint256" }], outputs: [{ name: "usdcOut", type: "uint256" }, { name: "fee", type: "uint256" }, { name: "gross", type: "uint256" }] },
  { type: "function", name: "price", stateMutability: "view", inputs: [], outputs: [{ type: "uint256" }] },
  { type: "function", name: "graduated", stateMutability: "view", inputs: [], outputs: [{ type: "bool" }] },
  { type: "function", name: "raisedUsdc", stateMutability: "view", inputs: [], outputs: [{ type: "uint256" }] },
  { type: "function", name: "graduationUsdc", stateMutability: "view", inputs: [], outputs: [{ type: "uint256" }] },
] as const;

export const erc20Abi = [
  { type: "function", name: "approve", stateMutability: "nonpayable", inputs: [{ name: "s", type: "address" }, { name: "a", type: "uint256" }], outputs: [{ type: "bool" }] },
  { type: "function", name: "allowance", stateMutability: "view", inputs: [{ name: "o", type: "address" }, { name: "s", type: "address" }], outputs: [{ type: "uint256" }] },
  { type: "function", name: "balanceOf", stateMutability: "view", inputs: [{ name: "a", type: "address" }], outputs: [{ type: "uint256" }] },
] as const;
