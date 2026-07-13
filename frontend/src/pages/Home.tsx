import { Database, FileCheck2, Layers, Sparkles, Trash2, Upload } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { KpiCard } from "@/components/charts/KpiCard";
import { ApprovalBadge } from "@/components/common/ApprovalBadge";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EmptyState, Spinner } from "@/components/ui/misc";
import { useAuth } from "@/contexts/AuthContext";
import { useDatasets, useDeleteDataset } from "@/hooks/useDatasets";
import { formatDate } from "@/lib/utils";
import type { DatasetSummary } from "@/types/models";

/** Landing dashboard: KPIs, quick actions and recent datasets. */
export function Home() {
  const { user } = useAuth();
  const { data, isLoading } = useDatasets();
  const del = useDeleteDataset();
  const [pending, setPending] = useState<DatasetSummary | null>(null);

  const confirmDelete = () => {
    if (pending) del.mutate(pending.id, { onSettled: () => setPending(null) });
  };
  const datasets = data?.items ?? [];
  const cleaned = datasets.filter((d) => d.is_cleaned).length;
  const totalRows = datasets.reduce((s, d) => s + d.row_count, 0);

  return (
    <div className="space-y-6">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-2xl font-bold">Welcome back, {user?.name?.split(" ")[0]} 👋</h1>
          <p className="text-muted-foreground">Your enterprise data quality command center.</p>
        </div>
        <Link to="/upload">
          <Button variant="gradient">
            <Upload className="size-4" /> Upload dataset
          </Button>
        </Link>
      </div>

      <div className="card-grid">
        <KpiCard label="Datasets" value={datasets.length} icon={Database} />
        <KpiCard label="Total Rows" value={totalRows} icon={Layers} />
        <KpiCard label="Cleaned" value={cleaned} icon={FileCheck2} />
        <KpiCard label="AI Copilot" value={"Active"} icon={Sparkles} format="text" />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Recent datasets</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <Spinner label="Loading datasets…" />
          ) : datasets.length === 0 ? (
            <EmptyState
              icon={<Sparkles className="size-8 text-accent" />}
              title={`Let's get started, ${user?.name?.split(" ")[0] ?? "there"}`}
              description={`Use the "Upload dataset" button in the top-right to add a CSV, Excel or JSON file. DataPilot AI will profile it, score its quality, and unlock chat, dashboards and governance — all in a few seconds.`}
            />
          ) : (
            <div className="divide-y divide-border">
              {datasets.slice(0, 6).map((d) => (
                <div key={d.id} className="flex items-center justify-between py-3">
                  <Link to={`/datasets/${d.id}`} className="flex min-w-0 flex-1 items-center gap-3">
                    <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                      <Database className="size-4" />
                    </div>
                    <div className="min-w-0">
                      <p className="truncate font-medium">
                        <span className="mr-2 font-mono text-xs text-muted-foreground">#{d.id}</span>
                        {d.name}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {d.row_count.toLocaleString()} rows · {d.col_count} cols · {formatDate(d.created_at)}
                      </p>
                    </div>
                  </Link>
                  <div className="flex shrink-0 items-center gap-2 pl-3">
                    <ApprovalBadge status={d.approval_status} />
                    {d.is_cleaned && <Badge variant="success">cleaned</Badge>}
                    <Badge variant="outline">{d.file_format.toUpperCase()}</Badge>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="text-muted-foreground hover:text-destructive"
                      title="Delete dataset"
                      onClick={() => setPending(d)}
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <ConfirmDialog
        open={!!pending}
        destructive
        title={`Delete "${pending?.name ?? ""}"?`}
        description="This permanently removes the dataset and all its analysis, chats and reports from the database. This cannot be undone."
        confirmLabel="Delete"
        loading={del.isPending}
        onConfirm={confirmDelete}
        onCancel={() => setPending(null)}
      />
    </div>
  );
}
