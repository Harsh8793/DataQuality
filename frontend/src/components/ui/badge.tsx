import { cva, type VariantProps } from "class-variance-authority";
import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors",
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary/15 text-primary",
        secondary: "border-transparent bg-secondary text-secondary-foreground",
        outline: "border-border text-foreground",
        critical: "border-transparent bg-destructive/15 text-destructive",
        high: "border-transparent bg-orange-500/15 text-orange-400",
        medium: "border-transparent bg-amber-500/15 text-amber-400",
        low: "border-transparent bg-blue-500/15 text-blue-400",
        info: "border-transparent bg-slate-500/15 text-slate-400",
        success: "border-transparent bg-success/15 text-success",
      },
    },
    defaultVariants: { variant: "default" },
  }
);

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
