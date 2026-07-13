import type { LucideIcon } from "lucide-react";

import { Card } from "@/components/ui/card";
import { formatValue } from "@/lib/utils";

/** A single KPI tile for the dashboard. */
export function KpiCard({
  label,
  value,
  format = "number",
  icon: Icon,
}: {
  label: string;
  value: number | string;
  format?: string;
  icon?: LucideIcon;
}) {
  return (
    <Card className="p-5">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-muted-foreground">{label}</p>
          <p className="mt-2 text-2xl font-bold tracking-tight">{formatValue(value, format)}</p>
        </div>
        {Icon && (
          <div className="flex size-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Icon className="size-4" />
          </div>
        )}
      </div>
    </Card>
  );
}
