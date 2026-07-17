import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  EyeOff,
  Lightbulb,
  RotateCcw,
  ShieldAlert,
  Sparkles,
  Trash2,
  Undo2,
  Wand2,
  Wrench,
} from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { DataTable } from "@/components/common/DataTable";
import { InfoTip } from "@/components/common/InfoTip";
import { Modal } from "@/components/common/Modal";
import { AddValidationCard } from "@/components/quality/AddValidationCard";
import { ScoreGauge } from "@/components/quality/ScoreGauge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress, Spinner } from "@/components/ui/misc";
import { useQuality } from "@/hooks/useDatasets";
import { aiService } from "@/services/aiService";
import { analysisService } from "@/services/analysisService";
import type { FixRecord, QualityIssue, Severity } from "@/types/models";

const DIMENSIONS: { key: keyof typeof DIM_INFO; label: string }[] = [
  { key: "completeness", label: "Completeness" },
  { key: "accuracy", label: "Accuracy" },
  { key: "consistency", label: "Consistency" },
  { key: "uniqueness", label: "Uniqueness" },
  { key: "validity", label: "Validity" },
  { key: "integrity", label: "Integrity" },
];

const DIM_INFO = {
  completeness: "How much of the data is actually filled in. Lowered by missing, null or blank values.",
  accuracy: "How correct and realistic the values look — right data types and no extreme outliers.",
  consistency: "How uniform the data is — consistent casing, formatting and no mixed types in a column.",
  uniqueness: "How free of duplicates the data is — no repeated rows, duplicate columns or repeated IDs.",
  validity: "How well values match their expected format — valid emails, phone numbers, URLs and dates.",
  integrity: "How well the data holds together structurally — unique identifiers and a non-empty, sound shape.",
} as const;

const SEVERITY_ORDER: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };
const SEVERITIES: Severity[] = ["critical", "high", "medium", "low", "info"];

function barColor(v: number) {
  if (v >= 80) return "hsl(var(--success))";
  if (v >= 60) return "hsl(var(--warning))";
  return "hsl(var(--destructive))";
}

