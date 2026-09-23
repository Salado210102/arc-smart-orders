import { useCallback, useEffect, useState } from "react";
import { Plus, Rocket, Sparkles } from "lucide-react";
import { formatUnits, parseUnits } from "viem";
import { EXPLORER, connect, publicClient, walletClient } from "./arc";
import { ADDR, erc20Abi, factoryAbi, registryAbi } from "./contracts";
import { AgentCard, type Agent } from "./components/AgentCard";
import { Navbar, type Tab } from "./components/Navbar";
import { StakingPanel } from "./components/StakingPanel";
import { SwapBox } from "./components/SwapBox";
import { Button } from "./components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "./components/ui/card";
import { Input } from "./components/ui/input";

export default function App() {
  const [account, setAccount] = useState<`0x${string}` | null>(null);
  const [usdc, setUsdc] = useState("0");
  const [tab, setTab] = useState<Tab>("agents");
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selected, setSelected] = useState<Agent | null>(null);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const [name, setName] = useState("My Agent");
  const [symbol, setSymbol] = useState("AGT");
  const [meta, setMeta] = useState("");
  const [pinataJwt, setPinataJwt] = useState(() => localStorage.getItem("pinataJwt") ?? "");

  const refreshAgents = useCallback(async () => {
    try {
      const list = (await publicClient.readContract({
        address: ADDR.registry,
        abi: registryAbi,
        functionName: "all",
      })) as readonly Agent[];
      setAgents(list.map((a) => ({ ...a })));
    } catch (e) {
      console.error(e);
    }
  }, []);

  useEffect(() => {
    void refreshAgents();
  }, [refreshAgents]);

  useEffect(() => {
    (async () => {
      if (!account) {
        setUsdc("0");
        return;
      }
      try {
        const b = (await publicClient.readContract({
          address: ADDR.usdc,
          abi: erc20Abi,
          functionName: "balanceOf",
          args: [account],
        })) as bigint;
        setUsdc(formatUnits(b, 6));
      } catch {
        /* ignore */
      }
    })();
  }, [account, msg]);

  async function doConnect() {
    try {
      setAccount(await connect());
    } catch (e) {
      setMsg((e as Error).message);
    }
  }

  async function pinMeta() {
    if (!pinataJwt) return setMsg("Paste a Pinata JWT first (stored locally in your browser).");
    setBusy(true);
    setMsg("Pinning metadata to IPFS…");
    try {
      const body = {
        pinataContent: { name, symbol, description: `${name} — AI agent launched on Arc`, capabilities: [], version: "1.0.0" },
        pinataMetadata: { name: `${symbol}-metadata.json` },
      };
      const r = await fetch("https://api.pinata.cloud/pinning/pinJSONToIPFS", {
        method: "POST",
        headers: { "content-type": "application/json", Authorization: `Bearer ${pinataJwt}` },
        body: JSON.stringify(body),
      });
      const j = (await r.json()) as { IpfsHash?: string; error?: { details?: string } };
      if (!r.ok || !j.IpfsHash) throw new Error(j?.error?.details ?? "pin_failed");
      localStorage.setItem("pinataJwt", pinataJwt);
      setMeta(`ipfs://${j.IpfsHash}`);
      setMsg(`Pinned ✓ ipfs://${j.IpfsHash}`);
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function create() {
    if (!account) return;
    setBusy(true);
    setMsg("Launching agent…");
    try {
      const w = walletClient() as any;
      const hash = await w.writeContract({
        account,
        chain: null,
        address: ADDR.factory,
        abi: factoryAbi,
        functionName: "launch",
        args: [
          name,
          symbol,
          parseUnits("1000000", 18),
          parseUnits("5000", 6),
          parseUnits("10000", 6),
          parseUnits("100000", 18),
          parseUnits("100000", 18),
          meta,
        ],
      });
      await publicClient.waitForTransactionReceipt({ hash });
      setMsg(`Agent launched ✓ ${EXPLORER}/tx/${hash}`);
      await refreshAgents();
      setTab("agents");
    } catch (e) {
      setMsg((e as { shortMessage?: string }).shortMessage ?? (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function trade(a: Agent) {
    setSelected(a);
    setTab("trade");
  }

  return (
    <div className="flex min-h-screen flex-col">
      <Navbar account={account} usdc={usdc} tab={tab} setTab={setTab} onConnect={doConnect} />

      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">
        {msg && (
          <div className="mb-6 rounded-lg border border-zinc-800 bg-zinc-900/60 px-4 py-3 font-mono text-xs text-zinc-300 break-all">
            {msg}
          </div>
        )}

        {tab === "agents" && (
          <>
            <SectionHeading
              title="Agents"
              subtitle={`${agents.length} agent${agents.length === 1 ? "" : "s"} registered on Arc`}
              action={
                <Button variant="secondary" size="sm" onClick={() => setTab("create")}>
                  <Plus className="h-3.5 w-3.5" /> New agent
                </Button>
              }
            />
            {agents.length === 0 ? (
              <Card className="p-10 text-center">
                <Rocket className="mx-auto h-6 w-6 text-violet-400" />
                <p className="mt-3 text-sm text-zinc-400">No agents yet — launch the first one.</p>
                <Button className="mt-4" size="sm" onClick={() => setTab("create")}>
                  Create agent
                </Button>
              </Card>
            ) : (
              <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
                {agents.map((a) => (
                  <AgentCard key={a.token} agent={a} onTrade={trade} />
                ))}
              </div>
            )}
          </>
        )}

        {tab === "create" && (
          <div className="mx-auto max-w-xl">
            <SectionHeading title="Launch an AI Agent" subtitle="ERC-8004 identity + USDC bonding curve" />
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-violet-400" /> Agent details
                </CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name" />
                <Input value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder="Ticker (e.g. AGT)" />
                <div>
                  <div className="mb-1 text-[11px] text-zinc-500">Metadata URI (auto-generated when pinned)</div>
                  <div className="flex items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-950/40 px-3 py-2">
                    <span className="min-w-0 flex-1 truncate font-mono text-xs text-zinc-400">
                      {meta || "not pinned yet"}
                    </span>
                    {meta && (
                      <button
                        onClick={() => {
                          navigator.clipboard.writeText(meta);
                          setMsg(`Copied ${meta}`);
                        }}
                        className="shrink-0 rounded-md border border-zinc-800 bg-zinc-900 px-2 py-1 text-[11px] text-zinc-400 hover:text-zinc-200"
                      >
                        Copy
                      </button>
                    )}
                  </div>
                </div>
                <Input
                  type="password"
                  value={pinataJwt}
                  onChange={(e) => setPinataJwt(e.target.value)}
                  placeholder="Pinata JWT (optional — pin metadata to IPFS)"
                />
                <div className="grid grid-cols-2 gap-3">
                  <Button variant="secondary" disabled={busy} onClick={pinMeta}>
                    Pin to IPFS
                  </Button>
                  <Button disabled={!account || busy} onClick={create}>
                    Launch
                  </Button>
                </div>
                <p className="text-[11px] text-zinc-600">
                  Soft launch: 1,000,000 supply · 5,000 USDC virtual · 10,000 USDC graduation cap · 1% fee · LP locked 365d.
                </p>
              </CardContent>
            </Card>
          </div>
        )}

        {tab === "trade" && (
          <>
            <SectionHeading title="Trade" subtitle="Buy / sell on the bonding curve" />
            <SwapBox agents={agents} selected={selected} account={account} onSelect={setSelected} setMsg={setMsg} busy={busy} setBusy={setBusy} />
          </>
        )}

        {tab === "stake" && (
          <>
            <SectionHeading title="Staking & Yield" subtitle="Stake the agent token, earn USDC" />
            <StakingPanel account={account} setMsg={setMsg} busy={busy} setBusy={setBusy} refreshKey={msg} />
          </>
        )}
      </main>

      <footer className="border-t border-zinc-800/60 py-6 text-center text-[11px] text-zinc-600">
        Arc Agent Launchpad · <a className="hover:text-zinc-400" href="https://github.com/Salado210102/arc-smart-orders" target="_blank" rel="noreferrer">open source (MIT)</a> · non-custodial · testnet
      </footer>
    </div>
  );
}

function SectionHeading({ title, subtitle, action }: { title: string; subtitle?: string; action?: React.ReactNode }) {
  return (
    <div className="mb-6 flex items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-zinc-500">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}
