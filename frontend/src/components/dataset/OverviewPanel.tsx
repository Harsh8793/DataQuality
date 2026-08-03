import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, RefreshCw, Sparkles } from "lucide-react";
import { useState } from "react";

import { CollapsibleCard } from "@/components/common/CollapsibleCard";
import { DataTable } from "@/components/common/DataTable";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Skeleton, Spinner } from "@/components/ui/misc";
import { useDataset, useDatasetPreview, useProfile } from "@/hooks/useDatasets";
import { cn } from "@/lib/utils";
import { aiService } from "@/services/aiService";

/** AI-generated executive summary shown at the top of the Overview tab. */
function DataStoryCard({ datasetId }: { datasetId: number }) {
  const qc = useQueryClient();
  const [regenerating, setRegenerating] = useState(false);
  const { data, isLoading } = useQuery({
    queryKey: ["dataset", datasetId, "story"],
    queryFn: () => aiService.story(datasetId),
    staleTime: Infinity,
  });

  const regenerate = async () => {
    setRegenerating(true);
    try {
      const fresh = await aiService.story(datasetId, true);
      qc.setQueryData(["dataset", datasetId, "story"], fresh);
    } finally {
      setRegenerating(false);
    }
  };

  return (
    <Card className="border-accent/30 bg-gradient-to-br from-accent/5 to-primary/5 p-4">
      <div className="flex items-start gap-3">
        <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-accent/15 text-accent">
          <Sparkles className="size-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold">Data story</p>
            <button
              onClick={regenerate}
              className="flex items-center gap-1 rounded-md px-2 py-0.5 text-xs text-muted-foreground transition-colors hover:text-primary"
              title="Regenerate with AI"
              disabled={regenerating}
            >
              <RefreshCw className={`size-3 ${regenerating ? "animate-spin" : ""}`} /> Regenerate
            </button>
          </div>
          {isLoading ? (
            <p className="mt-1 animate-pulse text-sm text-muted-foreground">Reading your data…</p>
          ) : (
            /* whitespace-pre-line keeps the one-bullet-per-line breaks the model returns. */
            <p className="mt-1 whitespace-pre-line text-sm leading-relaxed text-muted-foreground">
              {data?.story}
            </p>
          )}
        </div>
      </div>
    </Card>
  );
}

/** Placeholder table shown while the column profile is being built.
 *
 * Mirrors the real table's columns so the layout doesn't jump when data lands,
 * and says what is actually happening — profiling is fast, the AI descriptions
 * are what take the time on wide datasets.
 */
function ColumnProfileSkeleton({ columns }: { columns?: number }) {
  const rows = Math.min(columns || 6, 8);
  return (
    <div className="rounded-lg border border-border">
      <div className="flex items-center gap-2 border-b border-border bg-secondary/50 px-3 py-2.5">
        <Loader2 className="size-4 shrink-0 animate-spin text-primary" />
        <p className="text-sm">
          Profiling {columns ? `${columns} columns` : "your columns"} and writing AI descriptions…
          <span className="ml-1 text-muted-foreground">
            wide datasets take a few seconds — the rest of the page is ready to explore.
          </span>
        </p>
      </div>
      <div className="divide-y divide-border">
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="flex items-center gap-3 px-3 py-2.5">
            <Skeleton className="h-4 w-6 shrink-0" />
            <Skeleton className="h-4 w-32 shrink-0" />
            <Skeleton className="h-4 w-20 shrink-0" />
            <Skeleton className="h-4 w-12 shrink-0" />
            <Skeleton className="h-4 w-14 shrink-0" />
            <Skeleton className="h-4 flex-1" />
          </div>
        ))}
      </div>
    </div>
  );
}

