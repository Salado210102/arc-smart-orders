import type { Address } from "viem";

//  Arc testnet (P2 deployment — see DEPLOYMENTS.md)
export const ADDR = {
  factory: "0x3d66d4abE251Aa2bC92B7842002Eb822469369A9",
  registry: "0xAD5Bf8f7BA4A0e51092F4419CeF7D40308289e16",
  module: "0xBDF9BA264157EB634Dc65A61DfA512Fe5E3E1166",
  locker: "0xDf1592E1e6a6ABA13eF7c8821004a4011Bd90Aba",
  vault: "0x5D5e48336589f3d9fdC4EABd986a526D7BF1FE6d",
  splitter: "0xad5ad6b09d52FA8BD5Acd7d0954da783e7a7b2dc",
  vaultAsset: "0x23e904f3cba0a5a8b00612788650066e8cd49f99", // dry-run demo AgentToken
  usdc: "0x3600000000000000000000000000000000000000",
} as const satisfies Record<string, Address>;

export const vaultAbi = [
  { type: "function", name: "deposit", stateMutability: "nonpayable", inputs: [{ name: "assets", type: "uint256" }, { name: "receiver", type: "address" }], outputs: [{ name: "shares", type: "uint256" }] },
  { type: "function", name: "withdraw", stateMutability: "nonpayable", inputs: [{ name: "assets", type: "uint256" }, { name: "receiver", type: "address" }, { name: "owner", type: "address" }], outputs: [{ name: "shares", type: "uint256" }] },
  { type: "function", name: "claim", stateMutability: "nonpayable", inputs: [], outputs: [{ name: "p", type: "uint256" }] },
  { type: "function", name: "pendingRewards", stateMutability: "view", inputs: [{ name: "user", type: "address" }], outputs: [{ type: "uint256" }] },
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
