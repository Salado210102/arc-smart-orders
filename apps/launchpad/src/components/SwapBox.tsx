import { useEffect, useState } from "react";
import { ArrowDownUp } from "lucide-react";
import { formatUnits, parseUnits } from "viem";
import { EXPLORER, publicClient, walletClient } from "../arc";
import { ADDR, curveAbi, erc20Abi } from "../contracts";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { short, tokenTicker } from "../lib/utils";
import type { Agent } from "./AgentCard";

export function SwapBox({
  agents,
  selected,
  account,
  onSelect,
  setMsg,
  busy,
  setBusy,
}: {
  agents: Agent[];
  selected: Agent | null;
  account: `0x${string}` | null;
  onSelect: (a: Agent | null) => void;
  setMsg: (m: string) => void;
  busy: boolean;
  setBusy: (b: boolean) => void;
}) {
  const [dir, setDir] = useState<"buy" | "sell">("buy");
  const [amount, setAmount] = useState("10");
  const [quote, setQuote] = useState("");
  const [price, setPrice] = useState("");

  useEffect(() => {
    (async () => {
      if (!selected || !amount) {
        setQuote("");
        return;
      }
      try {
        if (dir === "buy") {
          const [out, fee] = (await publicClient.readContract({
            address: selected.curve,
            abi: curveAbi,
            functionName: "buyQuote",
            args: [parseUnits(amount, 6)],
          })) as readonly [bigint, bigint];
          setQuote(`≈ ${Number(formatUnits(out, 18)).toLocaleString()} tokens · fee ${formatUnits(fee, 6)} USDC`);
        } else {
          const [out, fee] = (await publicClient.readContract({
            address: selected.curve,
            abi: curveAbi,
            functionName: "sellQuote",
            args: [parseUnits(amount, 18)],
          })) as readonly [bigint, bigint, bigint];
          setQuote(`≈ ${formatUnits(out, 6)} USDC · fee ${formatUnits(fee, 6)} USDC`);
        }
        const p = (await publicClient.readContract({
          address: selected.curve,
          abi: curveAbi,
          functionName: "price",
        })) as bigint;
        setPrice(formatUnits(p, 6));
      } catch {
        setQuote("");
      }
    })();
  }, [selected, amount, dir]);

  async function run() {
    if (!account || !selected) return;
    setBusy(true);
    setMsg(dir === "buy" ? "Approving + buying…" : "Approving + selling…");
    try {
      const w = walletClient() as any;
      if (dir === "buy") {
        const usdcIn = parseUnits(amount, 6);
        const [out] = (await publicClient.readContract({
          address: selected.curve,
          abi: curveAbi,
          functionName: "buyQuote",
          args: [usdcIn],
        })) as readonly [bigint, bigint];
        const minOut = (out * 99n) / 100n;
        const a = await w.writeContract({ account, chain: null, address: ADDR.usdc, abi: erc20Abi, functionName: "approve", args: [selected.curve, usdcIn] });
        await publicClient.waitForTransactionReceipt({ hash: a });
        const h = await w.writeContract({ account, chain: null, address: selected.curve, abi: curveAbi, functionName: "buy", args: [usdcIn, minOut] });
        await publicClient.waitForTransactionReceipt({ hash: h });
        setMsg(`Bought ✓ ${EXPLORER}/tx/${h}`);
      } else {
        const tokensIn = parseUnits(amount, 18);
        const [usdcOut] = (await publicClient.readContract({
          address: selected.curve,
          abi: curveAbi,
          functionName: "sellQuote",
          args: [tokensIn],
        })) as readonly [bigint, bigint, bigint];
        const minOut = (usdcOut * 99n) / 100n;
        const a = await w.writeContract({ account, chain: null, address: selected.token, abi: erc20Abi, functionName: "approve", args: [selected.curve, tokensIn] });
        await publicClient.waitForTransactionReceipt({ hash: a });
        const h = await w.writeContract({ account, chain: null, address: selected.curve, abi: curveAbi, functionName: "sell", args: [tokensIn, minOut] });
        await publicClient.waitForTransactionReceipt({ hash: h });
        setMsg(`Sold ✓ ${EXPLORER}/tx/${h}`);
      }
    } catch (e) {
      setMsg((e as { shortMessage?: string }).shortMessage ?? (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="mx-auto w-full max-w-md">
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span>Swap on the curve</span>
          <Badge variant="muted">{dir === "buy" ? "USDC → Token" : "Token → USDC"}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <select
          value={selected?.token ?? ""}
          onChange={(e) => onSelect(agents.find((a) => a.token === e.target.value) ?? null)}
          className="h-10 w-full rounded-lg border border-zinc-800 bg-zinc-950/60 px-3 text-sm text-zinc-100 focus-visible:outline-none"
        >
          <option value="">Select an agent…</option>
          {agents.map((a) => (
            <option key={a.token} value={a.token}>
              {short(a.metadataURI)} · {short(a.token)}
            </option>
          ))}
        </select>

        <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-4">
          <div className="mb-1 text-[11px] text-zinc-500">{dir === "buy" ? "You pay (USDC)" : "You pay (Token)"}</div>
          <div className="flex items-center gap-2">
            <input
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              className="w-full bg-transparent font-mono text-2xl text-zinc-100 outline-none"
              placeholder="0.0"
            />
            <span className="font-mono text-sm text-zinc-400">{dir === "buy" ? "USDC" : "TOKEN"}</span>
          </div>
        </div>

        <div className="flex justify-center">
          <button
            onClick={() => setDir(dir === "buy" ? "sell" : "buy")}
            className="grid h-9 w-9 place-items-center rounded-lg border border-zinc-800 bg-zinc-900 text-zinc-300 transition-colors hover:bg-zinc-800"
          >
            <ArrowDownUp className="h-4 w-4" />
          </button>
        </div>

        <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-4">
          <div className="mb-1 text-[11px] text-zinc-500">You receive (est.)</div>
          <div className="font-mono text-sm text-emerald-400">
            {quote || `0.00 ${dir === "buy" ? (selected ? tokenTicker(selected.token) : "TOKEN") : "USDC"}`}
          </div>
          {price && <div className="mt-1 font-mono text-[11px] text-zinc-500">spot {price} USDC / token</div>}
        </div>

        <Button disabled={!account || !selected || busy} onClick={run} className="w-full">
          {dir === "buy" ? "Buy" : "Sell"}
        </Button>
        <p className="text-center text-[11px] text-zinc-600">1% slippage guard · 1% curve fee · gas in USDC</p>
      </CardContent>
    </Card>
  );
}
