import { useQuery } from "@tanstack/react-query";

import { systemService } from "@/services/systemService";

/** Server-state hooks for runtime/system health (React Query). */

/**
 * Live status of the AI layer.
 *
 * Polled on an interval so the dashboard tile flips to "Degraded" shortly
 * after Groq starts failing, without the user reloading the page.
 */
export function useLlmStatus() {
  return useQuery({
    queryKey: ["system", "llm"],
    queryFn: () => systemService.llmStatus(),
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
    staleTime: 10_000,
  });
}
