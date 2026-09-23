import { useCallback, useEffect, useState } from "react";
import { Coins, Gift, Lock, Wallet } from "lucide-react";
import { formatUnits, parseUnits } from "viem";
import { EXPLORER, publicClient, walletClient } from "../arc";
import { ADDR, erc20Abi, vaultAbi } from "../contracts";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { short } from "../lib/utils";

const tokenMetaAbi = [
  { type: "function", name: "symbol", stateMutability: "view", inputs: [], outputs: [{ type: "string" }] },
  { type: "function", name: "decimals", stateMutability: "view", inputs: [], outputs: [{ type: "uint8" }] },
] as const;

const VAULT = ADDR.vault;
const TOKEN = ADDR.vaultAsset;

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
  const [symbol, setSymbol] = useState("TOKEN");
  const [decimals, setDecimals] = useState(18);
  const [amount, setAmount] = useState("100");
  const [staked, setStaked] = useState(0n); // user shares
  const [pending, setPending] = useState(0n); // USDC claimable
  const [walletBal, setWalletBal] = useState(0n); // agent token balance
  const [allowance, setAllowance] = useState(0n);
  const [totalStaked, setTotalStaked] = useState(0n);
  const [pool, setPool] = useState(0n); // USDC waiting for the next staker

  const refresh = useCallback(async () => {
    try {
      const [sym, dec] = await Promise.all([
        publicClient.readContract({ address: TOKEN, abi: tokenMetaAbi, functionName: "symbol" }).catch(() => "TOKEN"),
        publicClient.readContract({ address: TOKEN, abi: tokenMetaAbi, functionName: "decimals" }).catch(() => 18),
      ]);
      setSymbol(sym as string);
      setDecimals(Number(dec));
      const [ts, pl] = await Promise.all([
        publicClient.readContract({ address: VAULT, abi: vaultAbi, functionName: "totalSupply" }) as Promise<bigint>,
        publicClient.readContract({ address: VAULT, abi: vaultAbi, functionName: "pool" }).catch(() => 0n) as Promise<bigint>,
      ]);
      setTotalStaked(ts);
      setPool(pl);
      if (!account) {
        setStaked(0n);
        setPending(0n);
        setWalletBal(0n);
        setAllowance(0n);
        return;
      }
      const [s, p, bal, al] = await Promise.all([
        publicClient.readContract({ address: VAULT, abi: vaultAbi, functionName: "balanceOf", args: [account] }) as Promise<bigint>,
        publicClient.readContract({ address: VAULT, abi: vaultAbi, functionName: "pendingRewards", args: [account] }) as Promise<bigint>,
        publicClient.readContract({ address: TOKEN, abi: erc20Abi, functionName: "balanceOf", args: [account] }) as Promise<bigint>,
        publicClient.readContract({ address: TOKEN, abi: erc20Abi, functionName: "allowance", args: [account, VAULT] }) as Promise<bigint>,
      ]);
      setStaked(s);
      setPending(p);
      setWalletBal(bal);
      setAllowance(al);
    } catch {
      /* ignore */
    }
  }, [account]);

  useEffect(() => {
    void refresh();
  }, [refresh, refreshKey]);

  const amountWei = (() => {
    try {
      return amount ? parseUnits(amount, decimals) : 0n;
    } catch {
      return 0n;
    }
  })();
  const needsApproval = amountWei > 0n && allowance < amountWei;

  async function deposit() {
    if (!account || amountWei <= 0n) return;
    setBusy(true);
    setMsg("Staking…");
    try {
      const w = walletClient() as unknown as { writeContract: (a: unknown) => Promise<`0x${string}`> };
      if (allowance < amountWei) {
        const a = await w.writeContract({ account, chain: null, address: TOKEN, abi: erc20Abi, functionName: "approve", args: [VAULT, amountWei] });
        await publicClient.waitForTransactionReceipt({ hash: a });
      }
      const h = await w.writeContract({ account, chain: null, address: VAULT, abi: vaultAbi, functionName: "deposit", args: [amountWei, account] });
      await publicClient.waitForTransactionReceipt({ hash: h });
      setMsg(`Staked ✓ ${EXPLORER}/tx/${h}`);
      await refresh();
    } catch (e) {
      setMsg((e as { shortMessage?: string }).shortMessage ?? (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function claim() {
    if (!account) return;
    setBusy(true);
    setMsg("Claiming USDC…");
    try {
      const w = walletClient() as unknown as { writeContract: (a: unknown) => Promise<`0x${string}`> };
      const h = await w.writeContract({ account, chain: null, address: VAULT, abi: vaultAbi, functionName: "claim", args: [] });
      await publicClient.waitForTransactionReceipt({ hash: h });
      setMsg(`Yield claimed ✓ ${EXPLORER}/tx/${h}`);
      await refresh();
    } catch (e) {
      setMsg((e as { shortMessage?: string }).shortMessage ?? (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function withdraw() {
    if (!account || amountWei <= 0n) return;
    setBusy(true);
    setMsg("Unstaking…");
    try {
      const w = walletClient() as unknown as { writeContract: (a: unknown) => Promise<`0x${string}`> };
      const h = await w.writeContract({ account, chain: null, address: VAULT, abi: vaultAbi, functionName: "withdraw", args: [amountWei, account, account] });
      await publicClient.waitForTransactionReceipt({ hash: h });
      setMsg(`Unstaked ✓ ${EXPLORER}/tx/${h}`);
      await refresh();
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
          <span className="flex items-center gap-2">
            <Coins className="h-4 w-4 text-violet-400" /> Staking &amp; Yield
          </span>
          <Badge variant="default">Live</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-4 text-xs">
          <div className="flex items-center justify-between">
            <span className="text-zinc-500">Demo agent token</span>
            <span className="font-mono text-zinc-300">
              {symbol} · {short(TOKEN)}
            </span>
          </div>
          <div className="mt-2 grid grid-cols-2 gap-2">
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-2">
              <div className="text-[10px] text-zinc-500">Total staked</div>
              <div className="font-mono text-zinc-200">
                {Number(formatUnits(totalStaked, decimals)).toLocaleString()} {symbol}
              </div>
            </div>
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-2">
              <div className="text-[10px] text-zinc-500">Yield pool (USDC)</div>
              <div className="font-mono text-emerald-400">{Number(formatUnits(pool, 6)).toFixed(4)}</div>
            </div>
          </div>
          {pool > 0n && totalStaked === 0n && (
            <p className="mt-2 text-[10px] text-amber-400/90">
              First staker captures the seeded yield pool ({Number(formatUnits(pool, 6)).toFixed(4)} USDC).
            </p>
          )}
        </div>

        <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-4">
          <div className="mb-1 flex items-center justify-between text-[11px] text-zinc-500">
            <span>You stake ({symbol})</span>
            {account && <span>wallet {Number(formatUnits(walletBal, decimals)).toLocaleString()}</span>}
          </div>
          <div className="flex items-center gap-2">
            <input
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              className="w-full bg-transparent font-mono text-2xl text-zinc-100 outline-none"
              placeholder="0"
            />
            <button
              onClick={() => setAmount(formatUnits(walletBal, decimals))}
              className="rounded-md border border-zinc-800 bg-zinc-900 px-2 py-1 text-[11px] text-zinc-400 hover:text-zinc-200"
            >
              MAX
            </button>
            <span className="font-mono text-sm text-zinc-400">{symbol}</span>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Button variant="secondary" disabled={!account || busy || amountWei <= 0n} onClick={withdraw}>
            <Wallet className="h-3.5 w-3.5" /> Unstake
          </Button>
          {needsApproval ? (
            <Button disabled={!account || busy} onClick={deposit}>
              <Lock className="h-3.5 w-3.5" /> Approve + Stake
            </Button>
          ) : (
            <Button disabled={!account || busy || amountWei <= 0n} onClick={deposit}>
              <Lock className="h-3.5 w-3.5" /> Stake
            </Button>
          )}
        </div>

        <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-4">
          <div className="flex items-center justify-between text-xs">
            <span className="text-zinc-500">Your staked</span>
            <span className="font-mono text-zinc-200">
              {Number(formatUnits(staked, decimals)).toLocaleString()} {symbol}
            </span>
          </div>
          <div className="mt-1 flex items-center justify-between text-xs">
            <span className="text-zinc-500">Claimable USDC</span>
            <span className="font-mono text-emerald-400">{Number(formatUnits(pending, 6)).toFixed(6)}</span>
          </div>
          <Button className="mt-3 w-full" disabled={!account || busy || pending <= 0n} onClick={claim}>
            <Gift className="h-3.5 w-3.5" /> Claim USDC
          </Button>
        </div>

        <p className="text-center text-[10px] text-zinc-600">
          Demo agent · ERC-4626-style vault · the agent&apos;s revenue (70%) streams to stakers as USDC.
        </p>
      </CardContent>
    </Card>
  );
}
