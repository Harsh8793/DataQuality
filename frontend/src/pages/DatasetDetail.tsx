import { AlertTriangle, ArrowLeft, Check, Database, Trash2, X } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ApprovalBadge } from "@/components/common/ApprovalBadge";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";

import { ChatPanel } from "@/components/chat/ChatPanel";
// import { CleaningPanel } from "@/components/cleaning/CleaningPanel";   // temporarily hidden
import { DashboardPanel } from "@/components/dashboard/DashboardPanel";
import { EditPanel } from "@/components/edit/EditPanel";
import { OverviewPanel } from "@/components/dataset/OverviewPanel";
import { GovernancePanel } from "@/components/governance/GovernancePanel";
// import { InsightsPanel } from "@/components/insights/InsightsPanel";   // temporarily hidden
import { QualityPanel } from "@/components/quality/QualityPanel";
import { ReportsPanel } from "@/components/reports/ReportsPanel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Spinner } from "@/components/ui/misc";
import { useDataset, useDeleteDataset, useSetApproval } from "@/hooks/useDatasets";

const TABS = [
  { value: "overview", label: "Overview" },
  { value: "quality", label: "Quality" },
  // { value: "cleaning", label: "Cleaning" },   // temporarily hidden
  { value: "edit", label: "Edit data" },
  { value: "dashboard", label: "Dashboard" },
  { value: "chat", label: "Chat" },
  // { value: "insights", label: "Insights" },   // temporarily hidden
  { value: "governance", label: "Governance" },
  { value: "reports", label: "Reports" },
];

/** Dataset workspace with all analysis tabs. */
export function DatasetDetail() {
  const params = useParams();
  const id = Number(params.id);
  const navigate = useNavigate();
  const { data: ds, isLoading } = useDataset(id);
  const del = useDeleteDataset();
  const approval = useSetApproval(id);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const confirmDelete = () => {
    del.mutate(id, { onSuccess: () => navigate("/datasets") });
  };

  if (isLoading) return <Spinner label="Loading dataset…" />;
  if (!ds) return <p className="text-muted-foreground">Dataset not found.</p>;

  return (
    <div className="space-y-4">
      <Link to="/datasets" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" /> Back to datasets
      </Link>

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex size-11 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-accent">
          <Database className="size-5 text-white" />
        </div>
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold">
            <span className="font-mono text-base text-muted-foreground">#{ds.id}</span>
            {ds.name}
          </h1>
          <p className="text-sm text-muted-foreground">
            {ds.row_count.toLocaleString()} rows · {ds.col_count} columns · {ds.file_format.toUpperCase()}
          </p>
        </div>
        {ds.is_cleaned && <Badge variant="success">cleaned</Badge>}
        <ApprovalBadge status={ds.approval_status} />
        <Button
          variant="outline"
          size="sm"
          className="ml-auto text-muted-foreground hover:text-destructive"
          onClick={() => setConfirmOpen(true)}
          disabled={del.isPending}
        >
          <Trash2 className="size-4" /> Delete
        </Button>
      </div>

      {ds.approval_status === "pending" && (
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-warning/40 bg-warning/10 p-4">
          <AlertTriangle className="size-5 shrink-0 text-warning" />
          <div className="min-w-0 flex-1">
            <p className="font-medium">Needs review</p>
            <p className="text-sm text-muted-foreground">
              This dataset's quality score is below the acceptance threshold (75/100). Review the issues,
              then approve to clear it for use or reject it.
            </p>
          </div>
          <div className="flex gap-2">
            <Button
              variant="destructive"
              size="sm"
              onClick={() => approval.mutate({ approved: false })}
              disabled={approval.isPending}
            >
              <X className="size-4" /> Reject
            </Button>
            <Button
              size="sm"
              onClick={() => approval.mutate({ approved: true })}
              disabled={approval.isPending}
            >
              <Check className="size-4" /> Approve
            </Button>
          </div>
        </div>
      )}

      {ds.approval_status === "rejected" && (
        <div className="flex items-center gap-3 rounded-lg border border-destructive/40 bg-destructive/10 p-4">
          <X className="size-5 shrink-0 text-destructive" />
          <p className="flex-1 text-sm">
            This dataset was <span className="font-medium">rejected</span> and is not cleared for downstream use.
          </p>
          <Button size="sm" variant="outline" onClick={() => approval.mutate({ approved: true })} disabled={approval.isPending}>
            <Check className="size-4" /> Approve instead
          </Button>
        </div>
      )}

      <Tabs defaultValue="overview">
        <TabsList>
          {TABS.map((t) => (
            <TabsTrigger key={t.value} value={t.value}>
              {t.label}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="overview"><OverviewPanel datasetId={id} /></TabsContent>
        <TabsContent value="quality"><QualityPanel datasetId={id} /></TabsContent>
        {/* <TabsContent value="cleaning"><CleaningPanel datasetId={id} /></TabsContent> */}
        <TabsContent value="edit"><EditPanel datasetId={id} /></TabsContent>
        <TabsContent value="dashboard"><DashboardPanel datasetId={id} /></TabsContent>
        <TabsContent value="chat"><ChatPanel datasetId={id} /></TabsContent>
        {/* <TabsContent value="insights"><InsightsPanel datasetId={id} /></TabsContent> */}
        <TabsContent value="governance"><GovernancePanel datasetId={id} /></TabsContent>
        <TabsContent value="reports"><ReportsPanel datasetId={id} /></TabsContent>
      </Tabs>

      <ConfirmDialog
        open={confirmOpen}
        destructive
        title={`Delete "${ds.name}"?`}
        description="This permanently removes the dataset and all its analysis, chats and reports from the database. This cannot be undone."
        confirmLabel="Delete"
        loading={del.isPending}
        onConfirm={confirmDelete}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  );
}
