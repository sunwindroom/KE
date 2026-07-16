import { createFileRoute } from "@tanstack/react-router";
import { PageHeader, SectionHeader, Kpi, Btn, Badge } from "@/components/panel";
import { Modal, useModal } from "@/components/modal";
import { useState, useCallback } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";

export const Route = createFileRoute("/rag")({
  component: RAG,
  head: () => ({ meta: [{ title: "RAG 检索增强 · Aether PHM" }] }),
});

function useSemanticSearch() {
  return useMutation({
    mutationFn: (req: { query: string; domain?: string; topK?: number }) =>
      apiClient.post<
        Array<{
          knowledgeId: string;
          title: string;
          snippet: string;
          score: number;
          source: string;
        }>
      >("/rag/search", req),
  });
}

function useCreateIndex() {
  return useMutation({
    mutationFn: (req: { domain: string; embeddingModel?: string }) =>
      apiClient.post<{ indexId: string; status: string }>("/rag/index", req),
  });
}

function useRagStats() {
  return useQuery({
    queryKey: ["rag", "stats"],
    queryFn: () =>
      apiClient.get<{
        totalChunks: number;
        avgLatencyMs: number | null;
        totalQueries: number;
        hitRate: number | null;
      }>("/rag/stats"),
  });
}

function useRunEval() {
  return useMutation({
    mutationFn: (req: { queries: string; domain?: string }) =>
      apiClient.get<{
        queries: Array<{
          query: string;
          hitCount: number;
          latencyMs: number;
          usedRealEmbedding: boolean;
          topScore: number;
        }>;
        summary: { hitRate: number; avgLatencyMs: number; queryCount: number };
      }>("/rag/eval", req),
  });
}

const DEFAULT_EVAL_QUERIES = [
  "GT-40 燃气轮机高温预警处置流程",
  "液压泵密封老化的早期征兆",
  "叶片裂纹寿命预测常用模型",
  "变频器过流保护规则集",
  "冷却回路故障典型传播路径",
];

