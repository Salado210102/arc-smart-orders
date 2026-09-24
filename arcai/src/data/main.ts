import { createServer } from "node:http";
import { loadConfig } from "./config.ts";
import { getHealth } from "./health.ts";
import { Ingestor } from "./ingest.ts";
import { consoleLogger, Metrics } from "./metrics.ts";
import { PgStore } from "./pg-store.ts";
import { HttpRpcSource } from "./source.ts";

const config = loadConfig(process.env);
const logger = consoleLogger();

if (config.databaseUrl.trim() === "") {
  logger.error("missing_configuration", { required: "DATABASE_URL" });
  process.exit(1);
}

const store = new PgStore(config.databaseUrl);
const source = new HttpRpcSource({
  rpcUrl: config.rpcUrl,
  chainId: config.chainId,
  seedAddresses: config.seed.map((s) => s.address),
});
const metrics = new Metrics();
const ingestor = new Ingestor({ store, source, config, logger, metrics });

await ingestor.init();
logger.info("data_engine_started", {
  chainId: config.chainId,
  rpc: config.rpcUrl,
  stream: config.stream,
  operationalConfirmationDepth: config.operationalConfirmationDepth,
});

if (config.healthPort !== null) {
  const server = createServer(async (req, res) => {
    if (req.url === "/health" || req.url === "/healthz") {
      const report = await getHealth(store, config, metrics, ingestor.head);
      res.writeHead(200, { "content-type": "application/json", connection: "close" });
      res.end(JSON.stringify(report));
      return;
    }
    res.writeHead(404, { connection: "close" });
    res.end();
  });
  server.listen(config.healthPort, "127.0.0.1", () => {
    logger.info("health_server_listening", { port: config.healthPort });
  });
}

const signal = { aborted: false };
process.on("SIGINT", () => {
  signal.aborted = true;
});
process.on("SIGTERM", () => {
  signal.aborted = true;
});

await ingestor.run(signal);
await store.close();
