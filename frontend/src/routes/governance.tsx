import { createFileRoute } from "@tanstack/react-router";
import { PageHeader, SectionHeader, Kpi, Btn, Badge } from "@/components/panel";
import { Modal, useModal } from "@/components/modal";
import { useState, useCallback } from "react";
import {
  useGovernanceStats,
  useKnowledgeReviewQueue,
  useReviewAction,
  useConflicts,
  useConflictResolve,
  useAuditLog,
  useSnapshots,
  useCreateSnapshot,
} from "@/hooks/use-governance";
import { useAuth } from "@/lib/auth";

export const Route = createFileRoute("/governance")({
  component: Governance,
  head: () => ({ meta: [{ title: "知识运营与治理 · Aether PHM" }] }),
});

function Governance() {
  const { user } = useAuth();
  const { data: stats } = useGovernanceStats();
  const { data: reviewQueue } = useKnowledgeReviewQueue();
  const { data: conflicts } = useConflicts("pending");
  const reviewAction = useReviewAction();
  const conflictResolve = useConflictResolve();
  const auditLog = useAuditLog();
  const snapshots = useSnapshots();
  const createSnapshot = useCreateSnapshot();
  const [resolveConflictId, setResolveConflictId] = useState<string | null>(null);
  const [resolveResolution, setResolveResolution] = useState("");
  const [snapshotName, setSnapshotName] = useState(
    `snapshot-${new Date().toISOString().slice(0, 10)}`,
  );
  const [snapshotComment, setSnapshotComment] = useState("");
  const auditModal = useModal();
  const snapshotModal = useModal();

  const handleReview = useCallback(
    (knowledgeId: string, action: "approved" | "rejected") => {
      reviewAction.mutate({
        knowledgeId,
        reviewer_id: user?.userId || "",
        action,
      });
    },
    [reviewAction, user],
  );

  const handleResolve = useCallback(() => {
    if (!resolveConflictId || !resolveResolution) return;
    conflictResolve.mutate(
      {
        conflictId: resolveConflictId,
        resolver_id: user?.userId || "",
        resolution: resolveResolution as "accept_a" | "accept_b" | "merge" | "escalate",
      },
      {
        onSuccess: () => {
          setResolveConflictId(null);
          setResolveResolution("");
        },
      },
    );
  }, [resolveConflictId, resolveResolution, conflictResolve, user]);

  const handleOpenAudit = useCallback(() => {
    auditModal.openModal();
    auditLog.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auditModal]);

  const handleOpenSnapshots = useCallback(() => {
    snapshotModal.openModal();
    snapshots.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [snapshotModal]);

  const handleCreateSnapshot = useCallback(() => {
    createSnapshot.mutate(
      { name: snapshotName, comment: snapshotComment || undefined, creator_id: user?.userId || "" },
      { onSuccess: () => snapshots.mutate() },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [createSnapshot, snapshotName, snapshotComment, user]);

  const totalKnowledge = stats?.totalKnowledgeCount ?? "—";
  const byDomain = stats?.byDomain ?? {};
  const growth = stats?.growthLast30Days;

  return (
    <div className="animate-in-up p-8">
      <PageHeader
        eyebrow="M10 · Governance"
        title="知识运营与治理"
        description="知识生命周期、版本、密级、责任专家与冲突仲裁的一体化治理面板，保证知识可追溯、可回滚、可审计。"
        actions={
          <>
            <Btn variant="outline" onClick={handleOpenAudit}>
              审计日志
            </Btn>
            <Btn variant="primary" onClick={handleOpenSnapshots}>
              发布快照
            </Btn>
          </>
        }
      />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
        <Kpi label="生效条目" value={String(totalKnowledge)} tone="success" />
        <Kpi label="待仲裁冲突" value={conflicts ? String(conflicts.length) : "—"} tone="warning" />
        <Kpi
          label="待审核条目"
          value={reviewQueue ? String(reviewQueue.length) : "—"}
          tone="primary"
        />
        <Kpi label="30日增长" value={growth !== undefined ? `+${growth}` : "—"} tone="success" />
      </div>

      {Object.keys(byDomain).length > 0 && (
        <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
          {Object.entries(byDomain).map(([domain, count]) => (
            <div key={domain} className="border border-border bg-card p-3">
              <div className="text-[10px] uppercase tracking-widest text-muted-foreground">
                {domain}
              </div>
              <div className="mt-1 font-mono text-lg font-bold">{count}</div>
            </div>
          ))}
        </div>
      )}

      <div className="mt-8 grid grid-cols-1 gap-8 xl:grid-cols-3">
        <div className="xl:col-span-2">
          <SectionHeader
            title="冲突仲裁队列"
            action={<Badge tone="primary">基于标题相似度自动检测</Badge>}
          />
          <div className="overflow-hidden border border-border">
            <table className="w-full text-left text-[11px]">
              <thead className="border-b border-border bg-card">
                <tr>
                  {["条目 A", "条目 B", "相似度", "说明", ""].map((h) => (
                    <th
                      key={h}
                      className="p-3 font-bold uppercase tracking-tighter text-muted-foreground"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {conflicts && conflicts.length > 0 ? (
                  conflicts.map((c) => (
                    <tr key={c.conflictId} className="hover:bg-white/5">
                      <td className="p-3 font-medium">{c.titleA}</td>
                      <td className="p-3 font-medium">{c.titleB}</td>
                      <td className="p-3 font-mono text-primary">
                        {c.similarity != null ? c.similarity.toFixed(2) : "-"}
                      </td>
                      <td
                        className="p-3 text-muted-foreground max-w-xs truncate"
                        title={c.description || ""}
                      >
                        {c.description}
                      </td>
                      <td className="p-3 text-right">
                        <Btn
                          variant="outline"
                          onClick={() => {
                            setResolveConflictId(c.conflictId);
                            setResolveResolution("");
                          }}
                        >
                          仲裁
                        </Btn>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={5} className="p-6 text-center text-muted-foreground">
                      暂无待仲裁冲突
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <SectionHeader title="待审核条目" />
          <div className="overflow-hidden border border-border">
            <table className="w-full text-left text-[11px]">
              <thead className="border-b border-border bg-card">
                <tr>
                  {["知识条目", "领域", "密级", "操作"].map((h) => (
                    <th
                      key={h}
                      className="p-3 font-bold uppercase tracking-tighter text-muted-foreground"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {reviewQueue && reviewQueue.length > 0 ? (
                  reviewQueue.map((r) => (
                    <tr key={r.knowledgeId} className="hover:bg-white/5">
                      <td className="p-3 font-medium">{r.title}</td>
                      <td className="p-3 text-muted-foreground">{r.domain}</td>
                      <td className="p-3">
                        <Badge tone="warning">{r.classificationLevel}</Badge>
                      </td>
                      <td className="p-3 text-right flex gap-2 justify-end">
                        <Btn
                          variant="outline"
                          onClick={() => handleReview(r.knowledgeId, "approved")}
                          disabled={reviewAction.isPending}
                        >
                          通过
                        </Btn>
                        <Btn
                          variant="ghost"
                          onClick={() => handleReview(r.knowledgeId, "rejected")}
                          disabled={reviewAction.isPending}
                        >
                          拒绝
                        </Btn>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={4} className="p-6 text-center text-muted-foreground">
                      暂无待审核条目
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div>
          <SectionHeader
            title="领域分布"
            action={<Badge tone="primary">{Object.keys(byDomain).length} 个领域</Badge>}
          />
          <div className="space-y-2 border border-border bg-card/40 p-4">
            {Object.keys(byDomain).length > 0 ? (
              Object.entries(byDomain).map(([domain, count]) => {
                const total = Object.values(byDomain).reduce((a, b) => a + b, 0) || 1;
                const pct = Math.round((count / total) * 100);
                return (
                  <div key={domain}>
                    <div className="mb-1 flex items-center justify-between text-[11px]">
                      <span className="text-muted-foreground">{domain}</span>
                      <span className="font-mono">
                        {count} · {pct}%
                      </span>
                    </div>
                    <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/5">
                      <div className="h-full bg-primary" style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                );
              })
            ) : (
              <div className="text-xs text-muted-foreground text-center py-4">暂无已发布知识</div>
            )}
          </div>
        </div>
      </div>

      {resolveConflictId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="w-full max-w-md border border-border bg-card p-6">
            <h3 className="mb-4 text-sm font-bold uppercase tracking-widest">
              仲裁冲突 {resolveConflictId}
            </h3>
            <div className="space-y-4">
              <div>
                <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                  解决方案
                </label>
                <select
                  value={resolveResolution}
                  onChange={(e) => setResolveResolution(e.target.value)}
                  className="w-full rounded border border-border bg-white/5 p-2 text-xs"
                >
                  <option value="">请选择</option>
                  <option value="accept_a">采用条目 A（废弃 B）</option>
                  <option value="accept_b">采用条目 B（废弃 A）</option>
                  <option value="merge">人工合并（暂不废弃任一方）</option>
                  <option value="escalate">升级处理</option>
                </select>
              </div>
              {conflictResolve.isError && (
                <div className="text-xs text-destructive">
                  仲裁失败：{(conflictResolve.error as Error)?.message}
                </div>
              )}
              <div className="flex gap-2 justify-end">
                <Btn variant="ghost" onClick={() => setResolveConflictId(null)}>
                  取消
                </Btn>
                <Btn
                  variant="primary"
                  onClick={handleResolve}
                  disabled={!resolveResolution || conflictResolve.isPending}
                >
                  {conflictResolve.isPending ? "提交中…" : "确认仲裁"}
                </Btn>
              </div>
            </div>
          </div>
        </div>
      )}

      {auditModal.open && (
        <Modal title="审计日志" onClose={auditModal.closeModal}>
          <div className="space-y-3">
            {auditLog.isPending ? (
              <div className="text-xs text-muted-foreground py-4 text-center">加载中…</div>
            ) : auditLog.data && auditLog.data.length > 0 ? (
              <div className="overflow-hidden border border-border max-h-96 overflow-y-auto">
                <table className="w-full text-left text-[11px]">
                  <thead className="border-b border-border bg-card sticky top-0">
                    <tr>
                      {["时间", "用户", "操作", "资源"].map((h) => (
                        <th
                          key={h}
                          className="p-3 font-bold uppercase tracking-tighter text-muted-foreground"
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {auditLog.data.map((l) => (
                      <tr key={l.id} className="hover:bg-white/5">
                        <td className="p-3 font-mono text-muted-foreground">
                          {new Date(l.createdAt).toLocaleString()}
                        </td>
                        <td className="p-3">{l.userId}</td>
                        <td className="p-3 font-mono text-primary">{l.action}</td>
                        <td className="p-3 text-muted-foreground">
                          {l.resourceType
                            ? `${l.resourceType}${l.resourceId ? ` · ${l.resourceId}` : ""}`
                            : "-"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="text-xs text-muted-foreground py-4 text-center">暂无审计记录</div>
            )}
            <div className="flex gap-2 justify-end">
              <Btn variant="ghost" onClick={auditModal.closeModal}>
                关闭
              </Btn>
            </div>
          </div>
        </Modal>
      )}

      {snapshotModal.open && (
        <Modal title="发布快照" onClose={snapshotModal.closeModal}>
          <div className="space-y-4">
            <div className="text-xs text-muted-foreground">
              记录当前知识库的条目统计快照，用于追溯知识库在某一时刻的整体状态（非数据库物理备份）。
            </div>
            <div>
              <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                快照名称
              </label>
              <input
                value={snapshotName}
                onChange={(e) => setSnapshotName(e.target.value)}
                className="w-full rounded border border-border bg-white/5 p-2 text-xs"
              />
            </div>
            <div>
              <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                备注
              </label>
              <textarea
                rows={2}
                value={snapshotComment}
                onChange={(e) => setSnapshotComment(e.target.value)}
                className="w-full rounded border border-border bg-white/5 p-2 text-xs"
                placeholder="快照说明"
              />
            </div>
            {createSnapshot.isError && (
              <div className="text-xs text-destructive">
                创建失败：{(createSnapshot.error as Error)?.message}
              </div>
            )}
            {createSnapshot.isSuccess && <div className="text-xs text-success">快照创建成功！</div>}
            <div className="flex gap-2 justify-end">
              <Btn variant="ghost" onClick={snapshotModal.closeModal}>
                关闭
              </Btn>
              <Btn
                variant="primary"
                onClick={handleCreateSnapshot}
                disabled={!snapshotName || createSnapshot.isPending}
              >
                {createSnapshot.isPending ? "创建中…" : "创建快照"}
              </Btn>
            </div>
            {snapshots.data && snapshots.data.length > 0 && (
              <div className="border-t border-border pt-3">
                <div className="mb-2 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                  历史快照
                </div>
                <div className="max-h-40 space-y-2 overflow-y-auto">
                  {snapshots.data.map((s) => (
                    <div
                      key={s.snapshotId}
                      className="border border-border bg-card/50 p-2 text-[11px]"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-bold">{s.name}</span>
                        <span className="font-mono text-muted-foreground">
                          {s.totalKnowledgeCount} 条
                        </span>
                      </div>
                      <div className="mt-0.5 font-mono text-[9px] text-muted-foreground">
                        {new Date(s.createdAt).toLocaleString()}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}
