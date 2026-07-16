import { useMutation, useQuery } from "@tanstack/react-query";
import { apiClient } from "../lib/api-client";

export function useIngestionStatus(candidateId: string | undefined) {
  return useQuery({
    queryKey: ["ingestion", candidateId],
    queryFn: () =>
      apiClient.get<{ candidateId: string; status: string; extractedKnowledgeIds: string[] }>(
        `/ingestion/status/${candidateId}`
      ),
    enabled: !!candidateId,
  });
}

export function useDocumentUpload() {
  return useMutation({
    mutationFn: async ({
      file,
      domain,
      classificationLevel,
      projectId,
      submitterId,
    }: {
      file: File;
      domain: string;
      classificationLevel: string;
      projectId?: string;
      submitterId: string;
    }) => {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("domain", domain);
      formData.append("classification_level", classificationLevel);
      if (projectId) formData.append("project_id", projectId);
      formData.append("submitter_id", submitterId);
      return apiClient.upload<{ candidateId: string; status: string }>("/ingestion/document", formData);
    },
  });
}

export function useExpertInput() {
  return useMutation({
    mutationFn: (req: {
      domain: string;
      type: string;
      title: string;
      content: Record<string, unknown>;
      classification_level: string;
      submitter_id: string;
    }) => apiClient.post<{ candidateId: string; status: string }>("/ingestion/expert-input", req),
  });
}

export function useCandidates(params?: { domain?: string; status?: string; page?: number; pageSize?: number }) {
  return useQuery({
    queryKey: ["ingestion", "candidates", params],
    queryFn: () =>
      apiClient.get<{
        page: number;
        page_size: number;
        total: number;
        items: Array<{
          candidateId: string;
          sourceType: string;
          domain: string;
          sourceName: string | null;
          status: string;
          classificationLevel: string;
          createdAt: string;
        }>;
      }>("/ingestion/candidates", params),
  });
}

export function useIngestionStats() {
  return useQuery({
    queryKey: ["ingestion", "stats"],
    queryFn: () =>
      apiClient.get<{
        todayCandidates: number;
        successRate: number | null;
        dlqCount: number;
        totalCandidates: number;
      }>("/ingestion/stats"),
  });
}

export function useDLQ(params?: { domain?: string; page?: number; pageSize?: number }) {
  return useQuery({
    queryKey: ["ingestion", "dlq", params],
    queryFn: () => apiClient.get("/ingestion/dlq", params),
  });
}