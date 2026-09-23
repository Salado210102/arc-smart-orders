import { useEffect, useState } from "react";
import { Coins, Landmark, Percent, Users } from "lucide-react";
import { formatUnits } from "viem";
import { publicClient } from "../arc";
import { ADDR, curveAbi, erc20Abi, registryAbi } from "../contracts";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { HealthMonitor } from "./HealthMonitor";
import type { Agent } from "./AgentCard";

export function Dashboard() {
  const [count, setCount] = useState(0);
  const [raised, setRaised] = useState(0n);
  const [treasury, setTreasury] = useState(0n);
  const [err, setErr] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const list = (await publicClient.readContract({
          address: ADDR.registry,
          abi: registryAbi,
          functionName: "all",
        })) as readonly Agent[];
        setCount(list.length);
        const rs = await Promise.all(
          list.map((a) =>
            publicClient
              .readContract({ address: a.curve, abi: curveAbi, functionName: "raisedUsdc" })
              .catch(() => 0n),
          ),
        );
        setRaised(rs.reduce((s, v) => s + (v as bigint), 0n));
        const t = (await publicClient.readContract({
          address: ADDR.usdc,
          abi: erc20Abi,
          functionName: "balanceOf",
          args: [ADDR.safe],
        })) as bigint;
        setTreasury(t);
      } catch (e) {
        setErr((e as Error).message);
      }
    })();
  }, []);

  const usd = (v: bigint) =>
    Number(formatUnits(v, 6)).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  return (
    <>
      <HealthMonitor />
      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
        <Stat icon={<Users className="h-4 w-4 text-violet-400" />} label="Agents launched" value={String(count)} />
        <Stat icon={<Coins className="h-4 w-4 text-emerald-400" />} label="USDC raised on curves" value={`$${usd(raised)}`} />
        <Stat icon={<Landmark className="h-4 w-4 text-emerald-400" />} label="Protocol treasury (Safe)" value={`$${usd(treasury)}`} />
        <Stat icon={<Percent className="h-4 w-4 text-violet-400" />} label="Fees" value="0.30% orders · 1% curve" />
      </div>

      <Card className="mt-5">
        <CardHeader>
          <CardTitle>Protocol metrics — Arc mainnet (5042)</CardTitle>
        </CardHeader>
        <CardContent className="text-xs text-zinc-500">
          <ul className="flex flex-col gap-1.5">
            <li>• All fees flow to the Safe 2/2 <span className="font-mono text-zinc-400">0x0FBFAF…7e93</span> (owner + treasury).</li>
            <li>• Bonding-curve fee (1%) splits 50% → Safe / 50% → the agent&apos;s creator.</li>
            <li>• Order-engine fee (0.30%, input-side) → Safe — <span className="text-emerald-400/80">live now</span> via Uniswap v3 fills.</li>
            <li>• <span className="text-emerald-400/80">Staking &amp; Yield vaults are live</span> per agent (70% stakers / 30% Safe); graduation is pending.</li>
          </ul>
          {err && <p className="mt-3 text-rose-400/80">read error: {err}</p>}
        </CardContent>
      </Card>
    </>
  );
}

function Stat({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <Card>
      <CardContent className="p-5">
        <div className="flex items-center gap-2 text-[11px] text-zinc-500">
          {icon}
          {label}
        </div>
        <div className="mt-2 font-mono text-xl font-semibold text-zinc-100">{value}</div>
      </CardContent>
    </Card>
  );
}
