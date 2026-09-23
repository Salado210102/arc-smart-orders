// Loads .env if present (Node 21.7+ / 22+, no dependency). Imported FIRST so other modules see env.
import { existsSync } from "node:fs";
if (existsSync(".env")) {
  try {
    (process as unknown as { loadEnvFile: (p: string) => void }).loadEnvFile(".env");
  } catch {
    /* ignore */
  }
}
export {};
