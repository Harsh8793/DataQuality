import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Filter, History, Pencil, RotateCcw, Save, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { CollapsibleCard } from "@/components/common/CollapsibleCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/misc";
import { editService, type RowFilter } from "@/services/editService";
import { formatDate } from "@/lib/utils";

const PAGE_SIZE = 100;
const NULL_LABEL = "(null)";

const OPERATORS: { value: string; label: string; needsValue: boolean }[] = [
  { value: "contains", label: "contains", needsValue: true },
  { value: "eq", label: "equals", needsValue: true },
  { value: "neq", label: "not equals", needsValue: true },
  { value: "gt", label: ">", needsValue: true },
  { value: "gte", label: "≥", needsValue: true },
  { value: "lt", label: "<", needsValue: true },
  { value: "lte", label: "≤", needsValue: true },
  { value: "empty", label: "is empty", needsValue: false },
  { value: "not_empty", label: "is not empty", needsValue: false },
];

function cellKey(row: number, col: string) {
  return `${row} ${col}`;
}

function display(value: unknown): string {
  if (value === null || value === undefined) return "";
  return String(value);
}

/** Manual data editor: filter rows, click a cell to change it, save to re-analyze, undo. */
export function EditPanel({ datasetId }: { datasetId: number }) {
  const qc = useQueryClient();
  const [page, setPage] = useState(0);
  const [applied, setApplied] = useState<RowFilter>({});
  const [draftCol, setDraftCol] = useState("");
  const [draftOp, setDraftOp] = useState("contains");
  const [draftVal, setDraftVal] = useState("");
  const [pending, setPending] = useState<Map<string, string>>(new Map());
  const [editing, setEditing] = useState<{ r: number; col: string; value: string } | null>(null);

  const rowsQuery = useQuery({
    queryKey: ["dataset", datasetId, "editor-rows", applied, page],
    queryFn: () => editService.queryRows(datasetId, applied, PAGE_SIZE, page * PAGE_SIZE),
    placeholderData: keepPreviousData,
  });
  const history = useQuery({
    queryKey: ["dataset", datasetId, "edits"],
    queryFn: () => editService.history(datasetId),
  });

  const refreshAfterChange = (report: { overall_score: number }) => {
    qc.setQueryData(["dataset", datasetId, "quality"], report);
    qc.invalidateQueries({ queryKey: ["dataset", datasetId, "editor-rows"] });
    qc.invalidateQueries({ queryKey: ["dataset", datasetId, "edits"] });
    qc.invalidateQueries({ queryKey: ["dataset", datasetId] });
    qc.invalidateQueries({ queryKey: ["datasets"] });
  };

  const save = useMutation({
    mutationFn: () =>
      editService.apply(
        datasetId,
        [...pending.entries()].map(([key, value]) => {
          const sep = key.indexOf(" ");
          return { row_index: Number(key.slice(0, sep)), column: key.slice(sep + 1), value };
        })
      ),
    onSuccess: (res) => {
      setPending(new Map());
      refreshAfterChange(res.report);
      toast.success(`Applied ${res.applied} edit(s) - new score: ${res.report.overall_score}/100`);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const undo = useMutation({
    mutationFn: () => editService.undo(datasetId),
    onSuccess: (res) => {
      refreshAfterChange(res.report);
      toast.success(`Undid ${res.undone} edit(s) - new score: ${res.report.overall_score}/100`);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  if (rowsQuery.isLoading && !rowsQuery.data) return <Spinner label="Loading data..." />;
  if (!rowsQuery.data) return null;

  const { columns, rows, row_indices, total_rows, matched_rows } = rowsQuery.data;
  const totalPages = Math.max(1, Math.ceil(matched_rows / PAGE_SIZE));
  const busy = save.isPending || undo.isPending;
  const filtered = !!applied.filter_column;
  const opNeedsValue = OPERATORS.find((o) => o.value === draftOp)?.needsValue ?? true;

  const applyFilter = () => {
    if (!draftCol) return;
    setEditing(null);
    setPage(0);
    setApplied({ filter_column: draftCol, filter_op: draftOp, filter_value: opNeedsValue ? draftVal : null });
  };
  const clearFilter = () => {
    setEditing(null);
    setPage(0);
    setApplied({});
    setDraftCol("");
    setDraftVal("");
  };

  const startEdit = (r: number, col: string) => {
    if (busy) return;
    const abs = row_indices[r];
    const current = pending.get(cellKey(abs, col)) ?? display(rows[r]?.[col]);
    setEditing({ r, col, value: current });
  };

  const commitEdit = () => {
    if (!editing) return;
    const abs = row_indices[editing.r];
    const key = cellKey(abs, editing.col);
    const original = display(rows[editing.r]?.[editing.col]);
    setPending((p) => {
      const next = new Map(p);
      if (editing.value === original) next.delete(key);
      else next.set(key, editing.value);
      return next;
    });
    setEditing(null);
  };

  const discardCell = (key: string) => {
    setPending((p) => {
      const next = new Map(p);
      next.delete(key);
      return next;
    });
  };

  const changePage = (next: number) => {
    setEditing(null);
    setPage(Math.min(Math.max(0, next), totalPages - 1));
  };

  const undoable = history.data?.items?.length ?? 0;
  const from = matched_rows === 0 ? 0 : page * PAGE_SIZE + 1;
  const to = Math.min((page + 1) * PAGE_SIZE, matched_rows);
  const selectCls =
    "rounded-lg border border-input bg-background px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-ring";

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Pencil className="size-4 text-accent" /> Edit data
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="mb-3 text-sm text-muted-foreground">
            Filter to the rows you want, then click any cell to change it. Saving applies the changes and
            re-runs the quality analysis. Every save is one undoable step. Leave a cell empty to set it to null.
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="gradient"
              size="sm"
              onClick={() => save.mutate()}
              disabled={pending.size === 0 || busy}
            >
              <Save className="size-4" />
              {save.isPending ? "Saving & re-analyzing..." : `Save & re-analyze${pending.size ? ` (${pending.size})` : ""}`}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => undo.mutate()}
              disabled={undoable === 0 || busy}
              title={undoable === 0 ? "No saved edits to undo" : "Revert the most recent saved edit batch"}
            >
              <RotateCcw className={`size-4 ${undo.isPending ? "animate-spin" : ""}`} />
              {undo.isPending ? "Undoing..." : "Undo last change"}
            </Button>
            {pending.size > 0 && (
              <Button variant="ghost" size="sm" onClick={() => setPending(new Map())} disabled={busy}>
                <X className="size-4" /> Discard unsaved
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-4">
          {/* Filter bar */}
          <div className="mb-3 flex flex-wrap items-center gap-2 rounded-lg border border-border bg-secondary/20 p-2">
            <Filter className="ml-1 size-4 text-muted-foreground" />
            <select className={selectCls} value={draftCol} onChange={(e) => setDraftCol(e.target.value)}>
              <option value="">Column…</option>
              {columns.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
            <select className={selectCls} value={draftOp} onChange={(e) => setDraftOp(e.target.value)}>
              {OPERATORS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
            <Input
              className="h-8 w-40 text-xs"
              placeholder="value"
              value={draftVal}
              disabled={!opNeedsValue}
              onChange={(e) => setDraftVal(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && applyFilter()}
            />
            <Button size="sm" variant="outline" onClick={applyFilter} disabled={!draftCol}>Apply</Button>
            {filtered && (
              <Button size="sm" variant="ghost" onClick={clearFilter}>
                <X className="size-4" /> Clear
              </Button>
            )}
            <span className="ml-auto text-xs text-muted-foreground">
              {filtered ? `${matched_rows.toLocaleString()} of ${total_rows.toLocaleString()} rows match` : `${total_rows.toLocaleString()} rows`}
              {rowsQuery.isFetching && <span className="ml-2 animate-pulse">loading...</span>}
            </span>
          </div>

          {/* Pager */}
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <span className="text-sm text-muted-foreground">
              {matched_rows === 0 ? "No matching rows" : `Showing ${from.toLocaleString()}-${to.toLocaleString()} of ${matched_rows.toLocaleString()}`}
            </span>
            <div className="flex items-center gap-1.5">
              <Button variant="outline" size="sm" onClick={() => changePage(page - 1)} disabled={page === 0 || busy}>
                <ChevronLeft className="size-4" /> Prev
              </Button>
              <span className="px-2 text-sm text-muted-foreground">Page {page + 1} / {totalPages.toLocaleString()}</span>
              <Button variant="outline" size="sm" onClick={() => changePage(page + 1)} disabled={page >= totalPages - 1 || busy}>
                Next <ChevronRight className="size-4" />
              </Button>
            </div>
          </div>

          {matched_rows === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">No rows match this filter.</p>
          ) : (
            <div className="max-h-[520px] overflow-auto rounded-lg border border-border">
              <table className="w-full text-sm">
                <thead className="sticky top-0 z-10 bg-secondary">
                  <tr>
                    <th className="px-2 py-2 text-left text-xs font-semibold text-muted-foreground">#</th>
                    {columns.map((c) => (
                      <th key={c} className="whitespace-nowrap px-3 py-2 text-left font-semibold">{c}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, r) => {
                    const absRow = row_indices[r];
                    return (
                      <tr key={absRow} className="border-t border-border">
                        <td className="px-2 py-1.5 text-xs text-muted-foreground">{absRow}</td>
                        {columns.map((c) => {
                          const key = cellKey(absRow, c);
                          const edited = pending.has(key);
                          const isEditing = editing?.r === r && editing?.col === c;
                          return (
                            <td key={c} className="whitespace-nowrap px-1 py-0.5">
                              {isEditing ? (
                                <input
                                  autoFocus
                                  className="w-full min-w-24 rounded border border-primary bg-background px-2 py-1 text-sm focus:outline-none"
                                  value={editing.value}
                                  onChange={(e) => setEditing({ ...editing, value: e.target.value })}
                                  onBlur={commitEdit}
                                  onKeyDown={(e) => {
                                    if (e.key === "Enter") commitEdit();
                                    if (e.key === "Escape") setEditing(null);
                                  }}
                                />
                              ) : (
                                <span
                                  role="button"
                                  tabIndex={0}
                                  onClick={() => startEdit(r, c)}
                                  onKeyDown={(e) => e.key === "Enter" && startEdit(r, c)}
                                  className={`block w-full cursor-pointer rounded px-2 py-1 text-left transition-colors hover:bg-secondary/60 ${
                                    edited ? "bg-warning/15 font-medium text-warning" : ""
                                  }`}
                                  title={edited ? "Unsaved change - click to edit again" : "Click to edit"}
                                >
                                  {edited ? (
                                    <>
                                      {pending.get(key) || NULL_LABEL}
                                      <X
                                        className="ml-1 inline size-3 opacity-60 hover:opacity-100"
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          discardCell(key);
                                        }}
                                      />
                                    </>
                                  ) : (
                                    display(row[c]) || <span className="text-muted-foreground">{NULL_LABEL}</span>
                                  )}
                                </span>
                              )}
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          {pending.size > 0 && (
            <p className="mt-2 text-xs text-muted-foreground">
              {pending.size} unsaved change(s) across all rows/pages. They're applied together on Save.
            </p>
          )}
        </CardContent>
      </Card>

      {(history.data?.items?.length ?? 0) > 0 && (
        <CollapsibleCard
          title={
            <span className="flex items-center gap-2">
              <History className="size-4" /> Edit history ({history.data!.items.length} undoable)
            </span>
          }
        >
          <div className="space-y-2">
            {history.data!.items.map((batch, i) => (
              <div key={batch.id} className="rounded-md border border-border bg-background p-3 text-sm">
                <div className="mb-1 flex items-center gap-2">
                  <Badge variant={i === 0 ? "secondary" : "outline"}>
                    {i === 0 ? "next undo" : `undo #${i + 1}`}
                  </Badge>
                  <span className="text-xs text-muted-foreground">{formatDate(batch.created_at)}</span>
                </div>
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                  {batch.edits.map((e, j) => (
                    <span key={j}>
                      row {e.row_index} - <span className="font-medium text-foreground">{e.column}</span>:{" "}
                      {display(e.old_value) || NULL_LABEL} {"->"} {display(e.new_value) || NULL_LABEL}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </CollapsibleCard>
      )}
    </div>
  );
}
