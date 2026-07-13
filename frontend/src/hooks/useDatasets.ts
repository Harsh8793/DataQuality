import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { analysisService } from "@/services/analysisService";
import { datasetService } from "@/services/datasetService";

/** Server-state hooks for datasets and analysis (React Query). */

export function useDatasets(limit = 20, offset = 0) {
  return useQuery({
    queryKey: ["datasets", limit, offset],
    queryFn: () => datasetService.list(limit, offset),
  });
}

export function useDataset(id: number) {
  return useQuery({ queryKey: ["dataset", id], queryFn: () => datasetService.get(id), enabled: !!id });
}

export function useDatasetPreview(id: number) {
  return useQuery({
    queryKey: ["dataset", id, "preview"],
    queryFn: () => datasetService.preview(id),
    enabled: !!id,
  });
}

export function useProfile(id: number) {
  return useQuery({
    queryKey: ["dataset", id, "profile"],
    queryFn: () => datasetService.profile(id),
    enabled: !!id,
  });
}

export function useUpload() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => datasetService.upload(file),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["datasets"] });
      toast.success("Dataset uploaded successfully.");
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useDeleteDataset() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => datasetService.remove(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["datasets"] });
      toast.success("Dataset deleted.");
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useQuality(id: number) {
  return useQuery({
    queryKey: ["dataset", id, "quality"],
    queryFn: () => analysisService.quality(id),
    enabled: !!id,
  });
}

export function useSetApproval(id: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ approved, note }: { approved: boolean; note?: string }) =>
      datasetService.setApproval(id, approved, note),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ["dataset", id] });
      qc.invalidateQueries({ queryKey: ["datasets"] });
      toast.success(vars.approved ? "Dataset approved." : "Dataset rejected.");
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useCleanResult(id: number) {
  return useQuery({
    queryKey: ["dataset", id, "clean"],
    queryFn: () => analysisService.cleanResult(id),
    enabled: !!id,
  });
}

export function useClean(id: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => analysisService.clean(id),
    onSuccess: (result) => {
      // Seed the cache so the result persists across tab switches.
      qc.setQueryData(["dataset", id, "clean"], result);
      qc.invalidateQueries({ queryKey: ["datasets"] });
      toast.success("Dataset cleaned successfully.");
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useDashboard(id: number) {
  return useQuery({
    queryKey: ["dataset", id, "dashboard"],
    queryFn: () => analysisService.dashboard(id),
    enabled: !!id,
  });
}

export function useSaveDashboard(id: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (selection: { kpis: string[]; charts: string[] }) =>
      analysisService.saveDashboard(id, selection),
    onError: (e: Error) => toast.error(e.message),
    onSettled: () => qc.invalidateQueries({ queryKey: ["dataset", id, "dashboard"] }),
  });
}

export function useInsights(id: number) {
  return useQuery({
    queryKey: ["dataset", id, "insights"],
    queryFn: () => analysisService.insights(id),
    enabled: !!id,
  });
}

export function useGovernance(id: number) {
  return useQuery({
    queryKey: ["dataset", id, "governance"],
    queryFn: () => analysisService.governance(id),
    enabled: !!id,
  });
}
