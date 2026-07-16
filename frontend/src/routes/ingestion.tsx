import { createFileRoute } from "@tanstack/react-router";
import { PageHeader, Kpi, SectionHeader, Btn, Badge } from "@/components/panel";
import { Upload, Database, UserSquare2, Globe2, X } from "lucide-react";
import { useState, useCallback } from "react";
import { useDocumentUpload, useExpertInput, useDLQ, useCandidates, useIngestionStats } from "@/hooks/use-ingestion";
import { useCreateExtractionTask } from "@/hooks/use-extraction";
import { useAuth } from "@/lib/auth";

export const Route = createFileRoute("/ingestion")({
  component: Ingestion,
  head: () => ({ meta: [{ title: "数据接入 · Aether PHM" }] }),
});

function Ingestion() {
  const { user } = useAuth();
  const [showUpload, setShowUpload] = useState(false);
  const [showExpert, setShowExpert] = useState(false);
  const { data: stats, isError: statsError, error: statsErrorObj } = useIngestionStats();

  return (
    <div className="animate-in-up p-8">
      {statsError && (
        <div className="mb-4 border border-destructive/50 bg-destructive/10 p-3 text-xs text-destructive">
          统计数据加载失败：{(statsErrorObj as Error)?.message || "无法连接后端服务"}
        </div>
      )}
      <PageHeader
        eyebrow="M01 · Data Ingestion"
        title="数据接入"
        description="面向多源异构数据的统一接入通道：文档、数据库、专家录入与外部标准，产出知识候选对象进入加工流水线。"
        actions={
          <>
            <Btn variant="outline" onClick={() => setShowExpert(true)}>
              专家录入
            </Btn>
            <Btn variant="primary" onClick={() => setShowUpload(true)}>
              上传文档
            </Btn>
          </>
        }
      />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
        <Kpi label="今日入队候选" value={stats ? String(stats.todayCandidates) : "—"} tone="primary" />
        <Kpi label="解析成功率" value={stats?.successRate != null ? `${(stats.successRate * 100).toFixed(1)}%` : "—"} tone="primary" />
        <Kpi label="死信队列" value={stats ? String(stats.dlqCount) : "—"} tone="warning" />
        <Kpi label="累计候选总数" value={stats ? String(stats.totalCandidates) : "—"} tone="primary" />
      </div>

      <div className="mt-8 grid grid-cols-1 gap-8 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <SectionHeader title="采集源" />
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {[
              {
                icon: Upload,
                name: "文档采集 (DocCollector)",
                desc: "目录扫描 / 文档系统 / 邮件附件",
                status: "success" as const,
              },
              {
                icon: Database,
                name: "数据库同步 (DBSyncAgent)",
                desc: "历史台账 · 传感器 CDC/批量",
                status: "success" as const,
              },
              {
                icon: UserSquare2,
                name: "专家录入 (ExpertInputAPI)",
                desc: "在线录入接口 · 结构化模板",
                status: "success" as const,
              },
              {
                icon: Globe2,
                name: "外部标准连接器",
                desc: "GB / ISO / 行业标准同步",
                status: "warning" as const,
              },
            ].map((s) => (
              <div
                key={s.name}
                className="border border-border bg-card p-5 transition hover:border-primary/40"
              >
                <div className="mb-3 flex items-center justify-between">
                  <s.icon className="size-5 text-primary" strokeWidth={1.5} />
                  <Badge tone={s.status}>{s.status === "success" ? "运行中" : "关注"}</Badge>
                </div>
                <div className="text-sm font-bold">{s.name}</div>
                <div className="mt-1 text-[11px] text-muted-foreground">{s.desc}</div>
              </div>
            ))}
          </div>

          <SectionHeader title="候选对象" />
          <CandidatesPanel userId={user?.userId || ""} />
        </div>

        <div>
          <SectionHeader title="死信队列 · km.ingestion.dlq" />
          <DLQPanel />
        </div>
      </div>

      {showUpload && (
        <DocumentUploadModal onClose={() => setShowUpload(false)} userId={user?.userId || ""} />
      )}
      {showExpert && (
        <ExpertInputModal onClose={() => setShowExpert(false)} userId={user?.userId || ""} />
      )}
    </div>
  );
}