/** Dataset overview: summary metadata, column profile and a data preview. */
export function OverviewPanel({ datasetId }: { datasetId: number }) {
  const { data: ds } = useDataset(datasetId);
  const { data: preview, isLoading } = useDatasetPreview(datasetId);
  const { data: profile, isLoading: profileLoading } = useProfile(datasetId);

  if (!ds) return <Spinner />;

  const stats = [
    { label: "Rows × Columns", value: `${ds.row_count.toLocaleString()} × ${ds.col_count}` },
    { label: "Format", value: ds.file_format.toUpperCase() },
    { label: "Encoding", value: ds.encoding ?? "—" },
    { label: "Delimiter", value: ds.delimiter ? JSON.stringify(ds.delimiter) : "—" },
  ];

  return (
    <div className="space-y-4">
      <DataStoryCard datasetId={datasetId} />

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {stats.map((s) => (
          <Card key={s.label} className="p-4 text-center">
            <p className="text-xs text-muted-foreground">{s.label}</p>
            <p className="mt-1 text-lg font-semibold capitalize">{s.value}</p>
          </Card>
        ))}
      </div>

      {/* Kept mounted while loading — on wide tables the AI descriptions take a
          few seconds, and a card that vanishes reads as a broken page. */}
      {profileLoading ? (
        <CollapsibleCard title="Column profile">
          <ColumnProfileSkeleton columns={ds.col_count} />
        </CollapsibleCard>
      ) : profile && profile.length > 0 ? (
        <CollapsibleCard title={`Column profile (${profile.length})`}>
          <div className="overflow-auto rounded-lg border border-border" style={{ maxHeight: 420 }}>
            <table className="w-full border-collapse text-sm">
              <thead className="sticky top-0 z-10 bg-secondary">
                <tr className="text-center text-secondary-foreground">
                  <th className="w-10 px-3 py-2 font-semibold">#</th>
                  <th className="px-3 py-2 font-semibold">Column</th>
                  <th className="px-3 py-2 font-semibold">Type</th>
                  <th className="whitespace-nowrap px-3 py-2 font-semibold">Null %</th>
                  <th className="whitespace-nowrap px-3 py-2 font-semibold">Distinct</th>
                  <th className="px-3 py-2 font-semibold">
                    <span className="inline-flex items-center gap-1">
                      <Sparkles className="size-3 text-accent" /> Description
                    </span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {profile.map((c, i) => (
                  <tr
                    key={c.name}
                    className={cn("border-t border-border text-center", i % 2 ? "bg-card" : "bg-background")}
                  >
                    <td className="px-3 py-1.5 text-xs text-muted-foreground">{i + 1}</td>
                    <td className="px-3 py-1.5">
                      <div className="flex items-center justify-center gap-2">
                        <span className="font-medium">{c.name}</span>
                        {c.is_pii && <Badge variant="critical">PII</Badge>}
                      </div>
                    </td>
                    <td className="px-3 py-1.5">
                      <Badge variant="secondary">{c.semantic_type}</Badge>
                    </td>
                    {/* Colour-code completeness so problem columns stand out at a glance. */}
                    <td
                      className={cn(
                        "px-3 py-1.5 tabular-nums",
                        c.null_pct >= 20
                          ? "font-semibold text-destructive"
                          : c.null_pct > 0
                            ? "text-amber-400"
                            : "text-muted-foreground"
                      )}
                    >
                      {c.null_pct}%
                    </td>
                    <td className="px-3 py-1.5 tabular-nums text-muted-foreground">
                      {c.distinct_count.toLocaleString()}
                    </td>
                    {/* Written by the governance agent; empty until that has run. */}
                    <td
                      className="max-w-[280px] truncate px-3 py-1.5 text-muted-foreground"
                      title={c.description ?? undefined}
                    >
                      {c.description ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CollapsibleCard>
      ) : null}

      <CollapsibleCard title={`Data preview${preview ? ` (${preview.total_rows.toLocaleString()} rows)` : ""}`}>
        {isLoading ? <Spinner /> : preview ? <DataTable columns={preview.columns} rows={preview.rows} /> : null}
      </CollapsibleCard>
    </div>
  );
}
