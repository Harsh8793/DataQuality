import { apiClient, unwrap } from "@/lib/apiClient";
import type { ApiResponse } from "@/types/api";
import type { ApplyEditsResult, EditBatch, RowQueryResult, UndoEditResult } from "@/types/models";

export interface RowFilter {
  filter_column?: string | null;
  filter_op?: string | null;
  filter_value?: string | null;
}

/** Manual data-editing API calls: apply cell edits, undo, history. */
export const editService = {
  apply: (datasetId: number, edits: { row_index: number; column: string; value: unknown }[]) =>
    unwrap<ApplyEditsResult>(
      apiClient.post<ApiResponse<ApplyEditsResult>>(`/datasets/${datasetId}/edits`, { edits })
    ),

  undo: (datasetId: number) =>
    unwrap<UndoEditResult>(apiClient.post<ApiResponse<UndoEditResult>>(`/datasets/${datasetId}/edits/undo`)),

  history: (datasetId: number) =>
    unwrap<{ items: EditBatch[] }>(apiClient.get<ApiResponse<{ items: EditBatch[] }>>(`/datasets/${datasetId}/edits`)),

  queryRows: (datasetId: number, filter: RowFilter, limit: number, offset: number) =>
    unwrap<RowQueryResult>(
      apiClient.post<ApiResponse<RowQueryResult>>(`/datasets/${datasetId}/rows/query`, {
        ...filter,
        limit,
        offset,
      })
    ),
};
