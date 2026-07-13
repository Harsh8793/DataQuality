import { useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw, Sparkles } from "lucide-react";
import { useState } from "react";

import { CollapsibleCard } from "@/components/common/CollapsibleCard";
import { DataTable } from "@/components/common/DataTable";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Spinner } from "@/components/ui/misc";
import { useDataset, useDatasetPreview, useProfile } from "@/hooks/useDatasets";
import { formatBytes } from "@/lib/utils";
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
            <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{data?.story}</p>
          )}
        </div>
      </div>
    </Card>
  );
}

/** Dataset overview: summary metadata, column profile and a data preview. */
export function OverviewPanel({ datasetId }: { datasetId: number }) {
  const { data: ds } = useDataset(datasetId);
  const { data: preview, isLoading } = useDatasetPreview(datasetId);
  const { data: profile } = useProfile(datasetId);

  if (!ds) return <Spinner />;

  const stats = [
    { label: "Rows", value: ds.row_count.toLocaleString() },
    { label: "Columns", value: ds.col_count },
    { label: "Format", value: ds.file_format.toUpperCase() },
    { label: "Encoding", value: ds.encoding ?? "—" },
    { label: "Delimiter", value: ds.delimiter ? JSON.stringify(ds.delimiter) : "—" },
    { label: "File size", value: formatBytes(ds.file_size_bytes) },
    { label: "In memory", value: formatBytes(ds.memory_bytes) },
    { label: "Status", value: ds.status },
  ];

  return (
    <div className="space-y-4">
      <DataStoryCard datasetId={datasetId} />

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {stats.map((s) => (
          <Card key={s.label} className="p-4">
            <p className="text-xs text-muted-foreground">{s.label}</p>
            <p className="mt-1 text-lg font-semibold capitalize">{s.value}</p>
          </Card>
        ))}
      </div>

      {profile && profile.length > 0 && (
        <CollapsibleCard title={`Column profile (${profile.length})`}>
          <div className="flex flex-wrap gap-2">
            {profile.map((c) => (
              <div key={c.name} className="rounded-lg border border-border bg-background px-3 py-2">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">{c.name}</span>
                  <Badge variant="secondary">{c.semantic_type}</Badge>
                  {c.is_pii && <Badge variant="critical">PII</Badge>}
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  {c.null_pct}% null · {c.distinct_count} distinct
                </p>
              </div>
            ))}
          </div>
        </CollapsibleCard>
      )}

      <CollapsibleCard title={`Data preview${preview ? ` (${preview.total_rows.toLocaleString()} rows)` : ""}`}>
        {isLoading ? <Spinner /> : preview ? <DataTable columns={preview.columns} rows={preview.rows} /> : null}
      </CollapsibleCard>
    </div>
  );
}
