import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "../lib/api-client";

export interface ExtractionTask {
  taskId: string;
  candidateId: string | null;
  domain: string | null;
  status: "processing" | "completed" | "failed";
  usedRealLlm: boolean;
  entitiesExtracted: number;
  relationsExtracted: number;
  knowledgeItemId: string | null;
  errorMessage: string | null;
  createdAt: string;
}

export interface ExtractionReviewItem {
  itemId: string;
  taskId: string;
  candidateId: string | null;
  domain: string | null;
  kind: "entity" | "relation";
  payload: Record<string, unknown>;
  confidence: number;
  hasConflict: boolean;
  createdAt: string;
}

export function useExtractionTasks(params?: { domain?: string; status?: string }) {
  return useQuery({
    queryKey: ["extraction", "tasks", params],
    queryFn: () => apiClient.get<ExtractionTask[]>("/extraction/tasks", params),
    refetchInterval: (query) => {
      const tasks = query.state.data as ExtractionTask[] | undefined;
      return tasks?.some((t) => t.status === "processing") ? 2000 : false;
    },
  });
}

export function useCreateExtractionTask() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (req: { candidate_id?: string; domain?: string; submitter_id: string }) =>
      apiClient.post<{ taskId: string; status: string }>("/extraction/task", req),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["extraction", "tasks"] });
    },
  });
}

export function useExtractionReviewQueue(params?: { domain?: string; kind?: string }) {
  return useQuery({
    queryKey: ["extraction", "review-queue", params],
    queryFn: () => apiClient.get<ExtractionReviewItem[]>("/extraction/review-queue", params),
  });
}

export function useExtractionReviewAction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (req: { item_id: string; action: "approved" | "rejected"; reviewer_id: string; comment?: string }) =>
      apiClient.post<{ itemId: string; status: string; materializedToGraph: boolean }>("/extraction/review/action", req),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["extraction", "review-queue"] });
      queryClient.invalidateQueries({ queryKey: ["extraction", "stats"] });
    },
  });
}

export function useExtractionStats() {
  return useQuery({
    queryKey: ["extraction", "stats"],
    queryFn: () =>
      apiClient.get<{
        entitiesToday: number;
        relationsToday: number;
        avgConfidence: number | null;
        pendingReviewRatio: number | null;
      }>("/extraction/stats"),
  });
}
