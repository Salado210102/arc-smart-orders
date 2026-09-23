import { useEffect, useState } from "react";
import { ArrowUpRight, Check, Coins, Copy } from "lucide-react";
import { publicClient } from "../arc";
import { curveAbi } from "../contracts";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { Progress } from "./ui/progress";
import { ipfsUrls, short, tokenTicker } from "../lib/utils";

export type Agent = {
  agentId: bigint;
  token: `0x${string}`;
  curve: `0x${string}`;
  creator: `0x${string}`;
  metadataURI: string;
  createdAt: bigint;
};

const gw = (uri: string) => ipfsUrls(uri)[0] ?? uri;

function useMeta(uri: string) {
  const [m, setM] = useState<{ name?: string; symbol?: string; image?: string; description?: string }>({});
  useEffect(() => {
    let alive = true;
    if (!uri) return;
    (async () => {
      for (const url of ipfsUrls(uri)) {
        try {
          const r = await fetch(url);
          if (!r.ok) continue;
          const j = await r.json();
          if (alive) setM(j);
          return;
        } catch {
          /* try next gateway */
        }
      }
    })();
    return () => {
      alive = false;
    };
  }, [uri]);
  return m;
}

function useProgress(curve: `0x${string}`) {
  const [p, setP] = useState<{ raised: bigint; target: bigint; graduated: boolean }>({
    raised: 0n,
    target: 0n,
    graduated: false,
  });
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [raised, target, graduated] = await Promise.all([
          publicClient.readContract({ address: curve, abi: curveAbi, functionName: "raisedUsdc" }),
          publicClient.readContract({ address: curve, abi: curveAbi, functionName: "graduationUsdc" }),
          publicClient.readContract({ address: curve, abi: curveAbi, functionName: "graduated" }),
        ]);
        if (alive) setP({ raised: raised as bigint, target: target as bigint, graduated: graduated as boolean });
      } catch {
        /* ignore */
      }
    })();
    return () => {
      alive = false;
    };
  }, [curve]);
  return p;
}

function CopyChip({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => {
        navigator.clipboard.writeText(value);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
      className="inline-flex items-center gap-1 rounded-md border border-zinc-800 bg-zinc-950/60 px-2 py-1 font-mono text-[11px] text-zinc-400 transition-colors hover:text-zinc-200"
      title={value}
    >
      {copied ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
      {label} {short(value)}
    </button>
  );
}

export function AgentCard({ agent, onTrade }: { agent: Agent; onTrade: (a: Agent) => void }) {
  const meta = useMeta(agent.metadataURI);
  const prog = useProgress(agent.curve);
  const pct = prog.target > 0n ? Number((prog.raised * 10000n) / prog.target) / 100 : 0;
  const ticker = meta.symbol ? `$${meta.symbol}` : tokenTicker(agent.token);
  const name = meta.name || `Agent #${agent.agentId}`;

  return (
    <Card className="group flex flex-col overflow-hidden transition-colors hover:border-zinc-700">
      <div className="flex items-center gap-3 border-b border-zinc-800/70 p-4">
        <div className="grid h-12 w-12 shrink-0 place-items-center overflow-hidden rounded-xl border border-zinc-800 bg-zinc-950">
          {meta.image ? (
            <img src={gw(meta.image)} alt="" className="h-full w-full object-cover" />
          ) : (
            <Coins className="h-5 w-5 text-violet-400" />
          )}
        </div>
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-zinc-100">{name}</div>
          <div className="font-mono text-xs text-emerald-400">{ticker}</div>
        </div>
        <Badge variant={prog.graduated ? "success" : "violet"} className="ml-auto shrink-0">
          {prog.graduated ? "Graduated" : "On curve"}
        </Badge>
      </div>

      <div className="flex flex-1 flex-col gap-3 p-4">
        <div>
          <div className="mb-1.5 flex items-center justify-between text-[11px] text-zinc-500">
            <span>Bonding curve</span>
            <span className="font-mono text-zinc-300">{pct.toFixed(1)}% to DEX</span>
          </div>
          <Progress value={pct} />
          <div className="mt-1.5 font-mono text-[11px] text-zinc-500">
            {Number(prog.raised / 10n ** 6n).toLocaleString()} / {Number(prog.target / 10n ** 6n).toLocaleString()} USDC
            raised
          </div>
        </div>

        <div className="flex flex-wrap gap-1.5">
          <CopyChip label="token" value={agent.token} />
          <CopyChip label="curve" value={agent.curve} />
        </div>

        <Button className="mt-auto w-full" size="sm" onClick={() => onTrade(agent)}>
          Trade <ArrowUpRight className="h-3.5 w-3.5" />
        </Button>
      </div>
    </Card>
  );
}
