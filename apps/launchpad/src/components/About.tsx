import { BookOpen, Coins, ExternalLink, Github, Landmark, Layers, Rocket, ShieldCheck, Zap } from "lucide-react";
import { ADDR } from "../contracts";
import { EXPLORER } from "../arc";
import { Badge } from "./ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";

const LINKS = {
  repo: "https://github.com/Salado210102/arc-smart-orders",
  release: "https://github.com/Salado210102/arc-smart-orders/releases/tag/mainnet-live-v1",
  docs: "https://github.com/Salado210102/arc-smart-orders/tree/main/docs",
  x: "https://x.com/VICENTEGon651262",
  arcHouse: "https://community.arc.io",
} as const;

const CONTRACTS: { name: string; addr: string; what: string }[] = [
  { name: "OrderExecutor", addr: "0x9b3a990d1a31Ff5E01ddB8702e10F2529811FDb7", what: "Smart-order fills (Permit2 witness + EIP-712 intent)" },
  { name: "AgentFactory", addr: ADDR.factory, what: "Launches an agent (token + USDC bonding curve)" },
  { name: "AgentRegistry", addr: ADDR.registry, what: "On-chain index of agents" },
  { name: "LiquidityLocker", addr: ADDR.locker, what: "365-day LP timelock (anti-rug)" },
  { name: "GraduationModule", addr: ADDR.module, what: "Seeds DEX liquidity at graduation (gated)" },
  { name: "Safe 2/2", addr: ADDR.safe, what: "Owner + treasury + feeRecipient" },
];

export function About() {
  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardContent className="p-6">
          <h2 className="text-xl font-semibold text-zinc-100">About Arc Smart Orders</h2>
          <p className="mt-2 max-w-3xl text-sm text-zinc-400">
            Non-custodial <strong className="text-zinc-200">smart orders</strong> and an{" "}
            <strong className="text-zinc-200">AI-agent launchpad</strong>, live on Arc mainnet. You sign an order
            off-chain; a keeper fills it on-chain — but the contract enforces exactly what you signed, so the keeper
            can never redirect the output or under-fill.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Badge variant="success">Live on Arc mainnet</Badge>
            <Badge variant="default">USDC-native</Badge>
            <Badge variant="violet">Open source · MIT</Badge>
            <Badge variant="muted">Non-custodial</Badge>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-5 md:grid-cols-3">
        <Feature
          icon={<Zap className="h-4 w-4 text-violet-400" />}
          title="Smart Orders"
          body="Sign a limit or TWAP order off-chain (Permit2 witness / EIP-712). A keeper fills it on-chain via Uniswap v3; the executor recomputes your commitment and reverts on mismatch."
        />
        <Feature
          icon={<Rocket className="h-4 w-4 text-violet-400" />}
          title="Agent Launchpad"
          body="Launch an AI agent on its own USDC bonding curve. It gets a token and an on-chain registry entry, with locked liquidity at graduation."
        />
        <Feature
          icon={<Coins className="h-4 w-4 text-emerald-400" />}
          title="Staking & Yield"
          body="Stake an agent token in an ERC-4626-style vault and earn the agent's USDC revenue: 70% to stakers, 30% to the Safe treasury."
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Layers className="h-4 w-4 text-violet-400" /> How it works
          </CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-zinc-400">
          <ol className="flex flex-col gap-2">
            <li>
              <span className="font-medium text-zinc-200">1 · Sign off-chain.</span> You authorize a Permit2
              transfer whose witness commits <code className="text-zinc-300">(tokenOut, minOut)</code> — or an
              EIP-712 <code className="text-zinc-300">DcaIntent</code> for recurring orders. Zero gas.
            </li>
            <li>
              <span className="font-medium text-zinc-200">2 · A keeper fills it.</span> The executor pulls the
              input, swaps on a whitelisted venue (Uniswap v3), and enforces your minimum on the net.
            </li>
            <li>
              <span className="font-medium text-zinc-200">3 · Fees route to a Safe.</span> A 0.30% input-side
              fee goes to a 2/2 Safe treasury. Funds never leave your wallet until the fill.
            </li>
          </ol>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-emerald-400" /> Contracts — Arc mainnet (5042)
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col divide-y divide-zinc-800/70">
            {CONTRACTS.map((c) => (
              <div key={c.name} className="flex flex-wrap items-center justify-between gap-2 py-2 text-xs">
                <div>
                  <span className="font-medium text-zinc-200">{c.name}</span>
                  <span className="ml-2 text-zinc-500">{c.what}</span>
                </div>
                <a
                  href={`${EXPLORER}/address/${c.addr}`}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 font-mono text-zinc-400 hover:text-emerald-300"
                >
                  {c.addr.slice(0, 10)}…{c.addr.slice(-6)} <ExternalLink className="h-3 w-3" />
                </a>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <BookOpen className="h-4 w-4 text-violet-400" /> Resources
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-2 sm:grid-cols-2">
          <ResourceLink icon={<Github className="h-3.5 w-3.5" />} href={LINKS.repo} label="Source code (MIT)" />
          <ResourceLink icon={<Layers className="h-3.5 w-3.5" />} href={LINKS.docs} label="Documentation" />
          <ResourceLink icon={<Rocket className="h-3.5 w-3.5" />} href={LINKS.release} label="Release — mainnet live" />
          <ResourceLink icon={<ExternalLink className="h-3.5 w-3.5" />} href={LINKS.x} label="Follow on X" />
          <ResourceLink icon={<Landmark className="h-3.5 w-3.5" />} href={LINKS.arcHouse} label="Arc House community" />
          <ResourceLink
            icon={<ShieldCheck className="h-3.5 w-3.5" />}
            href={`${EXPLORER}/address/${ADDR.safe}`}
            label="Treasury Safe (explorer)"
          />
        </CardContent>
      </Card>

      <p className="mx-auto max-w-3xl text-center text-[11px] leading-relaxed text-zinc-600">
        Reference implementation. Non-custodial — you keep your keys. Do your own research. Nothing here is
        financial advice.
      </p>
    </div>
  );
}

function Feature({ icon, title, body }: { icon: React.ReactNode; title: string; body: string }) {
  return (
    <Card>
      <CardContent className="p-5">
        <div className="flex items-center gap-2 text-sm font-medium text-zinc-100">
          {icon} {title}
        </div>
        <p className="mt-2 text-xs leading-relaxed text-zinc-400">{body}</p>
      </CardContent>
    </Card>
  );
}

function ResourceLink({ icon, href, label }: { icon: React.ReactNode; href: string; label: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="flex items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-950/60 px-3 py-2 text-xs text-zinc-300 transition-colors hover:border-zinc-700 hover:text-zinc-100"
    >
      {icon} {label} <ExternalLink className="ml-auto h-3 w-3 text-zinc-500" />
    </a>
  );
}
