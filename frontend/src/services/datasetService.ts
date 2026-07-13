import { apiClient, unwrap } from "@/lib/apiClient";
import type { ApiResponse, Paginated } from "@/types/api";
import type {
  ColumnProfile,
  DatasetPreview,
  DatasetSummary,
} from "@/types/models";

/** Dataset upload, listing, preview and profile API calls. */
export const datasetService = {
  upload: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return unwrap<DatasetSummary>(
      apiClient.post<ApiResponse<DatasetSummary>>("/datasets", form, {
        headers: { "Content-Type": "multipart/form-data" },
      })
    );
  },

  list: (limit = 20, offset = 0) =>
    unwrap<Paginated<DatasetSummary>>(
      apiClient.get<ApiResponse<Paginated<DatasetSummary>>>("/datasets", { params: { limit, offset } })
    ),

  get: (id: number) =>
    unwrap<DatasetSummary>(apiClient.get<ApiResponse<DatasetSummary>>(`/datasets/${id}`)),

  preview: (id: number, rows = 50, offset = 0) =>
    unwrap<DatasetPreview>(
      apiClient.get<ApiResponse<DatasetPreview>>(`/datasets/${id}/preview`, { params: { rows, offset } })
    ),

  profile: (id: number) =>
    unwrap<ColumnProfile[]>(apiClient.get<ApiResponse<ColumnProfile[]>>(`/datasets/${id}/profile`)),

  remove: (id: number) =>
    unwrap<null>(apiClient.delete<ApiResponse<null>>(`/datasets/${id}`)),

  setApproval: (id: number, approved: boolean, note?: string) =>
    unwrap<DatasetSummary>(
      apiClient.post<ApiResponse<DatasetSummary>>(`/datasets/${id}/approval`, { approved, note: note ?? null })
    ),
};