function CandidatesPanel({ userId }: { userId: string }) {
  const { data, isLoading, isError, error } = useCandidates({ pageSize: 10 });
  const createTask = useCreateExtractionTask();
  const [triggeredIds, setTriggeredIds] = useState<Record<string, boolean>>({});

  const handleTrigger = useCallback(
    (candidateId: string, domain: string) => {
      createTask.mutate(
        { candidate_id: candidateId, domain, submitter_id: userId },
        { onSuccess: () => setTriggeredIds((prev) => ({ ...prev, [candidateId]: true })) }
      );
    },
    [createTask, userId]
  );

  if (isLoading) {
    return <div className="border border-border bg-card/40 p-4 text-xs text-muted-foreground">加载中…</div>;
  }
  if (isError) {
    return (
      <div className="border border-destructive/50 bg-destructive/10 p-4 text-xs text-destructive">
        候选对象加载失败：{(error as Error)?.message || "无法连接后端服务"}
      </div>
    );
  }
  if (!data || data.items.length === 0) {
    return <div className="border border-border bg-card/40 p-4 text-xs text-muted-foreground">暂无候选对象，上传文档或专家录入后会出现在这里</div>;
  }

  return (
    <div className="overflow-hidden border border-border">
      <table className="w-full text-left text-[11px]">
        <thead className="border-b border-border bg-card">
          <tr>{["候选ID", "来源", "领域", "状态", "操作"].map((h) => (
            <th key={h} className="p-3 font-bold uppercase tracking-tighter text-muted-foreground">{h}</th>
          ))}</tr>
        </thead>
        <tbody className="divide-y divide-border">
          {data.items.map((c) => (
            <tr key={c.candidateId} className="hover:bg-white/5">
              <td className="p-3 font-mono text-primary">{c.candidateId}</td>
              <td className="p-3">{c.sourceName || c.sourceType}</td>
              <td className="p-3 text-muted-foreground">{c.domain}</td>
              <td className="p-3">
                <Badge tone={c.status === "processed" ? "success" : c.status === "failed" ? "danger" : "warning"}>
                  {c.status === "processed" ? "已处理" : c.status === "failed" ? "失败" : c.status === "processing" ? "处理中" : "待处理"}
                </Badge>
              </td>
              <td className="p-3 text-right">
                {c.status === "pending" && (
                  triggeredIds[c.candidateId] ? (
                    <span className="text-[10px] text-muted-foreground">已触发</span>
                  ) : (
                    <Btn variant="outline" onClick={() => handleTrigger(c.candidateId, c.domain)} disabled={createTask.isPending}>触发抽取</Btn>
                  )
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DLQPanel() {
  const { data, isLoading, isError, error } = useDLQ();
  const items = (
    data as
      | {
          items?: Array<{
            candidateId: string;
            domain: string;
            source: string;
            status: string;
            createdAt?: string;
          }>;
        }
      | undefined
  )?.items;

  if (isLoading) {
    return (
      <div className="border border-border bg-card/40 p-4 font-mono text-[11px] text-muted-foreground">
        加载中…
      </div>
    );
  }

  if (isError) {
    return (
      <div className="border border-destructive/50 bg-destructive/10 p-4 font-mono text-[11px] text-destructive">
        队列数据加载失败：{(error as Error)?.message || "无法连接后端服务"}
      </div>
    );
  }

  if (!items || items.length === 0) {
    return (
      <div className="border border-border bg-card/40 p-4 font-mono text-[11px] text-muted-foreground">
        暂无队列数据
      </div>
    );
  }

  return (
    <div className="border border-border bg-card/40 p-4 font-mono text-[11px] leading-relaxed">
      {items.slice(0, 5).map((l, i) => (
        <div key={i} className="border-b border-border/50 py-1.5 last:border-none">
          <span className="text-muted-foreground">{l.createdAt || ""}</span>{" "}
          <span className="text-foreground/90">
            candidate_id={l.candidateId} domain={l.domain} src={l.source} status={l.status}
          </span>
        </div>
      ))}
    </div>
  );
}

function DocumentUploadModal({ onClose, userId }: { onClose: () => void; userId: string }) {
  const upload = useDocumentUpload();
  const [file, setFile] = useState<File | null>(null);
  const [domain, setDomain] = useState("aerospace");
  const [classificationLevel, setClassificationLevel] = useState("internal");

  const handleSubmit = useCallback(() => {
    if (!file) return;
    upload.mutate(
      { file, domain, classificationLevel, submitterId: userId },
      {
        onSuccess: () => {
          onClose();
        },
      },
    );
  }, [file, domain, classificationLevel, userId, upload, onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-full max-w-md border border-border bg-card p-6">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-sm font-bold uppercase tracking-widest">上传文档</h3>
          <button onClick={onClose}>
            <X className="size-4 text-muted-foreground" />
          </button>
        </div>
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
              选择文件
            </label>
            <input
              type="file"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
              className="w-full text-xs"
              accept=".pdf,.docx,.doc,.pptx,.xlsx,.xls,.csv,.txt,.png,.jpg,.jpeg,.md"
            />
          </div>
          <div>
            <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
              领域
            </label>
            <select
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              className="w-full rounded border border-border bg-white/5 p-2 text-xs"
            >
              <option value="aerospace">航空</option>
              <option value="energy">能源</option>
              <option value="transportation">轨交</option>
              <option value="general">通用</option>
            </select>
          </div>
          <div>
            <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
              密级
            </label>
            <select
              value={classificationLevel}
              onChange={(e) => setClassificationLevel(e.target.value)}
              className="w-full rounded border border-border bg-white/5 p-2 text-xs"
            >
              <option value="public">公开</option>
              <option value="internal">内部</option>
              <option value="secret">秘密</option>
              <option value="confidential">机密</option>
            </select>
          </div>
          {upload.isError && (
            <div className="text-xs text-destructive">
              上传失败：{(upload.error as Error)?.message}
            </div>
          )}
          {upload.isSuccess && (
            <div className="text-xs text-success">
              上传成功！候选ID: {(upload.data as { candidateId?: string })?.candidateId}
            </div>
          )}
          <Btn
            variant="primary"
            onClick={handleSubmit}
            disabled={!file || upload.isPending}
            className="w-full justify-center"
          >
            {upload.isPending ? "上传中…" : "提交"}
          </Btn>
        </div>
      </div>
    </div>
  );
}

function ExpertInputModal({ onClose, userId }: { onClose: () => void; userId: string }) {
  const expertInput = useExpertInput();
  const [title, setTitle] = useState("");
  const [domain, setDomain] = useState("aerospace");
  const [type, setType] = useState("rule");
  const [content, setContent] = useState("");

  const handleSubmit = useCallback(() => {
    expertInput.mutate(
      {
        domain,
        type,
        title,
        content: { text: content },
        classification_level: "internal",
        submitter_id: userId,
      },
      {
        onSuccess: () => {
          onClose();
        },
      },
    );
  }, [title, domain, type, content, userId, expertInput, onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-full max-w-md border border-border bg-card p-6">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-sm font-bold uppercase tracking-widest">专家录入</h3>
          <button onClick={onClose}>
            <X className="size-4 text-muted-foreground" />
          </button>
        </div>
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
              标题
            </label>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full rounded border border-border bg-white/5 p-2 text-xs"
              placeholder="知识条目标题"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                领域
              </label>
              <select
                value={domain}
                onChange={(e) => setDomain(e.target.value)}
                className="w-full rounded border border-border bg-white/5 p-2 text-xs"
              >
                <option value="aerospace">航空</option>
                <option value="energy">能源</option>
                <option value="transportation">轨交</option>
                <option value="general">通用</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                类型
              </label>
              <select
                value={type}
                onChange={(e) => setType(e.target.value)}
                className="w-full rounded border border-border bg-white/5 p-2 text-xs"
              >
                <option value="rule">规则</option>
                <option value="entity">实体</option>
                <option value="relation">关系</option>
                <option value="event">事件</option>
              </select>
            </div>
          </div>
          <div>
            <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
              内容
            </label>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              rows={4}
              className="w-full rounded border border-border bg-white/5 p-2 text-xs"
              placeholder="知识内容描述"
            />
          </div>
          {expertInput.isError && (
            <div className="text-xs text-destructive">
              提交失败：{(expertInput.error as Error)?.message}
            </div>
          )}
          <Btn
            variant="primary"
            onClick={handleSubmit}
            disabled={!title || !content || expertInput.isPending}
            className="w-full justify-center"
          >
            {expertInput.isPending ? "提交中…" : "提交"}
          </Btn>
        </div>
      </div>
    </div>
  );
}
