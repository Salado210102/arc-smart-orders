import { Wallet, X } from "lucide-react";
import { Card } from "./ui/card";
import type { WalletInfo } from "../arc";

export function WalletPicker({
  wallets,
  onPick,
  onClose,
}: {
  wallets: WalletInfo[];
  onPick: (w: WalletInfo) => void;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4 backdrop-blur-sm" onClick={onClose}>
      <Card className="w-full max-w-sm p-5" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <div className="text-sm font-semibold text-zinc-100">Connect a wallet</div>
          <button onClick={onClose} className="rounded-md p-1 text-zinc-500 transition-colors hover:text-zinc-200">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="flex flex-col gap-2">
          {wallets.map((w) => (
            <button
              key={w.rdns ?? w.name}
              onClick={() => onPick(w)}
              className="flex items-center gap-3 rounded-lg border border-zinc-800 bg-zinc-950/60 px-3 py-2.5 text-left transition-colors hover:border-zinc-700 hover:bg-zinc-900"
            >
              {w.icon ? (
                <img src={w.icon} alt="" className="h-6 w-6 rounded" />
              ) : (
                <Wallet className="h-5 w-5 text-zinc-400" />
              )}
              <span className="text-sm text-zinc-200">{w.name}</span>
            </button>
          ))}
        </div>
        <p className="mt-4 text-center text-[11px] text-zinc-600">
          Arc Mainnet · chain 5042 · your keys stay in your wallet
        </p>
      </Card>
    </div>
  );
}
