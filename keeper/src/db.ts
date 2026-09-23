// SQLite persistence for orders (node:sqlite — no external dep).
import { DatabaseSync } from "node:sqlite";
import { mkdirSync } from "node:fs";
import { dirname } from "node:path";

const DB_PATH = process.env.DB_PATH ?? "data/orders.db";
mkdirSync(dirname(DB_PATH), { recursive: true });
export const db = new DatabaseSync(DB_PATH);

db.exec(`
CREATE TABLE IF NOT EXISTS orders (
  id TEXT PRIMARY KEY,
  maker TEXT NOT NULL,
  order_type TEXT NOT NULL DEFAULT 'LIMIT',
  token_in TEXT NOT NULL,
  token_out TEXT NOT NULL,
  amount_in TEXT NOT NULL,
  min_out TEXT NOT NULL,
  nonce TEXT NOT NULL,
  deadline INTEGER NOT NULL,
  signature TEXT NOT NULL,
  job_id TEXT,
  status TEXT NOT NULL DEFAULT 'PENDING',
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  filled_at INTEGER,
  fill_tx TEXT,
  error TEXT
);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status, created_at);
CREATE INDEX IF NOT EXISTS idx_orders_maker ON orders(maker, created_at DESC);
`);

export type OrderRow = {
  id: string;
  maker: string;
  order_type: string;
  token_in: string;
  token_out: string;
  amount_in: string;
  min_out: string;
  nonce: string;
  deadline: number;
  signature: string;
  job_id: string | null;
  status: string;
  created_at: number;
  updated_at: number;
  filled_at: number | null;
  fill_tx: string | null;
  error: string | null;
};

export function insertOrder(o: Omit<OrderRow, "created_at" | "updated_at" | "filled_at" | "fill_tx" | "error" | "status">) {
  const now = Math.floor(Date.now() / 1000);
  db.prepare(
    `INSERT INTO orders(id, maker, order_type, token_in, token_out, amount_in, min_out, nonce, deadline, signature, job_id, status, created_at, updated_at)
     VALUES(?,?,?,?,?,?,?,?,?,?,?, 'PENDING', ?, ?)`,
  ).run(o.id, o.maker, o.order_type, o.token_in, o.token_out, o.amount_in, o.min_out, o.nonce, o.deadline, o.signature, o.job_id, now, now);
  return getOrder(o.id)!;
}

export const getOrder = (id: string) => (db.prepare("SELECT * FROM orders WHERE id = ?").get(id) as OrderRow | undefined) ?? null;

export const listPending = (limit = 25) =>
  db.prepare("SELECT * FROM orders WHERE status = 'PENDING' ORDER BY created_at ASC LIMIT ?").all(limit) as OrderRow[];

export const listByMaker = (maker: string, limit = 100) =>
  db.prepare("SELECT * FROM orders WHERE maker = ? ORDER BY created_at DESC LIMIT ?").all(maker.toLowerCase(), limit) as OrderRow[];

export function markFilled(id: string, fillTx: string) {
  const now = Math.floor(Date.now() / 1000);
  db.prepare("UPDATE orders SET status='FILLED', fill_tx=?, filled_at=?, updated_at=? WHERE id = ?").run(fillTx, now, now, id);
}

export function markFailed(id: string, error: string) {
  db.prepare("UPDATE orders SET status='FAILED', error=?, updated_at=? WHERE id = ?").run(error.slice(0, 300), Math.floor(Date.now() / 1000), id);
}

export function expireOld(now: number) {
  db.prepare("UPDATE orders SET status='EXPIRED', updated_at=? WHERE status='PENDING' AND deadline <= ?").run(now, now);
}
