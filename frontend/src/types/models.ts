/** Domain types mirroring backend response schemas. */

export interface User {
  id: number;
  name: string;
  email: string;
  role: string;
}

export interface AuthToken {
  access_token: string;
  token_type: string;
  user: User;
}

export interface DatasetSummary {
  id: number;
  name: string;
  file_format: string;
  encoding: string | null;
  delimiter: string | null;
  row_count: number;
  col_count: number;
  file_size_bytes: number;
  memory_bytes: number;
  status: string;
  is_cleaned: boolean;
  parent_id: number | null;
  approval_status: "not_required" | "pending" | "approved" | "rejected";
  approval_note: string | null;
  created_at: string;
}

export interface DatasetPreview {
  columns: string[];
  rows: Record<string, unknown>[];
  total_rows: number;
}

export interface ColumnProfile {
  name: string;
  ordinal: number;
  physical_type: string;
  semantic_type: string;
  null_count: number;
  null_pct: number;
  distinct_count: number;
  cardinality_ratio: number;
  min_val: string | null;
  max_val: string | null;
  mean_val: number | null;
  std_val: number | null;
  sample_values: unknown[];
  business_name: string | null;
  description: string | null;
  sensitivity: string | null;
  is_pii: boolean;
}

export type Severity = "critical" | "high" | "medium" | "low" | "info";

export interface QualityIssue {
  id: number;
  check_key: string;
  dimension: string;
  severity: Severity;
  count: number;
  column_name: string | null;
  sample: unknown[];
  problem: string | null;
  why: string | null;
  business_impact: string | null;
  recommended_fix: string | null;
  confidence: number | null;
  fixable: boolean;
  column_level: boolean;
  suggest_drop: boolean;
  excluded: boolean;
}

export interface QualityReport {
  id: number;
  dataset_id: number;
  overall_score: number;
  previous_score: number | null;
  completeness: number;
  accuracy: number;
  consistency: number;
  uniqueness: number;
  validity: number;
  integrity: number;
  duplicate_rows: number;
  total_issues: number;
  issues: QualityIssue[];
}

export interface CleaningOp {
  op: string;
  column: string | null;
  rows_affected: number;
  detail: string;
  rows: number[];
}

export interface CompareMetric {
  label: string;
  before: number;
  after: number;
}

export interface CleaningResult {
  cleaned_dataset_id: number;
  operations: CleaningOp[];
  comparison: CompareMetric[];
}

export interface KpiCard {
  id: string;
  label: string;
  value: number;
  format: string;
}

export interface ChartSpec {
  id: string;
  type: "bar" | "pie" | "line" | "scatter";
  title: string;
  x: string;
  y: string;
  data: Record<string, unknown>[];
}

export interface DashboardSelection {
  kpis: string[];
  charts: string[];
}

export interface Dashboard {
  pool: { kpis: KpiCard[]; charts: ChartSpec[] };
  selected: DashboardSelection;
}

export interface Governance {
  classification: string;
  pii_columns: string[];
  rationale: string | null;
  ingestion_tier: string;
  tier_rationale: string | null;
  column_metadata: Record<string, unknown>[];
}

export interface Insight {
  title: string;
  insight: string;
  action: string;
  category: string;
}

export interface ChatMessage {
  answer: string;
  sql: string;
  columns: string[];
  rows: Record<string, unknown>[];
  row_count: number;
  chart_spec: ChartSpec | null;
  session_id: number;
}

export interface ChatHistoryMessage {
  role: "user" | "assistant";
  content: string;
  sql: string | null;
  columns: string[];
  rows: Record<string, unknown>[];
  chart_spec: ChartSpec | null;
}

export interface ChatHistory {
  session_id: number | null;
  messages: ChatHistoryMessage[];
}

export interface GeneratedReport {
  id: number;
  report_type: string;
  title: string;
  size_bytes: number;
}

export interface ExplainResult {
  explanation: string;
  generated_by: string;
}

export interface DataStory {
  story: string;
  generated_by: string;
}

export interface ChartCommandResult {
  kind: "kpi" | "chart";
  kpi: KpiCard | null;
  chart: ChartSpec | null;
  message: string;
}

export interface ColumnShift {
  column: string;
  left_mean: number | null;
  right_mean: number | null;
  mean_change_pct: number | null;
  left_null_pct: number;
  right_null_pct: number;
}

export interface CompareResult {
  left_name: string;
  right_name: string;
  left_rows: number;
  right_rows: number;
  left_cols: number;
  right_cols: number;
  added_columns: string[];
  removed_columns: string[];
  common_columns: number;
  column_shifts: ColumnShift[];
  narrative: string;
  generated_by: string;
}

export interface FixChange {
  row_index: number;
  identifier: string | null;
  old_value: unknown;
  new_value: unknown;
}

export interface FixRecord {
  id: number;
  batch_id: number;
  check_key: string;
  column_name: string | null;
  identifier_column: string | null;
  severity: string;
  problem: string | null;
  op: string;
  rows_affected: number;
  detail: string;
  changes: FixChange[];
  created_at: string;
}

export interface IssueFixResult {
  op: string;
  rows_affected: number;
  detail: string;
  fix: FixRecord | null;
  report: QualityReport;
}

export interface FixAllResult {
  applied: number;
  fixes: FixRecord[];
  report: QualityReport;
}

export interface FixListResult {
  fixes: FixRecord[];
  undoable: boolean;
}

export interface UndoFixResult {
  undone_fixes: number;
  report: QualityReport;
}

export interface ExclusionItem {
  id: number;
  check_key: string;
  column_name: string | null;
}

export interface ExclusionActionResult {
  exclusions: ExclusionItem[];
  report: QualityReport;
}

export interface ExclusionListResult {
  exclusions: ExclusionItem[];
}

export interface RowQueryResult {
  columns: string[];
  rows: Record<string, unknown>[];
  row_indices: number[];
  total_rows: number;
  matched_rows: number;
}

export interface CellEditRecord {
  row_index: number;
  column: string;
  old_value: unknown;
  new_value: unknown;
}

export interface EditBatch {
  id: number;
  edits: CellEditRecord[];
  created_at: string;
}

export interface ApplyEditsResult {
  edit_id: number;
  applied: number;
  report: QualityReport;
}

export interface UndoEditResult {
  undone: number;
  remaining: number;
  report: QualityReport;
}

export interface HistoryItem {
  id: number;
  action: string;
  summary: string | null;
  dataset_id: number;
  payload: Record<string, unknown>;
  created_at: string;
}
