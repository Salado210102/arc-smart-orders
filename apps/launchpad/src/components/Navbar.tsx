import { useEffect, useState } from "react";
import { Activity, BarChart3, Droplet, LogOut, Plus, Wallet, Zap } from "lucide-react";
import { cn, short } from "../lib/utils";

export type Tab = "agents" | "dashboard" | "create" | "trade" | "swap" | "stake";

const TABS: { key: Tab; label: string; icon: typeof Activity }[] = [
  { key: "agents", label: "Agents", icon: Activity },
  { key: "dashboard", label: "Dashboard", icon: BarChart3 },
  { key: "create", label: "Create", icon: Plus },
  { key: "trade", label: "Trade", icon: Droplet },
  { key: "swap", label: "Smart Swap", icon: Zap },
  { key: "stake", label: "Staking & Yield", icon: Wallet },
];

export function Navbar({
  account,
  usdc,
  tab,
  setTab,
  onConnect,
  onDisconnect,
}: {
  account: `0x${string}` | null;
  usdc: string;
  tab: Tab;
  setTab: (t: Tab) => void;
  onConnect: () => void;
  onDisconnect: () => void;
}) {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 8);
    window.addEventListener("scroll", on);
    return () => window.removeEventListener("scroll", on);
  }, []);

  return (
    <header
      className={cn(
        "sticky top-0 z-50 border-b transition-colors",
        scrolled ? "border-zinc-800 bg-zinc-950/80 backdrop-blur-xl" : "border-transparent bg-transparent",
      )}
    >
      <div className="mx-auto flex h-16 max-w-6xl items-center gap-4 px-4">
        {/* Logo */}
        <div className="flex items-center gap-2.5">
          <div className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-violet-600 to-emerald-500 shadow-lg shadow-violet-900/30">
            <Spark />
          </div>
          <div className="leading-tight">
            <div className="text-sm font-semibold tracking-tight text-zinc-100">Arc Agent Launchpad</div>
            <div className="font-mono text-[10px] uppercase tracking-widest text-zinc-500">smart orders · erc-8004</div>
          </div>
        </div>

        {/* Network pill */}
        <span className="ml-2 hidden items-center gap-1.5 rounded-full border border-emerald-800/60 bg-emerald-950/40 px-2.5 py-1 text-[11px] font-medium text-emerald-400 sm:flex">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
          Arc Mainnet · 5042
        </span>

        {/* Tabs */}
        <nav className="ml-auto hidden items-center gap-1 rounded-xl border border-zinc-800 bg-zinc-900/40 p-1 md:flex">
          {TABS.map((t) => {
            const Ico = t.icon;
            return (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                className={cn(
                  "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors",
                  tab === t.key ? "bg-zinc-800 text-zinc-100" : "text-zinc-400 hover:text-zinc-200",
                )}
              >
                <Ico className="h-3.5 w-3.5" />
                {t.label}
              </button>
            );
          })}
        </nav>

        {/* Connect */}
        <div className="ml-3">
          {account ? (
            <div className="flex items-center gap-2">
              <span className="hidden items-center gap-1.5 rounded-lg border border-zinc-800 bg-zinc-900/60 px-3 py-2 font-mono text-xs text-emerald-400 sm:flex">
                ${Number(usdc).toLocaleString(undefined, { maximumFractionDigits: 2 })} USDC
              </span>
              <span className="rounded-lg border border-violet-800/60 bg-violet-950/30 px-3 py-2 font-mono text-xs text-violet-300">
                {short(account)}
              </span>
              <button
                onClick={onDisconnect}
                title="Disconnect"
                aria-label="Disconnect"
                className="grid h-9 w-9 place-items-center rounded-lg border border-zinc-800 bg-zinc-900/60 text-zinc-400 transition-colors hover:text-zinc-100"
              >
                <LogOut className="h-4 w-4" />
              </button>
            </div>
          ) : (
            <button
              onClick={onConnect}
              className="flex items-center gap-2 rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white shadow-lg shadow-violet-900/30 transition-colors hover:bg-violet-500"
            >
              <Wallet className="h-4 w-4" />
              Connect Wallet
            </button>
          )}
        </div>
      </div>

      {/* Mobile tabs */}
      <nav className="flex items-center gap-1 overflow-x-auto border-t border-zinc-800/60 px-4 py-2 md:hidden">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={cn(
              "whitespace-nowrap rounded-lg px-3 py-1.5 text-xs font-medium",
              tab === t.key ? "bg-zinc-800 text-zinc-100" : "text-zinc-400",
            )}
          >
            {t.label}
          </button>
        ))}
      </nav>
    </header>
  );
}

function Spark() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2 4 15h6l-1 7 8-13h-6l1-7z" />
    </svg>
  );
}
