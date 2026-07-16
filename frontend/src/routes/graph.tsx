import { createFileRoute } from "@tanstack/react-router";
import { PageHeader, SectionHeader, Btn, Badge } from "@/components/panel";
import { Modal, useModal } from "@/components/modal";
import { Search, Layers, Filter, Maximize2 } from "lucide-react";
import { useState, useCallback, useRef, useEffect } from "react";
import { useGraphSubgraph, useGraphEntity } from "@/hooks/use-graph";
import { GraphRenderer } from "@/components/graph-renderer";

export const Route = createFileRoute("/graph")({
  component: GraphView,
  head: () => ({ meta: [{ title: "知识图谱可视化 · Aether PHM" }] }),
});

const DOMAIN_OPTIONS: Array<{ code: string; label: string }> = [
  { code: "energy", label: "能源" },
  { code: "aerospace", label: "航空" },
  { code: "transportation", label: "轨交" },
  { code: "general", label: "通用" },
];

const LAYOUT_OPTIONS: Array<{ id: "force" | "dagre"; name: string; desc: string }> = [
  { id: "force", name: "力导向布局 (Force)", desc: "节点间引力/斥力自动排列" },
  { id: "dagre", name: "层次布局 (Dagre)", desc: "按层级从上到下排列" },
];

function toGraphML(
  nodes: Array<{ id: string; name: string; type: string }>,
  edges: Array<{ source: string; target: string; relation: string }>,
) {
  const escape = (s: string) =>
    s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const nodeXml = nodes
    .map(
      (n) =>
        `    <node id="${escape(n.id)}"><data key="name">${escape(n.name)}</data><data key="type">${escape(n.type)}</data></node>`,
    )
    .join("\n");
  const edgeXml = edges
    .map(
      (e, i) =>
        `    <edge id="e${i}" source="${escape(e.source)}" target="${escape(e.target)}"><data key="relation">${escape(e.relation)}</data></edge>`,
    )
    .join("\n");
  return `<?xml version="1.0" encoding="UTF-8"?>
<graphml xmlns="http://graphml.graphdrawing.org/xmlns">
  <key id="name" for="node" attr.name="name" attr.type="string"/>
  <key id="type" for="node" attr.name="type" attr.type="string"/>
  <key id="relation" for="edge" attr.name="relation" attr.type="string"/>
  <graph id="G" edgedefault="directed">
${nodeXml}
${edgeXml}
  </graph>
</graphml>`;
}

