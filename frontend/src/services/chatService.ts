import { apiClient, unwrap } from "@/lib/apiClient";
import type { ApiResponse } from "@/types/api";
import type { ChatHistory, ChatMessage } from "@/types/models";

/** Chat API calls (per-dataset conversation history). */
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
