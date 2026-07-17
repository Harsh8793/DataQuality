import { apiClient, unwrap } from "@/lib/apiClient";
import type { ApiResponse } from "@/types/api";
import type {
  ChartCommandResult,
  ChartSpec,
  CompareResult,
  DataStory,
  CustomValidationItem,
  ExclusionActionResult,
  ExclusionListResult,
  ExplainResult,
  ValidationActionResult,
  ValidationProposal,
  FixAllResult,
  FixListResult,
  IssueFixResult,
  KpiCard,
  UndoFixResult,
} from "@/types/models";

/** AI playground API calls: explain, story, chart-on-command, compare, fixes. */
export const aiService = {
  explainKpi: (datasetId: number, kpi: KpiCard) =>
    unwrap<ExplainResult>(
      apiClient.post<ApiResponse<ExplainResult>>(`/datasets/${datasetId}/explain`, {
        kind: "kpi",
        label: kpi.label,
        value: kpi.value,
        format: kpi.format,
      })
    ),

  explainChart: (datasetId: number, chart: ChartSpec) =>
    unwrap<ExplainResult>(
      apiClient.post<ApiResponse<ExplainResult>>(`/datasets/${datasetId}/explain`, {
        kind: "chart",
        label: chart.title,
        chart_type: chart.type,
        x: chart.x,
        y: chart.y,
        data: chart.data.slice(0, 15),
      })
    ),

  story: (datasetId: number, refresh = false) =>
    unwrap<DataStory>(
      apiClient.get<ApiResponse<DataStory>>(`/datasets/${datasetId}/story`, { params: { refresh } })
    ),

  chartCommand: (datasetId: number, command: string) =>
    unwrap<ChartCommandResult>(
      apiClient.post<ApiResponse<ChartCommandResult>>(`/datasets/${datasetId}/dashboard/command`, { command })
    ),

  compare: (leftId: number, rightId: number) =>
    unwrap<CompareResult>(
      apiClient.post<ApiResponse<CompareResult>>(`/datasets/compare`, { left_id: leftId, right_id: rightId })
    ),

  chatSuggestions: (datasetId: number) =>
    unwrap<{ questions: string[] }>(
      apiClient.get<ApiResponse<{ questions: string[] }>>(`/datasets/${datasetId}/chat/suggestions`)
    ),

  fixIssue: (datasetId: number, issueId: number) =>
    unwrap<IssueFixResult>(
      apiClient.post<ApiResponse<IssueFixResult>>(`/datasets/${datasetId}/quality/issues/${issueId}/fix`)
    ),

  fixAll: (datasetId: number) =>
    unwrap<FixAllResult>(apiClient.post<ApiResponse<FixAllResult>>(`/datasets/${datasetId}/quality/fix-all`)),

  listFixes: (datasetId: number) =>
    unwrap<FixListResult>(apiClient.get<ApiResponse<FixListResult>>(`/datasets/${datasetId}/quality/fixes`)),

  undoFixes: (datasetId: number) =>
    unwrap<UndoFixResult>(apiClient.post<ApiResponse<UndoFixResult>>(`/datasets/${datasetId}/quality/fixes/undo`)),

  listExclusions: (datasetId: number) =>
    unwrap<ExclusionListResult>(apiClient.get<ApiResponse<ExclusionListResult>>(`/datasets/${datasetId}/quality/exclusions`)),

  excludeValidation: (datasetId: number, checkKey: string, columnName: string | null) =>
    unwrap<ExclusionActionResult>(
      apiClient.post<ApiResponse<ExclusionActionResult>>(`/datasets/${datasetId}/quality/exclusions`, {
        check_key: checkKey,
        column_name: columnName,
      })
    ),

  includeValidation: (datasetId: number, checkKey: string, columnName: string | null) =>
    unwrap<ExclusionActionResult>(
      apiClient.post<ApiResponse<ExclusionActionResult>>(`/datasets/${datasetId}/quality/exclusions/remove`, {
        check_key: checkKey,
        column_name: columnName,
      })
    ),

  proposeValidation: (datasetId: number, prompt: string) =>
    unwrap<ValidationProposal>(
      apiClient.post<ApiResponse<ValidationProposal>>(`/datasets/${datasetId}/quality/validations/propose`, { prompt })
    ),

  addValidation: (datasetId: number, proposal: ValidationProposal) =>
    unwrap<ValidationActionResult>(
      apiClient.post<ApiResponse<ValidationActionResult>>(`/datasets/${datasetId}/quality/validations`, {
        name: proposal.name,
        description: proposal.description,
        dimension: proposal.dimension,
        severity: proposal.severity,
        condition: proposal.condition,
      })
    ),

  listValidations: (datasetId: number) =>
    unwrap<{ validations: CustomValidationItem[] }>(
      apiClient.get<ApiResponse<{ validations: CustomValidationItem[] }>>(`/datasets/${datasetId}/quality/validations`)
    ),

  deleteValidation: (datasetId: number, validationId: number) =>
    unwrap<ValidationActionResult>(
      apiClient.delete<ApiResponse<ValidationActionResult>>(`/datasets/${datasetId}/quality/validations/${validationId}`)
    ),
};
