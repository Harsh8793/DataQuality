import { useMutation } from "@tanstack/react-query";
import { ArrowRight, GitCompareArrows, Sparkles } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Modal } from "@/components/common/Modal";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/misc";
import { aiService } from "@/services/aiService";
import type { CompareResult, DatasetSummary } from "@/types/models";

interface Props {
  open: boolean;
  datasets: DatasetSummary[];
  onClose: () => void;
}

/** Pick two datasets and get an AI-narrated schema + distribution comparison. */
export function CompareDatasetsModal({ open, datasets, onClose }: Props) {
  const [leftId, setLeftId] = useState<number | "">("");
  const [rightId, setRightId] = useState<number | "">("");
  const [result, setResult] = useState<CompareResult | null>(null);

  const compare = useMutation({
    mutationFn: () => aiService.compare(Number(leftId), Number(rightId)),
    onSuccess: setResult,
    onError: (e: Error) => toast.error(e.message),
  });

  const close = () => {
    setResult(null);
    onClose();
  };

  const selectCls =
    "w-full rounded-lg border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring";

  return (
    <Modal
      open={open}
      onClose={close}
      wide
      title="Compare datasets"
      description="AI narrates what changed between two files: schema drift, row deltas and distribution shifts."
    >
      <div className="space-y-4">
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-48 flex-1">
            <label className="mb-1 block text-xs font-medium text-muted-foreground">Baseline (before)</label>
            <select className={selectCls} value={leftId} onChange={(e) => setLeftId(Number(e.target.value) || "")}>
              <option value="">Select a dataset…</option>
              {datasets.map((d) => (
                <option key={d.id} value={d.id} disabled={d.id === rightId}>
                  #{d.id} · {d.name}
                </option>
              ))}
            </select>
          </div>
          <ArrowRight className="mb-2.5 size-4 shrink-0 text-muted-foreground" />
          <div className="min-w-48 flex-1">
            <label className="mb-1 block text-xs font-medium text-muted-foreground">Comparison (after)</label>
            <select className={selectCls} value={rightId} onChange={(e) => setRightId(Number(e.target.value) || "")}>
              <option value="">Select a dataset…</option>
              {datasets.map((d) => (
                <option key={d.id} value={d.id} disabled={d.id === leftId}>
                  #{d.id} · {d.name}
                </option>
              ))}
            </select>
          </div>
          <Button
            variant="gradient"
            onClick={() => compare.mutate()}
            disabled={!leftId || !rightId || leftId === rightId || compare.isPending}
          >
            <GitCompareArrows className="size-4" /> Compare
          </Button>
        </div>

        {compare.isPending && <Spinner label="Comparing datasets…" />}

        {result && !compare.isPending && (
          <div className="space-y-4">
            {/* AI narrative */}
            <div className="rounded-lg border border-accent/30 bg-accent/5 p-4">
              <div className="mb-1 flex items-center gap-2 text-sm font-semibold">
                <Sparkles className="size-4 text-accent" /> AI summary
              </div>
              <p className="text-sm leading-relaxed text-muted-foreground">{result.narrative}</p>
            </div>

            {/* Headline numbers */}
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-lg border border-border p-3">
                <p className="text-xs text-muted-foreground">Rows</p>
                <p className="text-sm font-semibold">
                  {result.left_rows.toLocaleString()} → {result.right_rows.toLocaleString()}{" "}
                  <span className={result.right_rows - result.left_rows >= 0 ? "text-success" : "text-destructive"}>
                    ({result.right_rows - result.left_rows >= 0 ? "+" : ""}
                    {(result.right_rows - result.left_rows).toLocaleString()})
                  </span>
                </p>
              </div>
              <div className="rounded-lg border border-border p-3">
                <p className="text-xs text-muted-foreground">Columns</p>
                <p className="text-sm font-semibold">
                  {result.left_cols} → {result.right_cols} · {result.common_columns} shared
                </p>
              </div>
              <div className="rounded-lg border border-border p-3">
                <p className="text-xs text-muted-foreground">Schema drift</p>
                <p className="text-sm font-semibold">
                  {result.added_columns.length} added · {result.removed_columns.length} removed
                </p>
              </div>
            </div>

            {(result.added_columns.length > 0 || result.removed_columns.length > 0) && (
              <div className="flex flex-wrap gap-1.5">
                {result.added_columns.map((c) => (
                  <Badge key={`a-${c}`} variant="success">+ {c}</Badge>
                ))}
                {result.removed_columns.map((c) => (
                  <Badge key={`r-${c}`} variant="critical">− {c}</Badge>
                ))}
              </div>
            )}

            {result.column_shifts.length > 0 && (
              <div className="overflow-auto rounded-lg border border-border">
                <table className="w-full text-sm">
                  <thead className="bg-secondary">
                    <tr>
                      {["Column", "Avg (before)", "Avg (after)", "Change", "Null % (before)", "Null % (after)"].map((h) => (
                        <th key={h} className="px-3 py-2 text-left font-semibold">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {result.column_shifts.map((s) => (
                      <tr key={s.column} className="border-t border-border">
                        <td className="px-3 py-2 font-medium">{s.column}</td>
                        <td className="px-3 py-2 text-muted-foreground">{s.left_mean ?? "—"}</td>
                        <td className="px-3 py-2 text-muted-foreground">{s.right_mean ?? "—"}</td>
                        <td className="px-3 py-2">
                          {s.mean_change_pct == null ? (
                            "—"
                          ) : (
                            <span className={Math.abs(s.mean_change_pct) >= 5 ? "font-semibold text-warning" : ""}>
                              {s.mean_change_pct > 0 ? "+" : ""}
                              {s.mean_change_pct}%
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-muted-foreground">{s.left_null_pct}%</td>
                        <td className="px-3 py-2 text-muted-foreground">{s.right_null_pct}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </Modal>
  );
}
