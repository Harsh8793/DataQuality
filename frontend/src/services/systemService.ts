import { apiClient, unwrap } from "@/lib/apiClient";
import type { ApiResponse } from "@/types/api";
import type { LlmStatus } from "@/types/models";

/** System/runtime health API calls. */
export const systemService = {
  llmStatus: () => unwrap<LlmStatus>(apiClient.get<ApiResponse<LlmStatus>>("/system/llm")),
};
