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

  /** Download the dataset's current data (edits + fixes included) as CSV. */
  exportCsv: async (id: number) => {
    const res = await apiClient.get(`/datasets/${id}/export`, { responseType: "blob" });
    // Prefer the server's filename so cleaned datasets are labelled as such.
    const disposition = String(res.headers["content-disposition"] ?? "");
    const filename = /filename="?([^"]+)"?/.exec(disposition)?.[1] ?? `dataset_${id}.csv`;

    const url = URL.createObjectURL(res.data as Blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
  },
};
