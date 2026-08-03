import type { LucideIcon } from "lucide-react";

import { Card } from "@/components/ui/card";
import { cn, formatValue } from "@/lib/utils";

/** Colour treatments for the icon chip, used to signal health on status tiles. */
export type KpiTone = "default" | "success" | "warning" | "danger" | "muted";

const toneStyles: Record<KpiTone, string> = {
  default: "bg-primary/10 text-primary",
  success: "bg-success/15 text-success",
  warning: "bg-amber-500/15 text-amber-400",
  danger: "bg-destructive/15 text-destructive",
  muted: "bg-secondary text-muted-foreground",
};

/** A single KPI tile for the dashboard. */
export function KpiCard({
  label,
  value,
  format = "number",
  icon: Icon,
  tone = "default",
  hint,
}: {
  label: string;
  value: number | string;
  format?: string;
  icon?: LucideIcon;
  /** Icon chip colour — use to signal status on non-numeric tiles. */
  tone?: KpiTone;
  /** Optional sub-line under the value (also shown as a tooltip). */
  hint?: string;
}) {
  return (
    <Card className="p-5" title={hint}>
      <div className="flex items-start justify-between">
        <div className="min-w-0">
          <p className="text-sm text-muted-foreground">{label}</p>
          <p className="mt-2 text-2xl font-bold tracking-tight">{formatValue(value, format)}</p>
          {hint && <p className="mt-1 truncate text-xs text-muted-foreground">{hint}</p>}
        </div>
        {Icon && (
          <div className={cn("flex size-9 shrink-0 items-center justify-center rounded-lg", toneStyles[tone])}>
            <Icon className="size-4" />
          </div>
        )}
      </div>
    </Card>
  );
}
