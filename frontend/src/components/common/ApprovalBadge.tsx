import { Badge } from "@/components/ui/badge";
import type { DatasetSummary } from "@/types/models";

const MAP: Record<DatasetSummary["approval_status"], { label: string; variant: "success" | "medium" | "critical" } | null> = {
  not_required: null,
  approved: { label: "Approved", variant: "success" },
  pending: { label: "Needs Review", variant: "medium" },
  rejected: { label: "Rejected", variant: "critical" },
};

/** Renders a dataset's approval status as a badge (nothing when not required). */
export function ApprovalBadge({ status }: { status: DatasetSummary["approval_status"] }) {
  const cfg = MAP[status];
  if (!cfg) return null;
  return <Badge variant={cfg.variant}>{cfg.label}</Badge>;
}
