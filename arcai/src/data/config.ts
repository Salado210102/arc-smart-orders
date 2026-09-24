import type { SeedToken } from "./types.ts";

export const NATIVE_USDC_EMITTER = "0xffffFFFfFFffffffffffffffFfFFFfffFFFfFFfE";
export const ERC20_USDC = "0x3600000000000000000000000000000000000000";
export const EURC_MAINNET = "0xbEf5f6d51CB62b58e6A8f77868681825C6fe21c1";
export const CIRBTC_MAINNET = "0x171A4217b86A807A64eB94757Db6849fb4bDbAA0";

export const MAINNET_SEED: SeedToken[] = [
  { address: NATIVE_USDC_EMITTER, emitterKind: "native-system", symbol: "USDC(native)", decimals: 18 },
  { address: ERC20_USDC, emitterKind: "erc20", symbol: "USDC", decimals: 6 },
  { address: EURC_MAINNET, emitterKind: "erc20", symbol: "EURC", decimals: 6 },
  { address: CIRBTC_MAINNET, emitterKind: "erc20", symbol: "cirBTC", decimals: 8 },
];

export type FinalitySource = "none" | "provider" | "contract";

export interface DataEngineConfig {
  chainId: number;
  rpcUrl: string;
  databaseUrl: string;
  operationalConfirmationDepth: number;
  finalitySource: FinalitySource;
  maxReorgDepth: number;
  startBlock: bigint | null;
  pollIntervalMs: number;
  maxRetries: number;
  retryBaseMs: number;
  maxBlocksPerTick: number;
  healthPort: number | null;
  stream: string;
  sourceId: string;
  seed: SeedToken[];
}

const int = (v: string | undefined, fallback: number): number => {
  if (v === undefined || v.trim() === "") return fallback;
  const n = Number(v);
  return Number.isFinite(n) && n >= 0 ? Math.floor(n) : fallback;
};

export function loadConfig(env: Record<string, string | undefined>): DataEngineConfig {
  const chainId = int(env.CHAIN_ID, 5042);
  const startRaw = env.START_BLOCK;
  const startBlock =
    startRaw && /^\d+$/.test(startRaw) ? BigInt(startRaw) : null;
  const fs = env.FINALITY_SOURCE;
  const finalitySource: FinalitySource =
    fs === "provider" || fs === "contract" ? fs : "none";
  return {
    chainId,
    rpcUrl: env.ARC_RPC ?? "https://rpc.mainnet.arc.io",
    databaseUrl: env.DATABASE_URL ?? "",
    operationalConfirmationDepth: int(env.OPERATIONAL_CONFIRMATION_DEPTH, 0),
    finalitySource,
    maxReorgDepth: int(env.REORG_MAX_DEPTH, 32),
    startBlock,
    pollIntervalMs: int(env.POLL_MS, 2000),
    maxRetries: int(env.MAX_RETRIES, 5),
    retryBaseMs: int(env.RETRY_BASE_MS, 500),
    maxBlocksPerTick: int(env.MAX_BLOCKS_PER_TICK, 25),
    healthPort: env.HEALTH_PORT && /^\d+$/.test(env.HEALTH_PORT) ? Number(env.HEALTH_PORT) : null,
    stream: env.STREAM ?? "live",
    sourceId: env.SOURCE_ID ?? "arc-rpc-primary",
    seed: MAINNET_SEED,
  };
}

export function seedFor(config: DataEngineConfig, address: string): SeedToken | null {
  const a = address.toLowerCase();
  return config.seed.find((s) => s.address.toLowerCase() === a) ?? null;
}
