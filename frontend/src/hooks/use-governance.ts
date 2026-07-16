import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "../lib/api-client";

export function useGovernanceStats() {
  return useQuery({
    queryKey: ["governance", "stats"],
    queryFn: () =>
      apiClient.get<{
        totalKnowledgeCount: number;
        byDomain: Record<string, number>;
        growthLast30Days: number;
      }>("/governance/stats/overview"),
  });
}

export function useKnowledgeReviewQueue(domain?: string) {
  return useQuery({
    queryKey: ["governance", "review-queue", domain],
    queryFn: () =>
      apiClient.get<
        Array<{
          knowledgeId: string;
          title: string;
          domain: string;
          type: string;
          classificationLevel: string;
          ownerId: string | null;
          createdAt: string;
        }>
      >("/governance/review-queue", domain ? { domain } : undefined),
  });
}

export function useReviewAction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      knowledgeId,
      reviewer_id,
      action,
      comment,
    }: {
      knowledgeId: string;
      reviewer_id: string;
      action: "approved" | "rejected" | "escalated";
      comment?: string;
    }) =>
      apiClient.post<{ knowledgeId: string; result: string; knowledgeStatus: string }>(
        `/governance/review/${knowledgeId}/action`,
        { reviewer_id, action, comment },
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["governance", "review-queue"] });
      queryClient.invalidateQueries({ queryKey: ["governance", "stats"] });
    },
  });
}

export function useConflicts(status: string = "pending") {
  return useQuery({
    queryKey: ["governance", "conflicts", status],
    queryFn: () =>
      apiClient.get<
        Array<{
          conflictId: string;
          domain: string | null;
          conflictType: string;
          knowledgeIdA: string;
          titleA: string;
          knowledgeIdB: string;
          titleB: string;
          description: string | null;
          similarity: number | null;
          status: string;
          createdAt: string;
        }>
      >("/governance/conflicts", { status }),
  });
}

export function useConflictResolve() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      conflictId,
      resolver_id,
      resolution,
      comment,
    }: {
      conflictId: string;
      resolver_id: string;
      resolution: "accept_a" | "accept_b" | "merge" | "escalate";
      comment?: string;
    }) =>
      apiClient.post<{
        conflictId: string;
        resolution: string;
        deprecatedKnowledgeId: string | null;
      }>(`/governance/conflict/${conflictId}/resolve`, { resolver_id, resolution, comment }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["governance", "conflicts"] });
    },
  });
}

export function useQualityCheck() {
  return useQuery({
    queryKey: ["governance", "quality-check"],
    queryFn: () =>
      apiClient.get<
        Array<{ knowledgeId: string; title: string; issueType: string; description: string }>
      >("/governance/quality-check"),
  });
}

export function useAuditLog(resourceType?: string) {
  return useMutation({
    mutationFn: () =>
      apiClient.get<
        Array<{
          id: string;
          userId: string;
          action: string;
          resourceType: string | null;
          resourceId: string | null;
          detail: string | null;
          createdAt: string;
        }>
      >("/governance/audit-log", resourceType ? { resource_type: resourceType } : undefined),
  });
}

export function useContributionRank() {
  return useQuery({
    queryKey: ["governance", "contribution-rank"],
    queryFn: () =>
      apiClient.get<Array<{ userId: string; publishedCount: number }>>(
        "/governance/stats/contribution-rank",
      ),
  });
}

export function useCreateSnapshot() {
  return useMutation({
    mutationFn: (req: { name: string; comment?: string; creator_id: string }) =>
      apiClient.post<{
        snapshotId: string;
        name: string;
        totalKnowledgeCount: number;
        byDomain: Record<string, number>;
        byStatus: Record<string, number>;
        createdAt: string;
      }>("/governance/snapshot", req),
  });
}

export function useSnapshots() {
  return useMutation({
    mutationFn: () =>
      apiClient.get<
        Array<{
          snapshotId: string;
          name: string;
          comment: string | null;
          totalKnowledgeCount: number;
          byDomain: Record<string, number>;
          byStatus: Record<string, number>;
          creatorId: string;
          createdAt: string;
        }>
      >("/governance/snapshots"),
  });
}
