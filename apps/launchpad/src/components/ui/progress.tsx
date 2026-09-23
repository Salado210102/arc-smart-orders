import { cn } from "../../lib/utils";

export function Progress({ value = 0, className }: { value?: number; className?: string }) {
  const v = Math.min(100, Math.max(0, value));
  return (
    <div className={cn("h-2 w-full overflow-hidden rounded-full bg-zinc-800", className)}>
      <div
        className="h-full rounded-full bg-gradient-to-r from-violet-500 to-emerald-400 transition-all"
        style={{ width: `${v}%` }}
      />
    </div>
  );
}
