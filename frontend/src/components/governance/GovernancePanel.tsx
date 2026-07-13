import { Database, Layers, Lock, ShieldCheck } from "lucide-react";

import { CollapsibleCard } from "@/components/common/CollapsibleCard";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/misc";
import { useGovernance } from "@/hooks/useDatasets";

const TIER_STYLE: Record<string, string> = {
  bronze: "bg-orange-500/15 text-orange-400",
  silver: "bg-slate-300/15 text-slate-300",
  gold: "bg-amber-400/15 text-amber-300",
};

/** Governance classification, PII detection, ingestion tier and metadata. */
export function GovernancePanel({ datasetId }: { datasetId: number }) {
  const { data, isLoading } = useGovernance(datasetId);

  if (isLoading) return <Spinner label="Classifying data governance…" />;
  if (!data) return null;

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Lock className="size-4 text-destructive" /> Classification
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Badge variant="critical" className="text-sm uppercase">{data.classification}</Badge>
            {data.rationale && <p className="mt-2 text-xs text-muted-foreground">{data.rationale}</p>}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ShieldCheck className="size-4 text-primary" /> PII columns
            </CardTitle>
          </CardHeader>
          <CardContent>
            {data.pii_columns.length ? (
              <div className="flex flex-wrap gap-1.5">
                {data.pii_columns.map((c) => (
                  <Badge key={c} variant="high">{c}</Badge>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No PII detected.</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Layers className="size-4 text-accent" /> Ingestion tier
            </CardTitle>
          </CardHeader>
          <CardContent>
            <span className={`inline-flex rounded-full px-3 py-1 text-sm font-semibold uppercase ${TIER_STYLE[data.ingestion_tier] ?? ""}`}>
              {data.ingestion_tier}
            </span>
            {data.tier_rationale && <p className="mt-2 text-xs text-muted-foreground">{data.tier_rationale}</p>}
          </CardContent>
        </Card>
      </div>

      {data.column_metadata.length > 0 && (
        <CollapsibleCard
          title={
            <span className="flex items-center gap-2">
              <Database className="size-4" /> Business metadata ({data.column_metadata.length})
            </span>
          }
        >
          <div className="overflow-auto rounded-lg border border-border">
              <table className="w-full text-sm">
                <thead className="bg-secondary">
                  <tr>
                    {["Column", "Business name", "Description", "Sensitivity", "PII"].map((h) => (
                      <th key={h} className="px-3 py-2 text-left font-semibold">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.column_metadata.map((m, i) => (
                    <tr key={i} className="border-t border-border">
                      <td className="px-3 py-2 font-medium">{String(m.name ?? "")}</td>
                      <td className="px-3 py-2 text-muted-foreground">{String(m.business_name ?? "—")}</td>
                      <td className="px-3 py-2 text-muted-foreground">{String(m.description ?? "—")}</td>
                      <td className="px-3 py-2">
                        <Badge variant="secondary">{String(m.sensitivity ?? "internal")}</Badge>
                      </td>
                      <td className="px-3 py-2">{m.is_pii ? <Badge variant="critical">Yes</Badge> : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
        </CollapsibleCard>
      )}
    </div>
  );
}
