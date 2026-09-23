import { Lock } from "lucide-react";
import { Card } from "./ui/card";

export function StakingPanel(_props: {
  account: `0x${string}` | null;
  setMsg: (m: string) => void;
  busy: boolean;
  setBusy: (b: boolean) => void;
  refreshKey: string;
}) {
  return (
    <Card className="mx-auto max-w-lg p-10 text-center">
      <div className="mx-auto grid h-12 w-12 place-items-center rounded-2xl border border-violet-900/50 bg-violet-950/30">
        <Lock className="h-5 w-5 text-violet-400" />
      </div>
      <h3 className="mt-4 text-sm font-semibold text-zinc-100">Staking &amp; Yield Vaults</h3>
      <p className="mt-2 text-sm text-zinc-400">Coming soon — pending access to Arc&apos;s liquidity venues.</p>
      <p className="mx-auto mt-3 max-w-sm text-[11px] leading-relaxed text-zinc-600">
        Per-agent ERC-4626 revenue vaults and the 70/30 RevenueSplitter activate once the Arc FX venue and DEX
        graduation are live.
      </p>
    </Card>
  );
}
