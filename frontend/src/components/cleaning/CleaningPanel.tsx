import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2, Download, Sparkles, Wand2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { DataTable } from "@/components/common/DataTable";
import { Modal } from "@/components/common/Modal";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/misc";
import { useClean, useCleanResult, useDataset } from "@/hooks/useDatasets";
import { analysisService } from "@/services/analysisService";
import type { CleaningOp, CompareMetric } from "@/types/models";

/** One-click cleaning with a persisted before/after comparison + download. */
export function CleaningPanel({ datasetId }: { datasetId: number }) {
  const clean = useClean(datasetId);
  const existing = useCleanResult(datasetId);
  const { data: ds } = useDataset(datasetId);
  const [downloading, setDownloading] = useState(false);

  // Prefer a fresh run's result, else the persisted one (survives navigation).
  const result = clean.data ?? existing.data ?? null;

  const download = async () => {
    setDownloading(true);
    try {
      await analysisService.downloadCleanComparison(datasetId, `${ds?.name ?? "dataset"}_comparison.xlsx`);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Wand2 className="size-4 text-accent" /> One-click AI cleaning
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="mb-4 text-sm text-muted-foreground">
            Automatically trims whitespace, removes duplicates, quarantines invalid values, fills missing data,
            standardizes categories, normalizes countries/genders, converts types and caps outliers.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button
              variant={result ? "secondary" : "gradient"}
              onClick={() => clean.mutate()}
              disabled={clean.isPending || !!result}
            >
              {result ? <CheckCircle2 className="size-4 text-success" /> : <Sparkles className="size-4" />}
              {clean.isPending ? "Cleaning…" : result ? "Cleaned" : "Run cleaning"}
            </Button>
            {result && (
              <Button variant="outline" onClick={download} disabled={downloading}>
                <Download className="size-4" />
                {downloading ? "Preparing…" : "Download comparison (Excel)"}
              </Button>
            )}
          </div>
          {result && (
            <p className="mt-2 text-xs text-muted-foreground">
              This dataset has already been cleaned — a cleaned copy is saved in your Datasets.
            </p>
          )}
          {result && (
            <p className="mt-2 text-xs text-muted-foreground">
              The Excel workbook contains two sheets: <span className="font-medium">Original</span> and{" "}
              <span className="font-medium">Cleaned</span>.
            </p>
          )}
        </CardContent>
      </Card>

      {result && (
        <>
          <Card>
            <CardHeader>
              <CardTitle>Before → After</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {result.comparison.map((m) => (
                  <CompareTile key={m.label} metric={m} />
                ))}
              </div>
              {result.comparison.some((m) => m.label === "Avg Null %" && m.after > m.before) && (
                <p className="mt-3 text-xs text-muted-foreground">
                  Note: Avg Null % can rise after cleaning — invalid values (e.g. malformed emails)
                  are quarantined to null rather than left to corrupt downstream use, and
                  contact/ID fields are never guess-filled.
                </p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Operations applied ({result.operations.length})</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {result.operations.map((op, i) => (
                <OperationRow key={i} op={op} opIndex={i} datasetId={datasetId} />
              ))}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

function OperationRow({ op, opIndex, datasetId }: { op: CleaningOp; opIndex: number; datasetId: number }) {
  const [open, setOpen] = useState(false);
  const hasRows = (op.rows?.length ?? 0) > 0;
  const affected = useQuery({
    queryKey: ["clean-affected", datasetId, opIndex],
    queryFn: () => analysisService.cleanOpAffected(datasetId, opIndex),
    enabled: open && hasRows,
  });

  return (
    <div className="flex items-center gap-3 rounded-md bg-secondary/40 px-3 py-2 text-sm">
      <CheckCircle2 className="size-4 text-success" />
      <span className="font-medium">{op.detail || op.op}</span>
      {op.column && <Badge variant="outline">{op.column}</Badge>}
      {hasRows ? (
        <button
          onClick={() => setOpen(true)}
          className="ml-auto rounded-md border border-border px-2 py-0.5 text-xs text-muted-foreground transition-colors hover:border-primary/50 hover:text-primary"
          title="View the original rows this operation changed"
        >
          {op.rows_affected} rows →
        </button>
      ) : (
        <span className="ml-auto text-xs text-muted-foreground">{op.rows_affected} rows</span>
      )}

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        wide
        title={`Rows changed — ${op.detail || op.op}`}
        description={
          op.column
            ? `Column "${op.column}" · ${op.rows_affected} rows (original values shown)`
            : `${op.rows_affected} rows (original values shown)`
        }
      >
        {affected.isLoading ? (
          <Spinner label="Loading affected rows…" />
        ) : affected.data && affected.data.rows.length > 0 ? (
          <>
            {affected.data.total_rows > affected.data.rows.length && (
              <p className="mb-2 text-xs text-muted-foreground">
                Showing first {affected.data.rows.length} of {affected.data.total_rows} affected rows.
              </p>
            )}
            <DataTable columns={affected.data.columns} rows={affected.data.rows} maxHeight={480} />
          </>
        ) : (
          <p className="text-sm text-muted-foreground">No rows to display for this operation.</p>
        )}
      </Modal>
    </div>
  );
}

function CompareTile({ metric }: { metric: CompareMetric }) {
  const improved =
    metric.label === "Quality Score" ? metric.after > metric.before : metric.after <= metric.before;
  return (
    <div className="rounded-lg border border-border bg-background p-4">
      <p className="text-xs text-muted-foreground">{metric.label}</p>
      <div className="mt-2 flex items-center gap-2">
        <span className="text-lg font-semibold text-muted-foreground">{metric.before}</span>
        <ArrowRight className="size-4 text-muted-foreground" />
        <span className={`text-lg font-bold ${improved ? "text-success" : "text-foreground"}`}>{metric.after}</span>
      </div>
    </div>
  );
}
