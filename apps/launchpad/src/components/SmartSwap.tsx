import { useCallback, useEffect, useState } from "react";
import { ArrowRight, BadgeCheck, ExternalLink, ShieldCheck, Zap } from "lucide-react";
import { formatUnits, parseUnits } from "viem";
import { EXPLORER, publicClient, walletClient } from "../arc";
import { erc20Abi } from "../contracts";
import {
  EURC_ADDR,
  KEEPER_API,
  PERMIT2,
  USDC_ADDR,
  getOrder,
  signLimitOrder,
  submitOrder,
  type OrderRow,
} from "../lib/orders";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { Input } from "./ui/input";

type Stage = "idle" | "approving" | "signing" | "submitted" | "filled" | "error";

const shortErr = (e: unknown) => (e as { shortMessage?: string }).shortMessage ?? (e as Error).message;

export function SmartSwap({
  account,
  setMsg,
  busy,
  setBusy,
}: {
  account: `0x${string}` | null;
  setMsg: (m: string) => void;
  busy: boolean;
  setBusy: (b: boolean) => void;
}) {
  const [amount, setAmount] = useState("1");
  const [rate, setRate] = useState("0.92");
  const [slip, setSlip] = useState("1");
  const [balance, setBalance] = useState<bigint | null>(null);
  const [allowance, setAllowance] = useState<bigint | null>(null);
  const [stage, setStage] = useState<Stage>("idle");
  const [err, setErr] = useState("");
  const [orderId, setOrderId] = useState<string | null>(null);
  const [order, setOrder] = useState<OrderRow | null>(null);

  const refresh = useCallback(async () => {
    if (!account) {
      setBalance(null);
      setAllowance(null);
      return;
    }
    try {
      const [b, a] = await Promise.all([
        publicClient.readContract({ address: USDC_ADDR, abi: erc20Abi, functionName: "balanceOf", args: [account] }),
        publicClient.readContract({ address: USDC_ADDR, abi: erc20Abi, functionName: "allowance", args: [account, PERMIT2] }),
      ]);
      setBalance(b as bigint);
      setAllowance(a as bigint);
    } catch {
      /* ignore */
    }
  }, [account]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Poll the keeper until the order reaches a terminal state.
  useEffect(() => {
    if (!orderId) return;
    let stop = false;
    let tries = 0;
    const tick = async () => {
      if (stop) return;
      const o = await getOrder(orderId);
      if (o) {
        setOrder(o);
        const s = o.status.toUpperCase();
        if (s === "FILLED") return setStage("filled");
        if (s === "FAILED" || s === "EXPIRED") {
          setErr(o.error ?? s);
          return setStage("error");
        }
      }
      if (++tries > 60) return; // ~3 min
      setTimeout(tick, 3000);
    };
    void tick();
    return () => {
      stop = true;
    };
  }, [orderId]);

  let amountIn = 0n;
  try {
    amountIn = amount ? parseUnits(amount, 6) : 0n;
  } catch {
    amountIn = 0n;
  }
  let minOut = 0n;
  const expected = (Number(amount || "0") * Number(rate || "0")).toFixed(6);
  try {
    const m = Number(expected) * (1 - Number(slip || "0") / 100);
    minOut = m > 0 ? parseUnits(m.toFixed(6), 6) : 0n;
  } catch {
    minOut = 0n;
  }

  const needsApproval = allowance !== null && amountIn > 0n && allowance < amountIn;

  async function approve() {
    if (!account) return;
    setBusy(true);
    setStage("approving");
    setErr("");
    try {
      const w = walletClient() as unknown as { writeContract: (a: unknown) => Promise<`0x${string}`> };
      const hash = await w.writeContract({
        account,
        chain: null,
        address: USDC_ADDR,
        abi: erc20Abi,
        functionName: "approve",
        args: [PERMIT2, 2n ** 256n - 1n],
      });
      await publicClient.waitForTransactionReceipt({ hash });
      setMsg(`Approved Permit2 ✓ ${EXPLORER}/tx/${hash}`);
      await refresh();
      setStage("idle");
    } catch (e) {
      setErr(shortErr(e));
      setStage("error");
    } finally {
      setBusy(false);
    }
  }

  async function sign() {
    if (!account) return;
    if (amountIn <= 0n) return setErr("Enter an amount");
    if (minOut <= 0n) return setErr("Enter a rate");
    setBusy(true);
    setStage("signing");
    setErr("");
    setOrder(null);
    setOrderId(null);
    try {
      const nonce = BigInt(Date.now());
      const deadline = BigInt(Math.floor(Date.now() / 1000) + 3600);
      const w = walletClient();
      const signature = await signLimitOrder(w, account, {
        tokenIn: USDC_ADDR,
        tokenOut: EURC_ADDR,
        amountIn,
        minOut,
        nonce,
        deadline,
      });
      setStage("submitted");
      const res = await submitOrder({
        maker: account,
        tokenIn: USDC_ADDR,
        tokenOut: EURC_ADDR,
        amountIn: amountIn.toString(),
        minOut: minOut.toString(),
        nonce: nonce.toString(),
        deadline: Number(deadline),
        signature,
      });
      if (!res.ok || !res.order) {
        setErr(`${res.error ?? "submit_failed"}${res.detail ? " — " + res.detail : ""}`);
        setStage("error");
        return;
      }
      setOrderId(res.order.id);
      setMsg(`Order signed (0 gas) + submitted ✓ id ${res.order.id}`);
    } catch (e) {
      setErr(shortErr(e));
      setStage("error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="mx-auto w-full max-w-md">
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span className="flex items-center gap-2">
            <Zap className="h-4 w-4 text-violet-400" /> Try Smart Swap
          </span>
          <Badge variant="muted">{stageBadge(stage)}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {/* Pair */}
        <div className="flex items-center gap-2 rounded-xl border border-zinc-800 bg-zinc-950/60 p-3">
          <select
            className="h-9 flex-1 rounded-lg border border-zinc-800 bg-zinc-950/60 px-3 text-sm text-zinc-100 focus-visible:outline-none"
            value="usdc-eurc"
            onChange={() => undefined}
          >
            <option value="usdc-eurc">USDC → EURC</option>
          </select>
          <ArrowRight className="h-4 w-4 shrink-0 text-zinc-500" />
          <span className="rounded-lg border border-zinc-800 bg-zinc-900/60 px-3 py-2 font-mono text-xs text-zinc-400">
            limit
          </span>
        </div>

        {/* Amount */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-4">
          <div className="mb-1 flex items-center justify-between text-[11px] text-zinc-500">
            <span>You sell (USDC)</span>
            {balance !== null && <span>balance {Number(formatUnits(balance, 6)).toFixed(4)}</span>}
          </div>
          <div className="flex items-center gap-2">
            <input
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              className="w-full bg-transparent font-mono text-2xl text-zinc-100 outline-none"
              placeholder="0.0"
            />
            <button
              onClick={() => balance !== null && setAmount(formatUnits(balance, 6))}
              className="rounded-md border border-zinc-800 bg-zinc-900 px-2 py-1 text-[11px] text-zinc-400 hover:text-zinc-200"
            >
              MAX
            </button>
            <span className="font-mono text-sm text-zinc-400">USDC</span>
          </div>
        </div>

        {/* Rate + slippage */}
        <div className="grid grid-cols-2 gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-[11px] text-zinc-500">Target rate (EURC/USDC)</span>
            <Input value={rate} onChange={(e) => setRate(e.target.value)} className="font-mono" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[11px] text-zinc-500">Slippage (%)</span>
            <Input value={slip} onChange={(e) => setSlip(e.target.value)} className="font-mono" />
          </label>
        </div>

        {/* Quotes */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-4 text-xs">
          <div className="flex justify-between text-zinc-500">
            <span>Expected receive</span>
            <span className="font-mono text-zinc-300">{expected} EURC</span>
          </div>
          <div className="mt-1 flex justify-between text-zinc-500">
            <span>Minimum receive (signed)</span>
            <span className="font-mono text-emerald-400">{formatUnits(minOut, 6)} EURC</span>
          </div>
        </div>

        {err && <div className="rounded-lg border border-red-900/50 bg-red-950/30 px-3 py-2 text-xs text-red-300">{err}</div>}

        {/* Actions */}
        {needsApproval ? (
          <Button variant="secondary" disabled={busy} onClick={approve} className="w-full">
            <ShieldCheck className="h-3.5 w-3.5" /> Approve USDC for Permit2 (one-time)
          </Button>
        ) : (
          <Button disabled={!account || busy || amountIn <= 0n} onClick={sign} className="w-full">
            <Zap className="h-3.5 w-3.5" /> Sign Order (0 gas)
          </Button>
        )}

        {/* Lifecycle */}
        {order && (
          <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 px-3 py-2 text-[11px]">
            <div className="flex items-center justify-between">
              <span className="text-zinc-500">order</span>
              <span className="font-mono text-zinc-400">{order.id.slice(0, 12)}…</span>
            </div>
            <div className="mt-1 flex items-center justify-between">
              <span className="text-zinc-500">status</span>
              <span className="font-mono text-zinc-200">{order.status}</span>
            </div>
            {stage === "filled" && order.fill_tx && (
              <a
                className="mt-2 inline-flex items-center gap-1 text-emerald-400 hover:text-emerald-300"
                href={`${EXPLORER}/tx/${order.fill_tx}`}
                target="_blank"
                rel="noreferrer"
              >
                <BadgeCheck className="h-3.5 w-3.5" /> view fill {order.fill_tx.slice(0, 10)}…{" "}
                <ExternalLink className="h-3 w-3" />
              </a>
            )}
          </div>
        )}

        <p className="text-center text-[11px] text-zinc-600">
          Non-custodial · you only sign (no gas) · keeper: {KEEPER_API.replace(/^https?:\/\//, "")}
        </p>
        <p className="text-center text-[10px] text-zinc-700">
          Beta preview — on Arc mainnet the keeper runs dry-run until the FX venue is wired; the order stays PENDING
          then expires (no funds move).
        </p>
      </CardContent>
    </Card>
  );
}

function stageBadge(stage: Stage) {
  switch (stage) {
    case "signing":
      return "signing…";
    case "approving":
      return "approving…";
    case "submitted":
      return "pending fill";
    case "filled":
      return "filled";
    case "error":
      return "error";
    default:
      return "idle";
  }
}
