import { useEffect, useState } from "react";
import { Coins, PiggyBank, TrendingUp } from "lucide-react";
import { formatUnits, parseUnits } from "viem";
import { EXPLORER, publicClient, walletClient } from "../arc";
import { ADDR, erc20Abi, vaultAbi } from "../contracts";
import { Button } from "./ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { Input } from "./ui/input";

export function StakingPanel({
  account,
  setMsg,
  busy,
  setBusy,
  refreshKey,
}: {
  account: `0x${string}` | null;
  setMsg: (m: string) => void;
  busy: boolean;
  setBusy: (b: boolean) => void;
  refreshKey: string;
}) {
  const [stakeAmt, setStakeAmt] = useState("100");
  const [staked, setStaked] = useState("0");
  const [pending, setPending] = useState("0");
  const [tvl, setTvl] = useState("0");

  useEffect(() => {
    (async () => {
      try {
        const t = (await publicClient.readContract({ address: ADDR.vault, abi: vaultAbi, functionName: "totalAssets" })) as bigint;
        setTvl(formatUnits(t, 18));
        if (account) {
          const [b, p] = await Promise.all([
            publicClient.readContract({ address: ADDR.vault, abi: vaultAbi, functionName: "balanceOf", args: [account] }) as Promise<bigint>,
            publicClient.readContract({ address: ADDR.vault, abi: vaultAbi, functionName: "pendingRewards", args: [account] }) as Promise<bigint>,
          ]);
          setStaked(formatUnits(b, 18));
          setPending(formatUnits(p, 6));
        }
      } catch {
        /* ignore */
      }
    })();
  }, [account, refreshKey]);

  async function act(kind: "stake" | "unstake" | "claim") {
    if (!account) return;
    setBusy(true);
    setMsg(kind === "claim" ? "Claiming USDC…" : kind === "stake" ? "Approving + staking…" : "Unstaking…");
    try {
      const w = walletClient() as any;
      let h: `0x${string}`;
      if (kind === "stake") {
        const amt = parseUnits(stakeAmt, 18);
        const a = await w.writeContract({ account, chain: null, address: ADDR.vaultAsset, abi: erc20Abi, functionName: "approve", args: [ADDR.vault, amt] });
        await publicClient.waitForTransactionReceipt({ hash: a });
        h = await w.writeContract({ account, chain: null, address: ADDR.vault, abi: vaultAbi, functionName: "deposit", args: [amt, account] });
      } else if (kind === "unstake") {
        const amt = parseUnits(stakeAmt, 18);
        h = await w.writeContract({ account, chain: null, address: ADDR.vault, abi: vaultAbi, functionName: "withdraw", args: [amt, account, account] });
      } else {
        h = await w.writeContract({ account, chain: null, address: ADDR.vault, abi: vaultAbi, functionName: "claim" });
      }
      await publicClient.waitForTransactionReceipt({ hash: h });
      setMsg(`${kind.toUpperCase()} ✓ ${EXPLORER}/tx/${h}`);
    } catch (e) {
      setMsg((e as { shortMessage?: string }).shortMessage ?? (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-5 md:grid-cols-2">
      <div className="flex flex-col gap-5">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-violet-400" /> Vault stats
            </CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-4">
            <Stat label="Total staked" value={`${Number(tvl).toLocaleString()} sAGT`} />
            <Stat label="Your stake" value={`${Number(staked).toLocaleString()} sAGT`} accent="violet" />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <PiggyBank className="h-4 w-4 text-violet-400" /> Stake / Unstake
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <Input value={stakeAmt} onChange={(e) => setStakeAmt(e.target.value)} placeholder="Amount (sAGT)" />
            <div className="grid grid-cols-2 gap-3">
              <Button disabled={!account || busy} onClick={() => act("stake")}>
                Stake
              </Button>
              <Button variant="secondary" disabled={!account || busy} onClick={() => act("unstake")}>
                Unstake
              </Button>
            </div>
            <p className="text-[11px] text-zinc-600">
              Deposits the agent token (ERC-4626). Principal returns exactly on unstake.
            </p>
          </CardContent>
        </Card>
      </div>

      <Card className="overflow-hidden border-emerald-900/40">
        <div className="bg-gradient-to-br from-emerald-950/40 to-zinc-900/0 p-6">
          <div className="flex items-center gap-2 text-xs text-emerald-400">
            <Coins className="h-4 w-4" /> Claimable USDC yield
          </div>
          <div className="mt-3 font-mono text-4xl font-semibold text-emerald-400">
            ${Number(pending).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 6 })}
          </div>
          <p className="mt-2 text-[11px] text-zinc-500">
            Agent revenue is split by <span className="font-mono">RevenueSplitter</span> — 70% to stakers, 30% to
            treasury.
          </p>
        </div>
        <CardContent className="pt-5">
          <Button variant="success" className="w-full" disabled={!account || busy || Number(pending) <= 0} onClick={() => act("claim")}>
            Claim USDC
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: "violet" }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-4">
      <div className="text-[11px] text-zinc-500">{label}</div>
      <div className={`mt-1 font-mono text-lg font-semibold ${accent === "violet" ? "text-violet-300" : "text-zinc-100"}`}>
        {value}
      </div>
    </div>
  );
}
