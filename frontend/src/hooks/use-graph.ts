import { useQuery } from "@tanstack/react-query";
import { apiClient } from "../lib/api-client";

export function useGraphStats(domain?: string) {
  return useQuery({
    queryKey: ["graph", "stats", domain],
    queryFn: () =>
      apiClient.get<{ totalNodes: number; totalEdges: number; byType: Record<string, number> }>(
        "/graph/stats",
        domain ? { domain } : undefined,
      ),
  });
}

export function useGraphSubgraph(params?: {
  centerEntity?: string;
  depth?: number;
  domain?: string;
}) {
  return useQuery({
    queryKey: ["graph", "subgraph", params],
    queryFn: () =>
      apiClient.get<{
        nodes: Array<{
          id: string;
          name: string;
          type: string;
          properties?: Record<string, unknown>;
        }>;
        edges: Array<{
          source: string;
          target: string;
          relation: string;
          properties?: Record<string, unknown>;
        }>;
      }>("/graph/subgraph", params),
  });
}

export function useGraphEntity(entityId: string | undefined) {
  return useQuery({
    queryKey: ["graph", "entity", entityId],
    queryFn: () =>
      apiClient.get<{
        entityId: string;
        name: string;
        type: string;
        relations: Array<{ relation: string; target: string; targetType: string }>;
      }>(`/graph/entity/${entityId}`),
    enabled: !!entityId,
  });
}
