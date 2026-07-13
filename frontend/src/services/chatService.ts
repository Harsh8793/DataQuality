import { apiClient, unwrap } from "@/lib/apiClient";
import type { ApiResponse, Paginated } from "@/types/api";
import type { ChatHistory, ChatMessage, HistoryItem } from "@/types/models";

/** Chat and history API calls. */
export const chatService = {
  ask: (datasetId: number, question: string, sessionId?: number) =>
    unwrap<ChatMessage>(
      apiClient.post<ApiResponse<ChatMessage>>(`/datasets/${datasetId}/chat`, {
        question,
        session_id: sessionId ?? null,
      })
    ),

  history: (datasetId: number) =>
    unwrap<ChatHistory>(apiClient.get<ApiResponse<ChatHistory>>(`/datasets/${datasetId}/chat/history`)),

  clearHistory: (datasetId: number) =>
    unwrap<null>(apiClient.delete<ApiResponse<null>>(`/datasets/${datasetId}/chat/history`)),
};

export const historyService = {
  list: (limit = 30, offset = 0) =>
    unwrap<Paginated<HistoryItem>>(
      apiClient.get<ApiResponse<Paginated<HistoryItem>>>("/history", { params: { limit, offset } })
    ),
};
