import { useMutation, useQuery } from "@tanstack/react-query";
import { apiClient } from "../lib/api-client";

export function useKnowledgeSearch(params?: {
  keyword?: string;
  domain?: string;
  type?: string;
  page?: number;
  pageSize?: number;
}) {
  return useQuery({
    queryKey: ["knowledge", "search", params],
    queryFn: () =>
      apiClient.get<{
        page: number;
        pageSize: number;
        total: number;
        items: Array<{
          knowledgeId: string;
          title: string;
          domain: string;
          type: string;
          confidence: number | null;
          classificationLevel: string;
          summary: string;
        }>;
      }>("/knowledge/search", params),
  });
}

export function useKnowledgeDetail(knowledgeId: string | undefined) {
  return useQuery({
    queryKey: ["knowledge", knowledgeId],
    queryFn: () =>
      apiClient.get<{
        knowledgeId: string;
        title: string;
        domain: string;
        type: string;
        summary: string;
        confidence: number | null;
        classificationLevel: string;
        status: string;
        version: number;
      }>(`/knowledge/${knowledgeId}`),
    enabled: !!knowledgeId,
  });
}

export function useSemanticSearch() {
  return useMutation({
    mutationFn: (req: { query: string; domain?: string; topK?: number }) =>
      apiClient.post("/knowledge/semantic-search", req),
  });
}