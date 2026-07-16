import { createFileRoute } from "@tanstack/react-router";
import { PageHeader, Kpi, SectionHeader, Btn, Badge } from "@/components/panel";
import { Modal, useModal } from "@/components/modal";
import { X } from "lucide-react";
import { useState, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { useAuth } from "@/lib/auth";
import { useCandidates } from "@/hooks/use-ingestion";
import {
  useExtractionTasks,
  useCreateExtractionTask,
  useExtractionReviewQueue,
  useExtractionReviewAction,
  useExtractionStats,
} from "@/hooks/use-extraction";

export const Route = createFileRoute("/extraction")({
  component: Extraction,
  head: () => ({ meta: [{ title: "知识抽取 · Aether PHM" }] }),
});

const STEPS = [
  { s: "DocParser", d: "解析 PDF/Word/文本 · 结构化提取" },
  { s: "TextExtraction", d: "候选原文抽取（文档 / 专家录入）" },
  { s: "ExtractionEngine", d: "LLM 优先，不可用时降级为规则抽取" },
  { s: "ConfidenceScorer", d: "每条实体/关系独立置信度评分" },
  { s: "ExpertReview", d: "人工逐条审核 · 通过 / 驳回" },
  { s: "GraphMaterialize", d: "审核通过后直接写入知识图谱" },
];

function useOntologySchema() {
  return useQuery({
    queryKey: ["ontology", "schema"],
    queryFn: () =>
      apiClient.get<{
        classes: Array<{ className: string; labelZh: string; properties: string }>;
        relations: Array<{ name: string; domain: string; range: string }>;
      }>("/ontology/schema"),
  });
}

function Extraction() {
  const { user } = useAuth();
  const [showTaskModal, setShowTaskModal] = useState(false);
  const schemaModal = useModal();
  const createTask = useCreateExtractionTask();
  const { data: tasks } = useExtractionTasks();
  const { data: reviewQueue } = useExtractionReviewQueue();
  const { data: stats } = useExtractionStats();
  const { data: schema } = useOntologySchema();
  const reviewAction = useExtractionReviewAction();

  const handleReview = useCallback(
    (itemId: string, action: "approved" | "rejected") => {
      reviewAction.mutate({ item_id: itemId, action, reviewer_id: user?.userId || "" });
    },
    [reviewAction, user]
  );

  return (
    <div className="animate-in-up p-8">
      <PageHeader
        eyebrow="M02 · Knowledge Extraction"
        title="知识抽取与加工"
        description="从候选知识中抽取结构化实体与关系，经专家逐条审核后直接写入知识图谱，形成完整的入库闭环。"
        actions={<><Btn variant="outline" onClick={schemaModal.openModal}>查看本体 Schema</Btn><Btn variant="primary" onClick={() => setShowTaskModal(true)}>发起抽取任务</Btn></>}
      />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
        <Kpi label="今日新增实体" value={stats ? String(stats.entitiesToday) : "—"} tone="primary" />
        <Kpi label="今日新增关系" value={stats ? String(stats.relationsToday) : "—"} tone="primary" />
        <Kpi label="平均置信度" value={stats?.avgConfidence != null ? stats.avgConfidence.toFixed(2) : "—"} tone="primary" />
        <Kpi label="待复核比例" value={stats?.pendingReviewRatio != null ? `${(stats.pendingReviewRatio * 100).toFixed(0)}%` : "—"} tone="warning" />
      </div>

      <div className="mt-8">
        <SectionHeader title="抽取流水线拓扑" />
        <div className="grid grid-cols-1 gap-2 md:grid-cols-6">
          {STEPS.map((step, i) => (
            <div key={step.s} className="relative border border-border bg-card p-4">
              <div className="font-mono text-[9px] text-muted-foreground">STEP {i + 1}</div>
              <div className="mt-1 text-xs font-bold">{step.s}</div>
              <div className="mt-1 text-[10px] leading-tight text-muted-foreground">{step.d}</div>
              {i < STEPS.length - 1 && (
                <div className="absolute right-[-6px] top-1/2 hidden size-2 -translate-y-1/2 rotate-45 border-r border-t border-primary/50 bg-background md:block" />
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="mt-8 grid grid-cols-1 gap-8 xl:grid-cols-2">
        <div>
          <SectionHeader title="最近抽取任务" />
          <div className="overflow-hidden border border-border">
            <table className="w-full text-left text-[11px]">
              <thead className="border-b border-border bg-card">
                <tr>{["任务", "领域", "状态", "抽取结果"].map((h) => (
                  <th key={h} className="p-3 font-bold uppercase tracking-tighter text-muted-foreground">{h}</th>
                ))}</tr>
              </thead>
              <tbody className="divide-y divide-border">
                {tasks && tasks.length > 0 ? tasks.slice(0, 8).map((t) => (
                  <tr key={t.taskId} className="hover:bg-white/5">
                    <td className="p-3 font-mono text-primary">{t.taskId}</td>
                    <td className="p-3">{t.domain || "-"}</td>
                    <td className="p-3">
                      <Badge tone={t.status === "completed" ? "success" : t.status === "failed" ? "danger" : "warning"}>
                        {t.status === "completed" ? "已完成" : t.status === "failed" ? "失败" : "处理中"}
                      </Badge>
                    </td>
                    <td className="p-3 font-mono text-[10px] text-muted-foreground">
                      {t.status === "failed" ? (t.errorMessage || "未知错误") : `实体 ${t.entitiesExtracted} · 关系 ${t.relationsExtracted}${t.usedRealLlm ? "" : "（规则降级）"}`}
                    </td>
                  </tr>
                )) : (
                  <tr><td colSpan={4} className="p-6 text-center text-muted-foreground">暂无抽取任务</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div>
          <SectionHeader title="人工复核队列" action={<Badge tone="warning">{reviewQueue ? `${reviewQueue.length} 待处理` : "待处理"}</Badge>} />
          <div className="overflow-hidden border border-border">
            <table className="w-full text-left text-[11px]">
              <thead className="border-b border-border bg-card">
                <tr>{["候选", "类型", "置信度", "操作"].map((h) => (
                  <th key={h} className="p-3 font-bold uppercase tracking-tighter text-muted-foreground">{h}</th>
                ))}</tr>
              </thead>
              <tbody className="divide-y divide-border">
                {reviewQueue && reviewQueue.length > 0 ? reviewQueue.map((item) => (
                  <tr key={item.itemId} className="hover:bg-white/5">
                    <td className="p-3">
                      {item.kind === "entity" ? (
                        <span>{String(item.payload.name)}（{String(item.payload.type)}）</span>
                      ) : (
                        <span>{String(item.payload.source_name)} --[{String(item.payload.relation)}]--&gt; {String(item.payload.target_name)}</span>
                      )}
                    </td>
                    <td className="p-3 text-muted-foreground">{item.kind === "entity" ? "实体" : "关系"}</td>
                    <td className="p-3 font-mono text-primary">{item.confidence.toFixed(3)}</td>
                    <td className="p-3 text-right space-x-1">
                      <Btn variant="outline" onClick={() => handleReview(item.itemId, "approved")} disabled={reviewAction.isPending}>通过</Btn>
                      <Btn variant="ghost" onClick={() => handleReview(item.itemId, "rejected")} disabled={reviewAction.isPending}>驳回</Btn>
                    </td>
                  </tr>
                )) : (
                  <tr><td colSpan={4} className="p-6 text-center text-muted-foreground">暂无待复核项</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {showTaskModal && (
        <ExtractionTaskModal
          onClose={() => setShowTaskModal(false)}
          onSubmit={(candidateId, domain) => {
            createTask.mutate(
              { candidate_id: candidateId || undefined, domain, submitter_id: user?.userId || "" },
              { onSuccess: () => setShowTaskModal(false) }
            );
          }}
          isPending={createTask.isPending}
        />
      )}

      {schemaModal.open && (
        <Modal title="本体 Schema（与知识图谱模块共用同一份定义）" onClose={schemaModal.closeModal}>
          <div className="space-y-4">
            <div className="text-xs text-muted-foreground">抽取引擎只会产出下列本体类型和关系类型范围内的实体与关系。</div>
            <pre className="overflow-auto border border-border bg-card p-4 font-mono text-[11px] leading-relaxed text-foreground/90 max-h-[400px]">
{JSON.stringify(schema || { classes: [], relations: [] }, null, 2)}
            </pre>
            <div className="flex gap-2 justify-end">
              <Btn variant="ghost" onClick={schemaModal.closeModal}>关闭</Btn>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}

function ExtractionTaskModal({ onClose, onSubmit, isPending }: { onClose: () => void; onSubmit: (candidateId: string, domain: string) => void; isPending: boolean }) {
  const [domain, setDomain] = useState("aerospace");
  const [candidateId, setCandidateId] = useState("");
  const { data: candidates, isLoading: candidatesLoading } = useCandidates({ domain, status: "pending", pageSize: 50 });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-full max-w-md border border-border bg-card p-6">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-sm font-bold uppercase tracking-widest">发起抽取任务</h3>
          <button onClick={onClose}><X className="size-4 text-muted-foreground" /></button>
        </div>
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-muted-foreground">领域</label>
            <select value={domain} onChange={(e) => { setDomain(e.target.value); setCandidateId(""); }} className="w-full rounded border border-border bg-white/5 p-2 text-xs">
              <option value="aerospace">航空</option>
              <option value="energy">能源</option>
              <option value="transportation">轨交</option>
              <option value="general">通用</option>
            </select>
          </div>
          <div>
            <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-muted-foreground">候选对象（待处理）</label>
            <select value={candidateId} onChange={(e) => setCandidateId(e.target.value)} className="w-full rounded border border-border bg-white/5 p-2 text-xs">
              <option value="">不指定 · 无候选可抽取时将报错</option>
              {candidates?.items.map((c) => (
                <option key={c.candidateId} value={c.candidateId}>{c.candidateId} · {c.sourceName || c.sourceType}</option>
              ))}
            </select>
            {candidatesLoading && <div className="mt-1 text-[10px] text-muted-foreground">加载候选列表…</div>}
            {!candidatesLoading && candidates && candidates.items.length === 0 && (
              <div className="mt-1 text-[10px] text-muted-foreground">该领域暂无待处理候选，请先在"数据接入"页上传文档或专家录入。</div>
            )}
          </div>
          <Btn variant="primary" onClick={() => onSubmit(candidateId, domain)} disabled={isPending || !candidateId} className="w-full justify-center">
            {isPending ? "提交中…" : "发起抽取"}
          </Btn>
        </div>
      </div>
    </div>
  );
}
