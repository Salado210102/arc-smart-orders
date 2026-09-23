import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] font-medium",
  {
    variants: {
      variant: {
        default: "border-zinc-700 bg-zinc-800 text-zinc-200",
        success: "border-emerald-800/60 bg-emerald-950/40 text-emerald-400",
        violet: "border-violet-800/60 bg-violet-950/40 text-violet-300",
        warning: "border-amber-800/60 bg-amber-950/40 text-amber-400",
        muted: "border-zinc-800 bg-zinc-900 text-zinc-500",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

export const Badge = ({ className, variant, ...props }: BadgeProps) => (
  <span className={cn(badgeVariants({ variant }), className)} {...props} />
);
