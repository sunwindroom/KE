import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowUpRight, Activity, CheckCircle2, Sparkles, Search } from "lucide-react";
import { Kpi, SectionHeader, Btn, Badge } from "@/components/panel";
import { GraphPreview } from "@/components/graph-preview";
import { useState, useCallback } from "react";
import { useKnowledgeSearch } from "@/hooks/use-knowledge";
import { useQA } from "@/hooks/use-qa";
import { useGovernanceStats } from "@/hooks/use-governance";

export const Route = createFileRoute("/")({
  component: Dashboard,
  head: () => ({
    meta: [
      { title: "工作台 · Aether PHM" },
      { name: "description", content: "PHM 知识工程平台工作台概览：知识条目、待审核任务、图谱规模与问答活跃度。" },
    ],
  }),
});

function Dashboard() {
  const [quickQuery, setQuickQuery] = useState("");
  const { data: governanceStats } = useGovernanceStats();
  const { data: knowledgeData } = useKnowledgeSearch({ keyword: quickQuery || undefined, pageSize: 5 });
  const { askStream, isStreaming, streamingText, stopStream } = useQA();

  const totalKnowledge = governanceStats?.totalKnowledgeCount;
  const growth = governanceStats?.growthLast30Days;

  const knowledgeItems = knowledgeData?.items;

  const handleQuickAsk = useCallback(() => {
    if (!quickQuery.trim()) return;
    askStream(quickQuery);
  }, [quickQuery, askStream]);

  return (
    <div className="animate-in-up space-y-8 p-8">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Kpi label="知识条目总数" value={totalKnowledge ? String(totalKnowledge) : "—"} meta={growth ? `+${growth}` : undefined} tone="success" />
        <Kpi label="待审核实体" value="—" tone="warning" />
        <Kpi label="图谱节点 / 关系" value="—" tone="primary" />
        <Kpi label="问答调用 (24H)" value="—" tone="primary" />
      </div>

      <div className="grid grid-cols-1 gap-8 xl:grid-cols-12">
        <div className="space-y-8 xl:col-span-7">
          <section>
            <SectionHeader
              title="知识搜索"
              action={
                <Link to="/rag">
                  <Btn variant="outline">高级搜索 <ArrowUpRight className="size-3" /></Btn>
                </Link>
              }
            />
            <div className="flex gap-3 mb-4">
              <div className="relative flex-1">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground/60" />
                <input
                  value={quickQuery}
                  onChange={(e) => setQuickQuery(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleQuickAsk()}
                  placeholder="搜索知识条目、实体或指令…"
                  className="w-full rounded border border-border bg-white/5 py-2 pl-8 pr-3 text-xs focus:border-primary/50 focus:outline-none"
                />
              </div>
              <Btn variant="primary" onClick={handleQuickAsk} disabled={!quickQuery.trim() || isStreaming}>
                {isStreaming ? "回答中…" : "搜索"}
              </Btn>
            </div>
            {isStreaming && streamingText && (
              <div className="border border-border bg-card p-4 text-sm leading-relaxed mb-4">
                {streamingText}
                <span className="inline-block h-4 w-0.5 animate-pulse bg-primary ml-0.5" />
              </div>
            )}
            {knowledgeItems && knowledgeItems.length > 0 && (
              <div className="space-y-2">
                {knowledgeItems.map((item) => (
                  <div key={item.knowledgeId} className="flex items-center justify-between border border-border bg-card/50 p-3">
                    <div className="min-w-0 flex-1">
                      <div className="text-xs font-bold">{item.title}</div>
                      <div className="mt-0.5 text-[10px] text-muted-foreground truncate">{item.summary}</div>
                    </div>
                    <div className="ml-3 flex items-center gap-2">
                      <Badge tone="primary">{item.domain}</Badge>
                      <Badge tone={item.type === "rule" ? "warning" : "default"}>{item.type}</Badge>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section>
            <SectionHeader
              title="摄取流水线状态"
              action={
                <Link to="/ingestion">
                  <Btn variant="outline">查看全部 <ArrowUpRight className="size-3" /></Btn>
                </Link>
              }
            />
            <div className="space-y-2">
              {[
                { name: "故障诊断手册抽取_V3", id: "PIPE-9284", pct: 85, status: "running" as const, meta: "进度 85.2%" },
                { name: "传感器实时流 · 燃气轮机", id: "PIPE-9101", pct: 42, status: "running" as const, meta: "142 KB/s" },
                { name: "结构化传感器日志映射", id: "PIPE-9102", pct: 100, status: "success" as const, meta: "已完成 · 1.2m" },
                { name: "外部标准规范同步", id: "PIPE-9081", pct: 0, status: "paused" as const, meta: "已暂停" },
              ].map((p) => (
                <div key={p.id} className="flex items-center gap-4 border border-border bg-card/50 p-3">
                  <div className={`grid size-8 place-items-center rounded border ${
                    p.status === "success" ? "border-success/30 bg-success/10"
                    : p.status === "running" ? "border-primary/30 bg-primary/10"
                    : "border-border bg-white/5"
                  }`}>
                    {p.status === "success"
                      ? <CheckCircle2 className="size-3.5 text-success" />
                      : p.status === "running"
                      ? <span className="size-1.5 animate-pulse rounded-full bg-primary" />
                      : <span className="size-1.5 rounded-full bg-muted-foreground" />}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-xs font-bold">{p.name}</div>
                    <div className="mt-0.5 font-mono text-[10px] text-muted-foreground">ID: {p.id} · {p.meta}</div>
                  </div>
                  <div className="h-1 w-32 overflow-hidden rounded-full bg-white/5">
                    <div
                      className={`h-full ${p.status === "success" ? "bg-success" : "bg-primary"}`}
                      style={{ width: `${p.pct}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </section>
        </div>

        <div className="flex flex-col xl:col-span-5">
          <SectionHeader
            title="实时知识图谱预览"
            action={<span className="font-mono text-[10px] text-muted-foreground">LIVE</span>}
          />
          <div className="relative flex-1 overflow-hidden border border-border bg-card/30 grid-bg min-h-[420px]">
            <div className="absolute left-4 top-4 z-10 space-y-2">
              {[
                { c: "bg-primary", l: "核心组件" },
                { c: "bg-graph-2", l: "故障模式" },
                { c: "bg-graph-3", l: "维修策略" },
                { c: "bg-graph-4", l: "传感器参数" },
              ].map((x) => (
                <div key={x.l} className="flex items-center gap-2 border border-border bg-background/70 px-2 py-1 text-[10px] backdrop-blur">
                  <span className={`size-2 rounded-full ${x.c}`} />
                  {x.l}
                </div>
              ))}
            </div>
            <GraphPreview className="absolute inset-0 h-full w-full" />
            <div className="absolute bottom-4 right-4">
              <Link to="/graph">
                <Btn variant="primary">
                  <Sparkles className="size-3" /> 进入图谱空间
                </Btn>
              </Link>
            </div>
          </div>

          <div className="mt-4 grid grid-cols-3 gap-2">
            {[
              { k: "本体类", v: "126" }, { k: "关系类型", v: "48" }, { k: "跨域链接", v: "1,842" },
            ].map((x) => (
              <div key={x.k} className="border border-border bg-card/40 p-3">
                <div className="text-[10px] uppercase tracking-widest text-muted-foreground">{x.k}</div>
                <div className="mt-1 font-mono text-lg font-bold">{x.v}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-8 border-t border-border pt-8 xl:grid-cols-3">
        <div className="xl:col-span-2">
          <SectionHeader title="智能问答摘录" action={<Badge tone="success">RAG · Enabled</Badge>} />
          <div className="space-y-4 border border-border bg-card p-6 shadow-2xl">
            <div className="flex gap-3">
              <div className="grid size-8 shrink-0 place-items-center rounded border border-border bg-white/5 font-mono text-[10px] text-muted-foreground">U</div>
              <div className="rounded bg-white/5 px-3 py-2 text-xs">如何处理 GT-40 燃气轮机的高温预警信号？</div>
            </div>
            <div className="flex gap-3">
              <div className="grid size-8 shrink-0 place-items-center rounded border border-primary/40 bg-primary/10 font-mono text-[10px] font-bold text-primary">AI</div>
              <div className="space-y-3">
                <div className="text-xs leading-relaxed">
                  根据知识库检索，<span className="text-primary">液压系统 YX-90</span> 的高温预警主要由冷却回路过滤器堵塞引起
                  （置信度 <span className="font-mono">0.94</span>）。建议按 <span className="underline decoration-primary/50">二级深度排查流程</span> 优先检查传感器 <span className="font-mono">SN-77203</span>。
                </div>
              </div>
            </div>
            <div className="relative">
              <input
                type="text"
                placeholder="继续追问…"
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    const val = (e.target as HTMLInputElement).value;
                    if (val.trim()) askStream(val);
                  }
                }}
                className="w-full border border-border bg-white/5 p-3 pr-16 text-xs focus:border-primary/50 focus:outline-none"
              />
              <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 font-mono text-[10px] text-muted-foreground">ENTER ⏎</span>
            </div>
          </div>
        </div>

        <div>
          <SectionHeader title="系统事件流" action={<Activity className="size-3.5 text-muted-foreground" />} />
          <div className="space-y-3 border border-border bg-card/50 p-4">
            {[
              { t: "12:04", txt: "本体版本 v3.2.1 已发布", tone: "success" as const },
              { t: "11:58", txt: "跨域链接检测：航空 ↔ 能源 · 12 处", tone: "primary" as const },
              { t: "11:47", txt: "冲突仲裁：故障模式 F-201 存在冲突", tone: "warning" as const },
              { t: "11:31", txt: "微调任务 FT-018 完成 · 准确率 92.4%", tone: "success" as const },
              { t: "11:12", txt: "接入死信队列新增 3 条待处理", tone: "warning" as const },
            ].map((e) => (
              <div key={e.t} className="flex items-start gap-3 text-xs">
                <span className="mt-0.5 font-mono text-[10px] text-muted-foreground">{e.t}</span>
                <Badge tone={e.tone}>{e.tone.toUpperCase()}</Badge>
                <span className="flex-1 text-foreground/90">{e.txt}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
