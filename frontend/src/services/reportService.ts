import { apiClient, unwrap } from "@/lib/apiClient";
import type { ApiResponse } from "@/types/api";
import type { GeneratedReport } from "@/types/models";

/** Report generation and download API calls. */
export const reportService = {
  generate: (datasetId: number, reportType: string) =>
    unwrap<GeneratedReport>(
      apiClient.post<ApiResponse<GeneratedReport>>(`/datasets/${datasetId}/reports`, {
        report_type: reportType,
      })
    ),

  /** Fetch a report as a blob and trigger a browser download. */
  download: async (reportId: number, filename: string) => {
    const res = await apiClient.get(`/reports/${reportId}/download`, { responseType: "blob" });
    const url = URL.createObjectURL(res.data as Blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
  },
};
