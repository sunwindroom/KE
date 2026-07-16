import { useMutation, useQuery } from "@tanstack/react-query";
import { apiClient } from "../lib/api-client";

export function useAgentTaskSubmit() {
  return useMutation({
    mutationFn: (req: { agent_type: string; input: Record<string, unknown>; domain?: string; submitter_id: string }) =>
      apiClient.post<{ taskId: string; status: string }>("/agent/task/submit", req),
  });
}

export function useAgentTaskStatus(taskId: string | undefined) {
  return useQuery({
    queryKey: ["agent", "task", taskId],
    queryFn: () =>
      apiClient.get<{ taskId: string; status: string; currentStep: string }>(`/agent/task/${taskId}/status`),
    enabled: !!taskId,
    refetchInterval: (query) => {
      const data = query.state.data;
      return data?.status === "running" || data?.status === "waiting_confirmation" ? 2000 : false;
    },
  });
}

export function useAgentTaskResult(taskId: string | undefined) {
  return useQuery({
    queryKey: ["agent", "task", taskId, "result"],
    queryFn: () =>
      apiClient.get<{
        taskId: string;
        trace: Array<{ step: number; action: string; output: string }>;
        finalResult: string;
      }>(`/agent/task/${taskId}/result`),
    enabled: !!taskId,
  });
}

export function useAgentConfirm() {
  return useMutation({
    mutationFn: ({
      taskId,
      confirmer_id,
      decision,
      comment,
    }: {
      taskId: string;
      confirmer_id: string;
      decision: string;
      comment?: string;
    }) =>
      apiClient.post<{ taskId: string; status: string }>(`/agent/task/${taskId}/confirm`, {
        confirmer_id,
        decision,
        comment,
      }),
  });
}