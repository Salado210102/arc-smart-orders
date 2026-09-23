// Arc Smart Orders — persistent keeper (API + worker).
//   API:    POST /v1/orders (signature/balance/permit2/expiry validated) -> SQLite
//   Worker: polls PENDING -> rate check -> OrderExecutor.executeOrder (input-side fee) -> FILLED
//           + submits the ERC-8183 deliverable when the order is linked to a job.
import "./env.ts";
import { startServer } from "./server.ts";
import { startWorker } from "./worker.ts";

await startServer();
startWorker();