function RAG() {
  const semanticSearch = useSemanticSearch();
  const createIndex = useCreateIndex();
  const { data: ragStats } = useRagStats();
  const runEval = useRunEval();
  const [searchQuery, setSearchQuery] = useState("");
  const [searchDomain, setSearchDomain] = useState<string | undefined>(undefined);
  const [showCreateIndex, setShowCreateIndex] = useState(false);
  const [newIndexDomain, setNewIndexDomain] = useState("aerospace");
  const evalModal = useModal();

  const handleSearch = useCallback(() => {
    if (!searchQuery.trim()) return;
    semanticSearch.mutate({ query: searchQuery, domain: searchDomain, topK: 10 });
  }, [searchQuery, searchDomain, semanticSearch]);

  const handleCreateIndex = useCallback(() => {
    createIndex.mutate(
      { domain: newIndexDomain, embeddingModel: "bge-m3" },
      { onSuccess: () => setShowCreateIndex(false) },
    );
  }, [newIndexDomain, createIndex]);

  const handleRunEval = useCallback(() => {
    runEval.mutate({ queries: DEFAULT_EVAL_QUERIES.join(",") });
  }, [runEval]);

  const results = semanticSearch.data as
    | Array<{ knowledgeId: string; title: string; snippet: string; score: number; source: string }>
    | undefined;

  return (
    <div className="animate-in-up p-8">
      <PageHeader
        eyebrow="M05 · Retrieval Augmented Generation"
        title="RAG 检索增强"
        description="向量库 + 全文关键词的混合检索，配合大模型生成与引用回溯，为问答提供高置信度证据链。"
        actions={
          <>
            <Btn variant="outline" onClick={evalModal.openModal}>
              检索评测
            </Btn>
            <Btn variant="primary" onClick={() => setShowCreateIndex(true)}>
              新建索引
            </Btn>
          </>
        }
      />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
        <Kpi
          label="向量索引块"
          value={ragStats ? String(ragStats.totalChunks) : "—"}
          tone="primary"
        />
        <Kpi
          label="平均召回延迟"
          value={ragStats?.avgLatencyMs != null ? `${ragStats.avgLatencyMs}ms` : "—"}
          tone="primary"
        />
        <Kpi
          label="历史查询命中率"
          value={ragStats?.hitRate != null ? `${(ragStats.hitRate * 100).toFixed(1)}%` : "—"}
          tone="primary"
        />
        <Kpi
          label="累计查询次数"
          value={ragStats ? String(ragStats.totalQueries) : "—"}
          tone="primary"
        />
      </div>

      <div className="mt-8 grid grid-cols-1 gap-8 xl:grid-cols-3">
        <div className="xl:col-span-2">
          <SectionHeader title="语义检索" />
          <div className="flex gap-3 mb-4">
            <input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              placeholder="输入检索查询…"
              className="flex-1 rounded border border-border bg-white/5 p-2 text-xs focus:border-primary/50 focus:outline-none"
            />
            <select
              value={searchDomain || ""}
              onChange={(e) => setSearchDomain(e.target.value || undefined)}
              className="rounded border border-border bg-white/5 px-2 py-1 text-xs"
            >
              <option value="">全部领域</option>
              <option value="aerospace">航空</option>
              <option value="energy">能源</option>
              <option value="transportation">轨交</option>
              <option value="general">通用</option>
            </select>
            <Btn variant="primary" onClick={handleSearch} disabled={semanticSearch.isPending}>
              {semanticSearch.isPending ? "检索中…" : "检索"}
            </Btn>
          </div>

          {results && results.length > 0 && (
            <div className="space-y-2">
              {results.map((r) => (
                <div key={r.knowledgeId} className="border border-border bg-card/50 p-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold">{r.title}</span>
                    <span className="font-mono text-[10px] text-primary">
                      score: {r.score.toFixed(3)}
                    </span>
                  </div>
                  <div className="mt-1 text-[11px] text-muted-foreground line-clamp-2">
                    {r.snippet}
                  </div>
                  <div className="mt-1 font-mono text-[9px] text-muted-foreground">
                    ID: {r.knowledgeId} · 来源: {r.source === "vector" ? "向量检索" : "关键词检索"}
                  </div>
                </div>
              ))}
            </div>
          )}

          {results && results.length === 0 && (
            <div className="text-xs text-muted-foreground">未找到相关结果</div>
          )}

          <SectionHeader title="检索链路" />
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            {[
              { s: "Vector Search", d: "Milvus 向量近邻检索" },
              { s: "Keyword Fallback", d: "标题/摘要关键词兜底" },
              { s: "Generate & Cite", d: "大模型生成 + 引用回溯" },
            ].map((x, i) => (
              <div key={x.s} className="border border-border bg-card p-4">
                <div className="font-mono text-[9px] text-muted-foreground">STAGE {i + 1}</div>
                <div className="mt-1 text-xs font-bold">{x.s}</div>
                <div className="mt-1 text-[10px] text-muted-foreground">{x.d}</div>
              </div>
            ))}
          </div>
        </div>

        <div>
          <SectionHeader title="索引配置" action={<Badge tone="primary">bge-m3</Badge>} />
          <div className="space-y-3 border border-border bg-card/40 p-4 text-xs">
            {[
              ["Embedding", "bge-m3 (1024-d)"],
              ["Vector DB", "Milvus · COSINE"],
              ["Chunk Size", "512 / 128 overlap"],
              ["Fallback", "关键词检索 + 哈希伪向量"],
            ].map(([k, v]) => (
              <div
                key={k}
                className="flex items-center justify-between border-b border-border/50 pb-2 last:border-none"
              >
                <span className="text-muted-foreground">{k}</span>
                <span className="font-mono text-foreground">{v}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {showCreateIndex && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="w-full max-w-md border border-border bg-card p-6">
            <h3 className="mb-4 text-sm font-bold uppercase tracking-widest">新建索引</h3>
            <div className="space-y-4">
              <div>
                <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                  领域
                </label>
                <select
                  value={newIndexDomain}
                  onChange={(e) => setNewIndexDomain(e.target.value)}
                  className="w-full rounded border border-border bg-white/5 p-2 text-xs"
                >
                  <option value="aerospace">航空</option>
                  <option value="energy">能源</option>
                  <option value="transportation">轨交</option>
                  <option value="general">通用</option>
                </select>
              </div>
              {createIndex.isError && (
                <div className="text-xs text-destructive">
                  创建失败：{(createIndex.error as Error)?.message}
                </div>
              )}
              {createIndex.isSuccess && (
                <div className="text-xs text-success">索引任务已提交，正在后台构建中</div>
              )}
              <div className="flex gap-2 justify-end">
                <Btn variant="ghost" onClick={() => setShowCreateIndex(false)}>
                  取消
                </Btn>
                <Btn variant="primary" onClick={handleCreateIndex} disabled={createIndex.isPending}>
                  {createIndex.isPending ? "创建中…" : "创建"}
                </Btn>
              </div>
            </div>
          </div>
        </div>
      )}

      {evalModal.open && (
        <Modal title="检索评测" onClose={evalModal.closeModal}>
          <div className="space-y-4">
            <div className="text-xs text-muted-foreground">
              对当前检索管线运行一组示例查询，测量真实的命中率与延迟。
              (未接入人工标注的相关性判定集，因此不展示 Recall/MRR 等需要 ground truth
              的指标，避免呈现编造数字。)
            </div>
            {runEval.data ? (
              <div className="overflow-hidden border border-border">
                <table className="w-full text-left text-[11px]">
                  <thead className="border-b border-border bg-card">
                    <tr>
                      {["查询", "命中数", "延迟", "使用真实向量"].map((h) => (
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
                    {runEval.data.queries.map((r) => (
                      <tr key={r.query} className="hover:bg-white/5">
                        <td className="p-3 font-medium">{r.query}</td>
                        <td className="p-3 font-mono text-primary">{r.hitCount}</td>
                        <td className="p-3 font-mono text-muted-foreground">{r.latencyMs}ms</td>
                        <td className="p-3">
                          <Badge tone={r.usedRealEmbedding ? "success" : "warning"}>
                            {r.usedRealEmbedding ? "是" : "降级"}
                          </Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot className="border-t border-border bg-card/50">
                    <tr>
                      <td className="p-3 font-bold">汇总</td>
                      <td className="p-3 font-mono text-primary" colSpan={3}>
                        命中率 {(runEval.data.summary.hitRate * 100).toFixed(1)}% · 平均延迟{" "}
                        {runEval.data.summary.avgLatencyMs}ms
                      </td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            ) : (
              <div className="text-xs text-muted-foreground">尚未运行评测</div>
            )}
            <div className="flex gap-2 justify-end">
              <Btn variant="ghost" onClick={evalModal.closeModal}>
                关闭
              </Btn>
              <Btn variant="primary" onClick={handleRunEval} disabled={runEval.isPending}>
                {runEval.isPending ? "评测运行中…" : "运行评测"}
              </Btn>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
