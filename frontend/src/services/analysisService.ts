import { apiClient, unwrap } from "@/lib/apiClient";
import type { ApiResponse } from "@/types/api";
import type {
  CleaningResult,
  Dashboard,
  DatasetPreview,
  Governance,
  Insight,
  QualityReport,
} from "@/types/models";

/** Analysis, cleaning, dashboard, insights and governance API calls. */
export const analysisService = {
  analyze: (id: number) =>
    unwrap<QualityReport>(apiClient.post<ApiResponse<QualityReport>>(`/datasets/${id}/analyze`)),

  quality: (id: number) =>
    unwrap<QualityReport>(apiClient.get<ApiResponse<QualityReport>>(`/datasets/${id}/quality`)),

  clean: (id: number) =>
    unwrap<CleaningResult>(apiClient.post<ApiResponse<CleaningResult>>(`/datasets/${id}/clean`)),

  cleanResult: (id: number) =>
    unwrap<CleaningResult | null>(apiClient.get<ApiResponse<CleaningResult | null>>(`/datasets/${id}/clean`)),

  downloadCleanComparison: async (id: number, filename: string) => {
    const res = await apiClient.get(`/datasets/${id}/clean/download`, { responseType: "blob" });
    const url = URL.createObjectURL(res.data as Blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
  },

  dashboard: (id: number) =>
    unwrap<Dashboard>(apiClient.get<ApiResponse<Dashboard>>(`/datasets/${id}/dashboard`)),

  saveDashboard: (id: number, selection: { kpis: string[]; charts: string[] }) =>
    unwrap<null>(apiClient.put<ApiResponse<null>>(`/datasets/${id}/dashboard`, selection)),

  insights: (id: number) =>
    unwrap<Insight[]>(apiClient.get<ApiResponse<Insight[]>>(`/datasets/${id}/insights`)),

  governance: (id: number) =>
    unwrap<Governance>(apiClient.get<ApiResponse<Governance>>(`/datasets/${id}/governance`)),

  affectedRows: (datasetId: number, issueId: number, allColumns = false) =>
    unwrap<DatasetPreview>(
      apiClient.get<ApiResponse<DatasetPreview>>(`/datasets/${datasetId}/quality/issues/${issueId}/affected`, {
        params: { all_columns: allColumns },
      })
    ),

  cleanOpAffected: (datasetId: number, opIndex: number) =>
    unwrap<DatasetPreview>(
      apiClient.get<ApiResponse<DatasetPreview>>(`/datasets/${datasetId}/clean/operations/${opIndex}/affected`)
    ),
};
