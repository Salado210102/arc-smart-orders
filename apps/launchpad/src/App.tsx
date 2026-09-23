import { useEffect, useState } from "react";
import { parseUnits, formatUnits } from "viem";
import { publicClient, connect, walletClient, EXPLORER } from "./arc.ts";
import { ADDR, factoryAbi, registryAbi, curveAbi, erc20Abi } from "./contracts.ts";

type Agent = {
  agentId: bigint;
  token: `0x${string}`;
  curve: `0x${string}`;
  creator: `0x${string}`;
  metadataURI: string;
  createdAt: bigint;
};

export default function App() {
  const [account, setAccount] = useState<`0x${string}` | null>(null);
  const [tab, setTab] = useState<"agents" | "create" | "trade">("agents");
  const [agents, setAgents] = useState<Agent[]>([]);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  async function refresh() {
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
  }
  useEffect(() => {
    void refresh();
  }, []);

  async function doConnect() {
    try {
      setAccount(await connect());
    } catch (e) {
      setMsg((e as Error).message);
    }
  }

  // ---- create ----
  const [name, setName] = useState("My Agent");
  const [symbol, setSymbol] = useState("AGT");
  const [meta, setMeta] = useState("ipfs://bafkreibdi6623n3xpf7ymk62ckb4bo75o3qemwkpfvp5i25j66itxvsoei");
  async function create() {
    if (!account) return;
    setBusy(true);
    setMsg("Launching…");
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
          parseUnits("1000000", 6),
          parseUnits("1000000", 18),
          parseUnits("1000000", 18),
          meta,
        ],
      });
      await publicClient.waitForTransactionReceipt({ hash });
      setMsg(`Launched ✓ ${EXPLORER}/tx/${hash}`);
      await refresh();
    } catch (e) {
      setMsg((e as { shortMessage?: string }).shortMessage ?? (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  // ---- trade ----
  const [sel, setSel] = useState<Agent | null>(null);
  const [amount, setAmount] = useState("10");
  const [quote, setQuote] = useState("");
  useEffect(() => {
    (async () => {
      if (!sel || !amount) return setQuote("");
      try {
        const [out, fee] = (await publicClient.readContract({
          address: sel.curve,
          abi: curveAbi,
          functionName: "buyQuote",
          args: [parseUnits(amount, 6)],
        })) as readonly [bigint, bigint];
        setQuote(`→ ~${Number(formatUnits(out, 18)).toLocaleString()} tokens · fee ${formatUnits(fee, 6)} USDC`);
      } catch {
        setQuote("");
      }
    })();
  }, [sel, amount]);

  async function buy() {
    if (!account || !sel) return;
    setBusy(true);
    setMsg("Approving + buying…");
    try {
      const w = walletClient() as any;
      const usdcIn = parseUnits(amount, 6);
      const [out] = (await publicClient.readContract({
        address: sel.curve,
        abi: curveAbi,
        functionName: "buyQuote",
        args: [usdcIn],
      })) as readonly [bigint, bigint];
      const minOut = (out * 99n) / 100n;
      const a = await w.writeContract({ account, chain: null, address: ADDR.usdc, abi: erc20Abi, functionName: "approve", args: [sel.curve, usdcIn] });
      await publicClient.waitForTransactionReceipt({ hash: a });
      const h = await w.writeContract({ account, chain: null, address: sel.curve, abi: curveAbi, functionName: "buy", args: [usdcIn, minOut] });
      await publicClient.waitForTransactionReceipt({ hash: h });
      setMsg(`Bought ✓ ${EXPLORER}/tx/${h}`);
    } catch (e) {
      setMsg((e as { shortMessage?: string }).shortMessage ?? (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function sell() {
    if (!account || !sel) return;
    setBusy(true);
    setMsg("Approving + selling…");
    try {
      const w = walletClient() as any;
      const tokensIn = parseUnits(amount, 18);
      const [usdcOut] = (await publicClient.readContract({
        address: sel.curve,
        abi: curveAbi,
        functionName: "sellQuote",
        args: [tokensIn],
      })) as readonly [bigint, bigint, bigint];
      const minOut = (usdcOut * 99n) / 100n;
      const a = await w.writeContract({ account, chain: null, address: sel.token, abi: erc20Abi, functionName: "approve", args: [sel.curve, tokensIn] });
      await publicClient.waitForTransactionReceipt({ hash: a });
      const h = await w.writeContract({ account, chain: null, address: sel.curve, abi: curveAbi, functionName: "sell", args: [tokensIn, minOut] });
      await publicClient.waitForTransactionReceipt({ hash: h });
      setMsg(`Sold ✓ ${EXPLORER}/tx/${h}`);
    } catch (e) {
      setMsg((e as { shortMessage?: string }).shortMessage ?? (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="wrap">
      <h1>🤖 Agent Launchpad — Arc</h1>
      <div className="tabs" style={{ marginBottom: 14 }}>
        {account ? (
          <span className="muted">{account} · <a href={`${EXPLORER}/address/${account}`} target="_blank" rel="noreferrer">explorer</a></span>
        ) : (
          <button onClick={doConnect}>Connect wallet</button>
        )}
      </div>

      <div className="tabs">
        <button className={tab === "agents" ? "" : "sec"} onClick={() => setTab("agents")}>Agents ({agents.length})</button>
        <button className={tab === "create" ? "" : "sec"} onClick={() => setTab("create")}>Create</button>
        <button className={tab === "trade" ? "" : "sec"} onClick={() => setTab("trade")}>Trade</button>
      </div>

      {msg && <p className="card" style={{ wordBreak: "break-all" }}>{msg}</p>}

      {tab === "agents" && (
        <div>
          {agents.length === 0 && <p className="muted">No agents yet.</p>}
          {agents.map((a) => (
            <div className="card" key={a.token}>
              <div><b>{a.metadataURI}</b></div>
              <div className="muted">token <code>{a.token}</code></div>
              <div className="muted">curve <code>{a.curve}</code> · creator <code>{a.creator}</code></div>
            </div>
          ))}
        </div>
      )}

      {tab === "create" && (
        <div className="card">
          <h2>Launch an AI Agent</h2>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name" />
          <input value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder="Symbol" />
          <input value={meta} onChange={(e) => setMeta(e.target.value)} placeholder="Metadata URI (IPFS)" />
          <p className="muted">Defaults: supply 1,000,000 · x0 5,000 USDC · graduation 1,000,000 USDC · fee 1% · lock 365d</p>
          <button disabled={!account || busy} onClick={create}>Create agent (ERC-8004 + curve)</button>
        </div>
      )}

      {tab === "trade" && (
        <div className="card">
          <h2>Buy / Sell on the curve</h2>
          <select onChange={(e) => setSel(agents[Number(e.target.value)] ?? null)} defaultValue="-1">
            <option value="-1">Select an agent…</option>
            {agents.map((a, i) => (
              <option key={a.token} value={i}>{a.metadataURI}</option>
            ))}
          </select>
          <input value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="Amount (USDC to buy / tokens to sell)" />
          {quote && <p className="muted">{quote}</p>}
          <div style={{ display: "flex", gap: 8 }}>
            <button disabled={!account || !sel || busy} onClick={buy}>Buy</button>
            <button className="sec" disabled={!account || !sel || busy} onClick={sell}>Sell</button>
          </div>
          <p className="muted">Buy input is USDC (6 dec). Sell input is the agent token (18 dec). 1% slippage guard.</p>
        </div>
      )}
    </div>
  );
}