/** Quality report: score, dimensions, filterable issues, one-click fixes with diffs. */
export function QualityPanel({ datasetId }: { datasetId: number }) {
  const qc = useQueryClient();
  const { data: report, isLoading } = useQuality(datasetId);
  const [severityFilter, setSeverityFilter] = useState<Severity | "all">("all");
  const [confirmFixAll, setConfirmFixAll] = useState(false);
  const [confirmUndo, setConfirmUndo] = useState(false);
  const [issuesOpen, setIssuesOpen] = useState(true);
  const [statusFilter, setStatusFilter] = useState<"all" | "open" | "ignored" | "solved">("all");
  const [diff, setDiff] = useState<FixRecord | null>(null);

  const fixes = useQuery({
    queryKey: ["dataset", datasetId, "fixes"],
    queryFn: () => aiService.listFixes(datasetId),
  });

  const refreshAll = (rep: { overall_score: number }) => {
    qc.setQueryData(["dataset", datasetId, "quality"], rep);
    qc.invalidateQueries({ queryKey: ["dataset", datasetId, "fixes"] });
    qc.invalidateQueries({ queryKey: ["dataset", datasetId] });
    qc.invalidateQueries({ queryKey: ["datasets"] });
  };

  const exclude = useMutation({
    mutationFn: ({ checkKey, column }: { checkKey: string; column: string | null }) =>
      aiService.excludeValidation(datasetId, checkKey, column),
    onSuccess: (res) => {
      refreshAll(res.report);
      toast.success(`Validation ignored — score now ${res.report.overall_score}/100`);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const include = useMutation({
    mutationFn: ({ checkKey, column }: { checkKey: string; column: string | null }) =>
      aiService.includeValidation(datasetId, checkKey, column),
    onSuccess: (res) => {
      refreshAll(res.report);
      toast.success(`Validation re-included — score now ${res.report.overall_score}/100`);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const deleteValidation = useMutation({
    mutationFn: (checkKey: string) => aiService.deleteValidation(datasetId, Number(checkKey.split("_")[1])),
    onSuccess: (res) => {
      refreshAll(res.report);
      toast.success("Custom validation deleted.");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const fixAll = useMutation({
    mutationFn: () => aiService.fixAll(datasetId),
    onSuccess: (res) => {
      refreshAll(res.report);
      setConfirmFixAll(false);
      toast.success(`Applied ${res.applied} fixes — score now ${res.report.overall_score}/100`);
    },
    onError: (e: Error) => {
      toast.error(e.message);
      setConfirmFixAll(false);
    },
  });

  const undoFixes = useMutation({
    mutationFn: () => aiService.undoFixes(datasetId),
    onSuccess: (res) => {
      refreshAll(res.report);
      setConfirmUndo(false);
      toast.success(`Undid ${res.undone_fixes} fix(es) — score now ${res.report.overall_score}/100`);
    },
    onError: (e: Error) => {
      toast.error(e.message);
      setConfirmUndo(false);
    },
  });

  const counts = useMemo(() => {
    const c: Record<string, number> = { critical: 0, high: 0, medium: 0, low: 0, info: 0 };
    // Count only active (non-ignored) issues toward the severity summary.
    for (const i of report?.issues ?? []) if (!i.excluded) c[i.severity] = (c[i.severity] ?? 0) + 1;
    return c;
  }, [report]);

  if (isLoading) return <Spinner label="Running quality analysis…" />;
  if (!report) return null;

  const fixableCount = report.issues.filter((i) => i.fixable).length;
  const fixList = fixes.data?.fixes ?? [];

  // Merge open/ignored issues and solved fixes into ONE stably-ordered list.
  // The sort key is severity → check → column (NOT status), so an issue keeps
  // its exact position when it flips to ignored or solved.
  const openKeys = new Set(report.issues.map((i) => `${i.check_key}::${i.column_name}`));
  const solvedOnly = fixList.filter((f) => !openKeys.has(`${f.check_key}::${f.column_name}`));
  type Row =
    | { kind: "open" | "ignored"; severity: string; sortKey: string; issue: QualityIssue }
    | { kind: "solved"; severity: string; sortKey: string; fix: FixRecord };
  const rows: Row[] = [
    ...report.issues.map((i): Row => ({
      kind: i.excluded ? "ignored" : "open",
      severity: i.severity,
      sortKey: `${SEVERITY_ORDER[i.severity] ?? 9}:${i.check_key}:${i.column_name}`,
      issue: i,
    })),
    ...solvedOnly.map((f): Row => ({
      kind: "solved",
      severity: f.severity,
      sortKey: `${SEVERITY_ORDER[f.severity] ?? 9}:${f.check_key}:${f.column_name}`,
      fix: f,
    })),
  ].sort((a, b) => a.sortKey.localeCompare(b.sortKey));

  const visibleRows = rows.filter(
    (r) =>
      (severityFilter === "all" || r.severity === severityFilter) &&
      (statusFilter === "all" || r.kind === statusFilter)
  );
  const openCount = report.issues.filter((i) => !i.excluded).length;
  const ignoredCount = report.issues.filter((i) => i.excluded).length;
  const solvedCount = solvedOnly.length;

  return (
    <div className="space-y-4">
      {/* ---- Top summary strip ---- */}
      <Card>
        <CardContent className="flex flex-col gap-5 pt-6 lg:flex-row lg:items-center">
          <div className="flex shrink-0 items-center gap-4">
            <ScoreGauge score={report.overall_score} size={130} />
          </div>

          {/* What the Data Quality score is and how it's computed */}
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold">What is the Data Quality score?</p>
            <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
              A 0–100 rating of how trustworthy this dataset is, averaged across six
              dimensions — completeness, accuracy, consistency, uniqueness, validity and
              integrity. Each dimension starts at 100 and loses points for every issue
              found, weighted by its <span className="font-medium text-foreground">severity</span>{" "}
              (critical &gt; high &gt; medium &gt; low) and the{" "}
              <span className="font-medium text-foreground">share of rows affected</span>. The
              overall score is a weighted blend of the six (completeness and validity count most).
            </p>
          </div>

          {/* Actions */}
          <div className="flex shrink-0 flex-wrap gap-2 lg:ml-auto">
            {fixes.data?.undoable && (
              <Button variant="outline" size="sm" onClick={() => setConfirmUndo(true)} disabled={undoFixes.isPending}>
                <RotateCcw className={`size-4 ${undoFixes.isPending ? "animate-spin" : ""}`} /> Undo fixes
              </Button>
            )}
            <Button
              variant="gradient"
              size="sm"
              onClick={() => setConfirmFixAll(true)}
              disabled={fixableCount === 0 || fixAll.isPending}
              title={fixableCount === 0 ? "No auto-fixable issues" : `Fix ${fixableCount} issues in one click`}
            >
              <Wand2 className="size-4" />
              {fixAll.isPending ? "Fixing…" : `Fix all (${fixableCount})`}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* ---- Dimension breakdown ---- */}
      <Card>
        <CardHeader>
          <CardTitle>Dimension breakdown</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-x-8 gap-y-3 sm:grid-cols-2">
          {DIMENSIONS.map((dim) => {
            const value = report[dim.key] as number;
            return (
              <div key={dim.key}>
                <div className="mb-1 flex justify-between text-sm">
                  <span className="flex items-center gap-1.5">
                    {dim.label}
                    <InfoTip text={DIM_INFO[dim.key]} label={`What is ${dim.label}?`} />
                  </span>
                  <span className="font-medium" style={{ color: barColor(value) }}>{value.toFixed(0)}</span>
                </div>
                <Progress value={value} indicatorColor={barColor(value)} />
              </div>
            );
          })}
        </CardContent>
      </Card>

      {/* ---- AI validation builder ---- */}
      <AddValidationCard datasetId={datasetId} onAdded={refreshAll} />

      {/* ---- Detected issues (open + solved, one stable list) ---- */}
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3 p-5">
          <button
            type="button"
            onClick={() => setIssuesOpen((v) => !v)}
            className="flex items-center gap-2 text-left"
          >
            <ChevronDown className={`size-5 text-muted-foreground transition-transform ${issuesOpen ? "rotate-180" : ""}`} />
            <CardTitle className="flex items-center gap-2">
              <AlertTriangle className="size-4 text-warning" /> Detected issues
              <Badge variant="outline">{openCount} open</Badge>
              {ignoredCount > 0 && <Badge variant="secondary">{ignoredCount} ignored</Badge>}
              {solvedCount > 0 && <Badge variant="success">{solvedCount} solved</Badge>}
            </CardTitle>
          </button>

          {/* Filter dropdowns */}
          <div className="flex flex-wrap items-center gap-2">
            <FilterSelect
              value={statusFilter}
              onChange={(v) => setStatusFilter(v as typeof statusFilter)}
              options={[
                { value: "all", label: `All statuses (${openCount + ignoredCount + solvedCount})` },
                { value: "open", label: `Open (${openCount})` },
                { value: "ignored", label: `Ignored (${ignoredCount})` },
                { value: "solved", label: `Solved (${solvedCount})` },
              ]}
            />
            <FilterSelect
              value={severityFilter}
              onChange={(v) => setSeverityFilter(v as typeof severityFilter)}
              options={[
                { value: "all", label: `All severities (${report.total_issues})` },
                ...SEVERITIES.filter((s) => counts[s]).map((s) => ({
                  value: s,
                  label: `${s[0].toUpperCase()}${s.slice(1)} (${counts[s]})`,
                })),
              ]}
            />
          </div>
        </div>

        {issuesOpen && (
          <CardContent className="space-y-3 pt-0">
            {rows.length === 0 ? (
              <p className="text-sm text-muted-foreground">No issues detected — great data quality! 🎉</p>
            ) : visibleRows.length === 0 ? (
              <p className="text-sm text-muted-foreground">No issues match the current filters.</p>
            ) : (
              visibleRows.map((r) =>
                r.kind === "solved" ? (
                  <SolvedCard key={`fix-${r.fix.id}`} fix={r.fix} onView={() => setDiff(r.fix)} />
                ) : (
                  <IssueCard
                    key={`issue-${r.issue.id}`}
                    issue={r.issue}
                    datasetId={datasetId}
                    onFixed={refreshAll}
                    onExclude={() =>
                      exclude.mutate({ checkKey: r.issue.check_key, column: r.issue.column_name })
                    }
                    onInclude={() =>
                      include.mutate({ checkKey: r.issue.check_key, column: r.issue.column_name })
                    }
                    onDeleteValidation={() => deleteValidation.mutate(r.issue.check_key)}
                    busy={exclude.isPending || include.isPending || deleteValidation.isPending}
                  />
                )
              )
            )}
          </CardContent>
        )}
      </Card>

      {/* Shared before/after diff modal for solved issues */}
      <FixDiffModal fix={diff} onClose={() => setDiff(null)} />

      <ConfirmDialog
        open={confirmFixAll}
        title={`Fix all ${fixableCount} issues?`}
        description="This applies each issue's automated fix to this dataset in place and re-runs the analysis. You can undo it in one click afterwards. (Cleaning, which makes a separate cleaned copy, is unaffected.)"
        confirmLabel="Fix all"
        loading={fixAll.isPending}
        onConfirm={() => fixAll.mutate()}
        onCancel={() => setConfirmFixAll(false)}
      />
      <ConfirmDialog
        open={confirmUndo}
        destructive
        title="Undo the last batch of fixes?"
        description="This restores the data to exactly how it was before the most recent fix (or fix-all) and re-runs the analysis."
        confirmLabel="Undo fixes"
        loading={undoFixes.isPending}
        onConfirm={() => undoFixes.mutate()}
        onCancel={() => setConfirmUndo(false)}
      />
    </div>
  );
}

function FilterSelect({
  value,
  onChange,
  options,
}: {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="rounded-lg border border-input bg-background px-3 py-1.5 text-xs font-medium text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  );
}

function IssueCard({
  issue,
  datasetId,
  onFixed,
  onExclude,
  onInclude,
  onDeleteValidation,
  busy,
}: {
  issue: QualityIssue;
  datasetId: number;
  onFixed: (report: { overall_score: number }) => void;
  onExclude: () => void;
  onInclude: () => void;
  onDeleteValidation: () => void;
  busy: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const [affectedOpen, setAffectedOpen] = useState(false);
  const [allCols, setAllCols] = useState(false);
  const qc = useQueryClient();

  const affected = useQuery({
    queryKey: ["affected", datasetId, issue.id, allCols],
    queryFn: () => analysisService.affectedRows(datasetId, issue.id, allCols),
    enabled: affectedOpen,
  });

  const fix = useMutation({
    mutationFn: () => aiService.fixIssue(datasetId, issue.id),
    onSuccess: (res) => {
      onFixed(res.report);
      qc.invalidateQueries({ queryKey: ["dataset", datasetId, "fixes"] });
      toast.success(`${res.detail} — new score: ${res.report.overall_score}/100`);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const title = issue.problem ?? issue.check_key.replace(/_/g, " ");
  const hasDetails = !!(issue.why || issue.business_impact || issue.recommended_fix);
  const ignored = issue.excluded;

  return (
    <div className={`rounded-lg border bg-background ${ignored ? "border-dashed border-border/70 opacity-70" : "border-border"}`}>
      {/* Header row */}
      <div className="flex flex-wrap items-center gap-2 p-3">
        <Badge variant={issue.severity as Severity}>{issue.severity}</Badge>
        {ignored && (
          <Badge variant="secondary" className="gap-1">
            <EyeOff className="size-3" /> Ignored
          </Badge>
        )}
        {issue.custom && (
          <Badge variant="default" className="gap-1">
            <Wand2 className="size-3" /> Custom
          </Badge>
        )}
        <span className={`font-medium ${ignored ? "text-muted-foreground line-through decoration-muted-foreground/40" : ""}`}>
          {title}
        </span>
        {issue.column_name && <Badge variant="outline">{issue.column_name}</Badge>}
        <Badge variant="secondary" className="capitalize">{issue.dimension}</Badge>

        <div className="ml-auto flex items-center gap-1.5">
          {ignored ? (
            <span className="text-xs text-muted-foreground" title="This validation is excluded from the quality score">
              not counted in score
            </span>
          ) : (
            <>
              {issue.fixable && (
                <button
                  onClick={() => fix.mutate()}
                  disabled={fix.isPending}
                  className="flex items-center gap-1 rounded-md border border-primary/40 bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary transition-colors hover:bg-primary/20 disabled:opacity-50"
                  title="Apply the targeted fix for just this issue"
                >
                  <Wrench className={`size-3 ${fix.isPending ? "animate-spin" : ""}`} />
                  {fix.isPending ? "Fixing…" : "Fix this"}
                </button>
              )}
              {issue.suggest_drop && (
                <span
                  className="flex items-center gap-1 rounded-md border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-400"
                  title="This column is 100% empty — there is nothing to impute from, so dropping it is recommended"
                >
                  <Lightbulb className="size-3" /> Suggest: drop column
                </span>
              )}
            </>
          )}
          <button
            onClick={() => setAffectedOpen(true)}
            className="rounded-md border border-border px-2 py-0.5 text-xs text-muted-foreground transition-colors hover:border-primary/50 hover:text-primary"
            title={issue.column_level ? "View this column's values" : "View affected rows"}
          >
            {issue.column_level ? "View column →" : `${issue.count} affected →`}
          </button>
          {ignored ? (
            <button
              onClick={onInclude}
              disabled={busy}
              className="flex items-center gap-1 rounded-md border border-primary/40 bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary transition-colors hover:bg-primary/20 disabled:opacity-50"
              title="Re-include this validation in the quality score"
            >
              <Undo2 className="size-3" /> Re-include
            </button>
          ) : (
            <button
              onClick={onExclude}
              disabled={busy}
              className="flex items-center gap-1 rounded-md border border-border px-2 py-0.5 text-xs text-muted-foreground transition-colors hover:border-warning/50 hover:text-warning disabled:opacity-50"
              title="Ignore this validation — keeps it here but removes it from the score (reversible)"
            >
              <EyeOff className="size-3" /> Ignore
            </button>
          )}
          {issue.custom && (
            <button
              onClick={onDeleteValidation}
              disabled={busy}
              className="flex items-center gap-1 rounded-md border border-border px-2 py-0.5 text-xs text-muted-foreground transition-colors hover:border-destructive/50 hover:text-destructive disabled:opacity-50"
              title="Delete this custom validation permanently"
            >
              <Trash2 className="size-3" /> Delete rule
            </button>
          )}
          {hasDetails && (
            <button
              onClick={() => setExpanded((v) => !v)}
              className="rounded-md p-1 text-muted-foreground transition-colors hover:text-foreground"
              title={expanded ? "Hide details" : "Show details"}
              aria-expanded={expanded}
            >
              <ChevronDown className={`size-4 transition-transform ${expanded ? "rotate-180" : ""}`} />
            </button>
          )}
        </div>
      </div>

      {/* Expandable AI explanation */}
      {expanded && hasDetails && (
        <div className="grid gap-2 border-t border-border p-3 text-sm sm:grid-cols-3">
          {issue.why && <Detail icon={<Sparkles className="size-3.5" />} label="Why" text={issue.why} />}
          {issue.business_impact && (
            <Detail icon={<ShieldAlert className="size-3.5" />} label="Business impact" text={issue.business_impact} />
          )}
          {issue.recommended_fix && (
            <Detail icon={<Wrench className="size-3.5" />} label="Recommended fix" text={issue.recommended_fix} />
          )}
          {issue.confidence != null && (
            <div className="flex items-center gap-1 text-xs text-muted-foreground sm:col-span-3">
              <Lightbulb className="size-3" /> AI confidence: {(issue.confidence * 100).toFixed(0)}%
            </div>
          )}
        </div>
      )}

      <Modal
        open={affectedOpen}
        onClose={() => setAffectedOpen(false)}
        wide
        title={issue.column_level ? `Column values — ${title}` : `Affected rows — ${title}`}
        description={
          issue.check_key === "duplicate_columns"
            ? `Compare "${issue.column_name}" with the column it duplicates — the values should be identical in every row.`
            : issue.column_level
              ? `Column-level issue on "${issue.column_name}" — it applies to the whole column; its values are shown below.`
              : issue.column_name
                ? `Column "${issue.column_name}" · ${issue.count} rows affected`
                : `${issue.count} rows affected`
        }
      >
        <div className="mb-2 flex justify-end">
          <button
            onClick={() => setAllCols((v) => !v)}
            className="rounded-md border border-border px-2 py-1 text-xs text-muted-foreground hover:text-primary"
          >
            {allCols ? "Show key columns only" : "Show all columns"}
          </button>
        </div>
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
          <p className="text-sm text-muted-foreground">No specific rows to display for this issue.</p>
        )}
      </Modal>
    </div>
  );
}

function SolvedCard({ fix, onView }: { fix: FixRecord; onView: () => void }) {
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-success/25 bg-success/5 p-3">
      <Badge variant="success" className="gap-1">
        <CheckCircle2 className="size-3" /> Solved
      </Badge>
      <span className="text-sm font-medium text-muted-foreground line-through decoration-success/50">
        {fix.problem ?? fix.check_key.replace(/_/g, " ")}
      </span>
      {fix.column_name && <Badge variant="outline">{fix.column_name}</Badge>}
      <span className="text-xs text-success">{fix.detail}</span>
      {fix.changes.length > 0 && (
        <button
          onClick={onView}
          className="ml-auto rounded-md border border-border px-2 py-0.5 text-xs text-muted-foreground transition-colors hover:border-primary/50 hover:text-primary"
        >
          View changes →
        </button>
      )}
    </div>
  );
}

function FixDiffModal({ fix, onClose }: { fix: FixRecord | null; onClose: () => void }) {
  const idCol = fix?.identifier_column;
  const valueCol = fix?.column_name ?? "value";
  return (
    <Modal
      open={!!fix}
      onClose={onClose}
      wide
      title={`Changes — ${fix?.problem ?? fix?.check_key.replace(/_/g, " ") ?? ""}`}
      description={fix ? `${fix.detail} · showing ${fix.changes.length} of ${fix.rows_affected} changes` : ""}
    >
      {fix && (
        <div className="overflow-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-secondary">
              <tr>
                <th className="px-3 py-2 text-left font-semibold">Row #</th>
                {idCol && <th className="px-3 py-2 text-left font-semibold">{idCol}</th>}
                <th className="px-3 py-2 text-left font-semibold">{valueCol} (before)</th>
                <th className="px-3 py-2 text-left font-semibold" />
                <th className="px-3 py-2 text-left font-semibold">{valueCol} (after)</th>
              </tr>
            </thead>
            <tbody>
              {fix.changes.map((c, i) => (
                <tr key={i} className="border-t border-border">
                  <td className="px-3 py-2 text-xs text-muted-foreground">{c.row_index >= 0 ? c.row_index : "—"}</td>
                  {idCol && (
                    <td className="px-3 py-2 font-medium text-muted-foreground">
                      {c.identifier != null ? String(c.identifier) : "—"}
                    </td>
                  )}
                  <td className="px-3 py-2">
                    <span className="rounded bg-destructive/10 px-1.5 py-0.5 text-destructive">
                      {c.old_value === null ? "(null)" : String(c.old_value)}
                    </span>
                  </td>
                  <td className="px-2 text-muted-foreground"><ArrowRight className="size-3.5" /></td>
                  <td className="px-3 py-2">
                    <span className="rounded bg-success/10 px-1.5 py-0.5 text-success">
                      {c.new_value === null ? "(null)" : String(c.new_value)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Modal>
  );
}

function Detail({ icon, label, text }: { icon: React.ReactNode; label: string; text: string }) {
  return (
    <div className="rounded-md bg-secondary/40 p-2">
      <div className="mb-1 flex items-center gap-1 text-xs font-medium text-primary">
        {icon} {label}
      </div>
      <p className="text-xs text-muted-foreground">{text}</p>
    </div>
  );
}
