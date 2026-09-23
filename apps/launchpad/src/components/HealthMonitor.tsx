import { useEffect, useState } from "react";
import { Activity, Server, Zap } from "lucide-react";
import { publicClient } from "../arc";
import { Badge } from "./ui/badge";

/** Live status badges: Arc RPC (real ping), Keeper engine state, and network finality. */
export function HealthMonitor() {
  const [rpc, setRpc] = useState<{ ok: boolean; ms: number | null }>({ ok: false, ms: null });

  useEffect(() => {
    let alive = true;
    const ping = async () => {
      const t0 = performance.now();
      try {
        const chainId = await publicClient.getChainId();
        const ms = Math.round(performance.now() - t0);
        if (alive) setRpc({ ok: chainId === 5042, ms });
      } catch {
        if (alive) setRpc({ ok: false, ms: null });
      }
    };
    void ping();
    const id = setInterval(ping, 15000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  return (
    <div className="mb-5 flex flex-wrap items-center gap-2">
      <Badge variant={rpc.ok ? "success" : "warning"}>
        <Server className="h-3 w-3" />
        RPC Mainnet: {rpc.ok ? `Connected · ${rpc.ms}ms` : "Disconnected"}
      </Badge>
      <Badge variant="violet">
        <Activity className="h-3 w-3" />
        Keeper Agent Engine: Standby · dry-run
      </Badge>
      <Badge variant="muted">
        <Zap className="h-3 w-3" />
        Network Finality: ~0.48s BFT
      </Badge>
    </div>
  );
}
