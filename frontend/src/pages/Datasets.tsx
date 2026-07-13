import { Database, GitCompareArrows, Trash2, Upload } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { ApprovalBadge } from "@/components/common/ApprovalBadge";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { CompareDatasetsModal } from "@/components/dataset/CompareDatasetsModal";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState, Spinner } from "@/components/ui/misc";
import { useDatasets, useDeleteDataset } from "@/hooks/useDatasets";
import { formatBytes, formatDate } from "@/lib/utils";
import type { DatasetSummary } from "@/types/models";

/** All datasets list page. */
export function Datasets() {
  const { data, isLoading } = useDatasets(50);
  const datasets = data?.items ?? [];
  const del = useDeleteDataset();
  const [pending, setPending] = useState<DatasetSummary | null>(null);
  const [compareOpen, setCompareOpen] = useState(false);

  const confirmDelete = () => {
    if (pending) del.mutate(pending.id, { onSettled: () => setPending(null) });
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Datasets</h1>
          <p className="text-muted-foreground">{datasets.length} dataset(s)</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setCompareOpen(true)} disabled={datasets.length < 2}>
            <GitCompareArrows className="size-4" /> Compare
          </Button>
          <Link to="/upload">
            <Button variant="gradient">
              <Upload className="size-4" /> Upload
            </Button>
          </Link>
        </div>
      </div>

      {isLoading ? (
        <Spinner label="Loading…" />
      ) : datasets.length === 0 ? (
        <EmptyState icon={<Database className="size-8" />} title="No datasets" description="Upload one to get started." />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {datasets.map((d) => (
            <Card key={d.id} className="h-full transition-colors hover:border-primary/50">
              <CardContent className="pt-5">
                <div className="mb-3 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="flex size-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
                      <Database className="size-4" />
                    </div>
                    <Badge variant="secondary" className="font-mono">#{d.id}</Badge>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <ApprovalBadge status={d.approval_status} />
                    {d.is_cleaned && <Badge variant="success">cleaned</Badge>}
                    <Badge variant="outline">{d.file_format.toUpperCase()}</Badge>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="size-8 text-muted-foreground hover:text-destructive"
                      title="Delete dataset"
                      onClick={() => setPending(d)}
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  </div>
                </div>
                <Link to={`/datasets/${d.id}`} className="block">
                  <p className="truncate font-semibold hover:text-primary">{d.name}</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {d.row_count.toLocaleString()} rows · {d.col_count} cols · {formatBytes(d.file_size_bytes)}
                  </p>
                  <p className="mt-2 text-xs text-muted-foreground">{formatDate(d.created_at)}</p>
                </Link>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <CompareDatasetsModal open={compareOpen} datasets={datasets} onClose={() => setCompareOpen(false)} />

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