function downloadBlob(content: string, filename: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function GraphView() {
  const [domain, setDomain] = useState<string | undefined>(undefined);
  const [depth, setDepth] = useState(2);
  const [layout, setLayout] = useState<"force" | "dagre">("force");
  const [selectedEntityId, setSelectedEntityId] = useState<string | undefined>(undefined);
  const [searchQuery, setSearchQuery] = useState("");
  const exportModal = useModal();
  const layoutModal = useModal();
  const [isFullscreen, setIsFullscreen] = useState(false);
  const graphContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onFullscreenChange = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", onFullscreenChange);
    return () => document.removeEventListener("fullscreenchange", onFullscreenChange);
  }, []);

  const { data: graphData, isLoading: graphLoading } = useGraphSubgraph({
    centerEntity: searchQuery || undefined,
    depth,
    domain,
  });

  const { data: entityDetail } = useGraphEntity(selectedEntityId);

  const handleNodeClick = useCallback((nodeId: string) => {
    setSelectedEntityId(nodeId);
  }, []);

  return (
    <div className="animate-in-up p-8">
      <PageHeader
        eyebrow="M09 · Graph Visualization"
        title="知识图谱可视化"
        description="面向工程师的交互式图谱空间，支持类型过滤、多跳展开、路径分析与子图导出。"
        actions={
          <>
            <Btn variant="outline" onClick={exportModal.openModal}>
              导出子图
            </Btn>
            <Btn
              variant="primary"
              onClick={() => {
                if (graphContainerRef.current) {
                  if (document.fullscreenElement) {
                    document.exitFullscreen();
                  } else {
                    graphContainerRef.current.requestFullscreen();
                  }
                }
              }}
            >
              {isFullscreen ? "退出全屏" : "进入全屏"}
            </Btn>
          </>
        }
      />

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-4">
        <aside className="space-y-6 xl:col-span-1">
          <div>
            <SectionHeader
              title="过滤器"
              action={<Filter className="size-3.5 text-muted-foreground" />}
            />
            <div className="space-y-3 border border-border bg-card/40 p-4">
              <div>
                <div className="mb-2 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                  领域
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {DOMAIN_OPTIONS.map((d) => (
                    <button
                      key={d.code}
                      onClick={() => setDomain(domain === d.code ? undefined : d.code)}
                      className={`rounded border px-2 py-1 text-[10px] transition ${
                        domain === d.code
                          ? "border-primary/40 bg-primary/10 text-primary"
                          : "border-border hover:border-primary/40 hover:text-primary"
                      }`}
                    >
                      {d.label}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <div className="mb-2 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                  展开深度
                </div>
                <input
                  type="range"
                  min={1}
                  max={4}
                  value={depth}
                  onChange={(e) => setDepth(Number(e.target.value))}
                  className="w-full accent-primary"
                />
                <div className="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
                  <span>1</span>
                  <span>2</span>
                  <span>3</span>
                  <span>4</span>
                </div>
              </div>
            </div>
          </div>

          <div>
            <SectionHeader
              title="节点检查器"
              action={selectedEntityId ? <Badge tone="primary">已选中</Badge> : undefined}
            />
            <div className="space-y-2 border border-border bg-card/40 p-4 text-[11px]">
              {entityDetail ? (
                <>
                  <div className="flex items-center justify-between border-b border-border/50 pb-1.5">
                    <span className="text-muted-foreground">ID</span>
                    <span className="font-mono text-foreground">{entityDetail.entityId}</span>
                  </div>
                  <div className="flex items-center justify-between border-b border-border/50 pb-1.5">
                    <span className="text-muted-foreground">名称</span>
                    <span className="font-mono text-foreground">{entityDetail.name}</span>
                  </div>
                  <div className="flex items-center justify-between border-b border-border/50 pb-1.5">
                    <span className="text-muted-foreground">类型</span>
                    <span className="font-mono text-foreground">{entityDetail.type}</span>
                  </div>
                  {entityDetail.relations.map((r, i) => (
                    <div
                      key={i}
                      className="flex items-center justify-between border-b border-border/50 pb-1.5 last:border-none"
                    >
                      <span className="text-muted-foreground">{r.relation}</span>
                      <span className="font-mono text-primary">{r.target}</span>
                    </div>
                  ))}
                </>
              ) : (
                <div className="text-muted-foreground">点击图谱节点查看详情</div>
              )}
            </div>
          </div>
        </aside>

        <div className="xl:col-span-3">
          <div className="mb-4 flex items-center justify-between">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground/60" />
              <input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="搜索节点 / 关系"
                className="w-80 rounded border border-border bg-white/5 py-1.5 pl-8 pr-3 text-xs focus:border-primary/50 focus:outline-none"
              />
            </div>
            <div className="flex gap-2">
              <Btn variant="ghost" onClick={layoutModal.openModal}>
                <Layers className="size-3" /> 布局
              </Btn>
              <Btn variant="outline" onClick={exportModal.openModal}>
                保存视图
              </Btn>
            </div>
          </div>

          <div
            ref={graphContainerRef}
            className="relative min-h-[600px] overflow-hidden border border-border bg-card/30 grid-bg"
          >
            {graphLoading ? (
              <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
                加载图谱数据…
              </div>
            ) : graphData && graphData.nodes.length > 0 ? (
              <GraphRenderer
                nodes={graphData.nodes}
                edges={graphData.edges}
                onNodeClick={handleNodeClick}
                layout={layout}
                className="absolute inset-0 h-full w-full"
              />
            ) : (
              <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
                {searchQuery ? "未找到匹配的图谱数据" : "输入搜索词加载图谱"}
              </div>
            )}
            {graphData && (
              <div className="absolute bottom-3 left-3 flex items-center gap-3 rounded border border-border bg-background/80 px-3 py-1.5 font-mono text-[10px] text-muted-foreground backdrop-blur">
                <span>节点 {graphData.nodes.length}</span>
                <span>关系 {graphData.edges.length}</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {exportModal.open && (
        <Modal title="导出子图" onClose={exportModal.closeModal}>
          <div className="space-y-4">
            <div className="text-xs text-muted-foreground">
              将当前图谱视图导出为 JSON 或 GraphML 格式。
            </div>
            <div className="grid grid-cols-2 gap-3">
              <button
                onClick={() => {
                  const data = graphData ? JSON.stringify(graphData, null, 2) : "{}";
                  downloadBlob(data, "subgraph.json", "application/json");
                }}
                className="border border-border bg-card p-4 text-center hover:border-primary/40 transition"
              >
                <div className="text-xs font-bold">JSON</div>
                <div className="mt-1 text-[10px] text-muted-foreground">结构化节点与关系数据</div>
              </button>
              <button
                onClick={() => {
                  const xml = toGraphML(graphData?.nodes ?? [], graphData?.edges ?? []);
                  downloadBlob(xml, "subgraph.graphml", "application/xml");
                }}
                className="border border-border bg-card p-4 text-center hover:border-primary/40 transition"
              >
                <div className="text-xs font-bold">GraphML</div>
                <div className="mt-1 text-[10px] text-muted-foreground">通用图数据交换格式</div>
              </button>
            </div>
            <div className="flex gap-2 justify-end">
              <Btn variant="ghost" onClick={exportModal.closeModal}>
                关闭
              </Btn>
            </div>
          </div>
        </Modal>
      )}

      {layoutModal.open && (
        <Modal title="布局设置" onClose={layoutModal.closeModal}>
          <div className="space-y-4">
            <div className="text-xs text-muted-foreground">选择图谱的布局算法。</div>
            <div className="space-y-2">
              {LAYOUT_OPTIONS.map((l) => (
                <button
                  key={l.id}
                  onClick={() => setLayout(l.id)}
                  className={`w-full border p-3 text-left transition ${layout === l.id ? "border-primary/40 bg-primary/10" : "border-border hover:border-primary/40"}`}
                >
                  <div className="text-xs font-bold">{l.name}</div>
                  <div className="mt-0.5 text-[10px] text-muted-foreground">{l.desc}</div>
                </button>
              ))}
            </div>
            <div className="flex gap-2 justify-end">
              <Btn variant="ghost" onClick={layoutModal.closeModal}>
                关闭
              </Btn>
              <Btn variant="primary" onClick={layoutModal.closeModal}>
                应用
              </Btn>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
