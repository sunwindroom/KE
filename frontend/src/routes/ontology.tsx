import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { PageHeader, SectionHeader, Kpi, Btn, Badge } from "@/components/panel";
import { GraphPreview } from "@/components/graph-preview";
import { Modal, useModal } from "@/components/modal";
import { X } from "lucide-react";
import { useState, useCallback } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { useAuth } from "@/lib/auth";
import { useGraphStats } from "@/hooks/use-graph";

export const Route = createFileRoute("/ontology")({
  component: Ontology,
  head: () => ({ meta: [{ title: "本体与知识图谱 · Aether PHM" }] }),
});

function useOntologyClasses() {
  return useQuery({
    queryKey: ["ontology", "classes"],
    queryFn: () =>
      apiClient.get<
        Array<{ className: string; labelZh: string; properties: string; instanceCount?: number }>
      >("/ontology/classes"),
  });
}

function useOntologyRelations() {
  return useQuery({
    queryKey: ["ontology", "relations"],
    queryFn: () =>
      apiClient.get<Array<{ name: string; domain: string; range: string }>>("/ontology/relations"),
  });
}

function usePublishOntology() {
  return useMutation({
    mutationFn: (req: { version: string; comment?: string; publisher_id: string }) =>
      apiClient.post<{ version: string; status: string }>("/ontology/publish", req),
  });
}

const CLASSES = [
  { c: "Equipment", zh: "装备", props: "id, name, model, domain, level" },
  { c: "Component", zh: "部件", props: "id, name, parent_id, type" },
  { c: "FailureMode", zh: "故障模式", props: "id, mechanism, severity" },
  { c: "Symptom", zh: "征兆", props: "id, parameter, detection_method" },
  { c: "DiagnosisMethod", zh: "诊断方法", props: "id, principle" },
  { c: "HealthState", zh: "健康状态", props: "id, threshold_definition" },
  { c: "RULModel", zh: "寿命预测模型", props: "id, applicable_type" },
  { c: "MaintenanceStrategy", zh: "维修策略", props: "id, description" },
];

const RELS = [
  { r: "BELONGS_TO", from: "Component", to: "Equipment" },
  { r: "OCCURS_IN", from: "FailureMode", to: "Component" },
  { r: "MANIFESTS_AS", from: "FailureMode", to: "Symptom" },
  { r: "LEADS_TO", from: "FailureMode", to: "FailureMode" },
  { r: "RESOLVED_BY", from: "FailureMode", to: "MaintenanceStrategy" },
  { r: "DETECTED_BY", from: "Symptom", to: "DiagnosisMethod" },
  { r: "APPLIES_MODEL", from: "Component", to: "RULModel" },
];

function Ontology() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [showPublish, setShowPublish] = useState(false);
  const [showCrossDomain, setShowCrossDomain] = useState(false);
  const [versionInput, setVersionInput] = useState("v3.3.0");
  const [commentInput, setCommentInput] = useState("");
  const owlModal = useModal();
  const { data: apiClasses, isLoading: classesLoading } = useOntologyClasses();
  const { data: apiRelations } = useOntologyRelations();
  const { data: graphStats } = useGraphStats();
  const publishOntology = usePublishOntology();

  const displayClasses =
    apiClasses && apiClasses.length > 0
      ? apiClasses.map((c) => ({ c: c.className, zh: c.labelZh, props: c.properties }))
      : CLASSES;

  const displayRels =
    apiRelations && apiRelations.length > 0
      ? apiRelations.map((r) => ({ r: r.name, from: r.domain, to: r.range }))
      : RELS;

  const handlePublish = useCallback(() => {
    publishOntology.mutate({
      version: versionInput,
      comment: commentInput || undefined,
      publisher_id: user?.userId || "",
    });
  }, [publishOntology, versionInput, commentInput, user]);

  return (
    <div className="animate-in-up p-8">
      <PageHeader
        eyebrow="M03 · Ontology & Graph"
        title="本体与知识图谱"
        description="核心层 + 领域扩展层的本体定义，与图实例化引擎、跨域关联器及质量评估协同，构建可追溯的 PHM 知识图谱。"
        actions={
          <>
            <Btn variant="outline" onClick={owlModal.openModal}>
              导出 OWL
            </Btn>
            <Btn variant="primary" onClick={() => setShowPublish(true)}>
              发布新版本
            </Btn>
          </>
        }
      />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
        <Kpi label="本体类" value={String(displayClasses.length)} tone="primary" />
        <Kpi label="关系类型" value={String(displayRels.length)} tone="primary" />
        <Kpi
          label="图谱节点"
          value={graphStats ? String(graphStats.totalNodes) : "—"}
          tone="success"
        />
        <Kpi
          label="图谱关系"
          value={graphStats ? String(graphStats.totalEdges) : "—"}
          tone="success"
        />
      </div>

      <div className="mt-8 grid grid-cols-1 gap-8 xl:grid-cols-12">
        <div className="xl:col-span-5">
          <SectionHeader title="核心类定义" />
          <div className="overflow-hidden border border-border">
            <table className="w-full text-left text-[11px]">
              <thead className="border-b border-border bg-card">
                <tr>
                  {["Class", "名称", "关键属性"].map((h) => (
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
                {displayClasses.map((c) => (
                  <tr key={c.c} className="hover:bg-white/5">
                    <td className="p-3 font-mono text-primary">{c.c}</td>
                    <td className="p-3">{c.zh}</td>
                    <td className="p-3 font-mono text-[10px] text-muted-foreground">{c.props}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <SectionHeader title="关系类型" action={<Badge tone="primary">v3.2.1</Badge>} />
          <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
            {displayRels.map((r) => (
              <div
                key={r.r}
                className="flex items-center justify-between border border-border bg-card/50 p-3 text-[11px]"
              >
                <span className="font-mono text-primary">{r.r}</span>
                <span className="text-muted-foreground">
                  {r.from} <span className="text-primary">→</span> {r.to}
                </span>
              </div>
            ))}
          </div>
        </div>

        <div className="xl:col-span-7">
          <SectionHeader title="图谱质量评估" action={<Badge tone="success">健康</Badge>} />
          <div className="grid grid-cols-3 gap-3">
            <Kpi
              label="完整性"
              value={graphStats && graphStats.totalNodes > 0 ? "100%" : "—"}
              tone="success"
            />
            <Kpi label="一致性" value={graphStats ? "100%" : "—"} tone="success" />
            <Kpi label="准确性" value="—" tone="primary" />
          </div>

          <div className="mt-4 border border-border bg-card/30 grid-bg relative min-h-[380px] overflow-hidden">
            <GraphPreview className="absolute inset-0 h-full w-full" />
            <div className="absolute bottom-3 right-3 flex gap-2">
              <Btn variant="outline" onClick={() => setShowCrossDomain(true)}>
                跨域关联
              </Btn>
              <Btn variant="primary" onClick={() => navigate({ to: "/graph" })}>
                图谱空间
              </Btn>
            </div>
          </div>
        </div>
      </div>

      {showPublish && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="w-full max-w-md border border-border bg-card p-6">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-sm font-bold uppercase tracking-widest">发布新版本</h3>
              <button onClick={() => setShowPublish(false)}>
                <X className="size-4 text-muted-foreground" />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                  版本号
                </label>
                <input
                  value={versionInput}
                  onChange={(e) => setVersionInput(e.target.value)}
                  className="w-full rounded border border-border bg-white/5 p-2 text-xs"
                />
              </div>
              <div>
                <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                  备注
                </label>
                <textarea
                  rows={2}
                  value={commentInput}
                  onChange={(e) => setCommentInput(e.target.value)}
                  className="w-full rounded border border-border bg-white/5 p-2 text-xs"
                  placeholder="版本变更说明"
                />
              </div>
              {publishOntology.isError && (
                <div className="text-xs text-destructive">
                  发布失败：{(publishOntology.error as Error)?.message}
                </div>
              )}
              {publishOntology.isSuccess && <div className="text-xs text-success">发布成功！</div>}
              <div className="flex gap-2 justify-end">
                <Btn variant="ghost" onClick={() => setShowPublish(false)}>
                  取消
                </Btn>
                <Btn
                  variant="primary"
                  onClick={handlePublish}
                  disabled={publishOntology.isPending || !versionInput}
                >
                  {publishOntology.isPending ? "发布中…" : "发布"}
                </Btn>
              </div>
            </div>
          </div>
        </div>
      )}

      {showCrossDomain && (
        <Modal title="跨域关联" onClose={() => setShowCrossDomain(false)}>
          <div className="space-y-4">
            <div className="text-xs text-muted-foreground">
              跨域关联用于发现不同业务领域（能源 / 航空 / 轨交 /
              通用）之间共享的部件、故障模式或维修策略。
              点击"打开图谱空间"后可分别选择两个领域，在图谱中对比其实体重叠情况。
            </div>
            <div className="flex gap-2 justify-end">
              <Btn variant="ghost" onClick={() => setShowCrossDomain(false)}>
                关闭
              </Btn>
              <Btn
                variant="primary"
                onClick={() => {
                  setShowCrossDomain(false);
                  navigate({ to: "/graph" });
                }}
              >
                打开图谱空间
              </Btn>
            </div>
          </div>
        </Modal>
      )}

      {owlModal.open && (
        <Modal title="导出 OWL" onClose={owlModal.closeModal}>
          <div className="space-y-4">
            <div className="text-xs text-muted-foreground">将当前本体定义导出为 OWL/XML 格式。</div>
            <pre className="overflow-auto border border-border bg-card p-4 font-mono text-[11px] leading-relaxed text-foreground/90 max-h-[300px]">
              {`<?xml version="1.0"?>
<Ontology xmlns="http://www.w3.org/2002/07/owl#"
  ontologyIRI="http://aether-phm.org/ontology/v3.2.1">
${displayClasses.map((c) => `  <Declaration><Class IRI="#${c.c}"/></Declaration>`).join("\n")}
${displayRels.map((r) => `  <Declaration><ObjectProperty IRI="#${r.r}"/></Declaration>`).join("\n")}
${displayRels.map((r) => `  <ObjectPropertyDomain><ObjectProperty IRI="#${r.r}"/><Class IRI="#${r.from}"/></ObjectPropertyDomain>`).join("\n")}
${displayRels.map((r) => `  <ObjectPropertyRange><ObjectProperty IRI="#${r.r}"/><Class IRI="#${r.to}"/></ObjectPropertyRange>`).join("\n")}
</Ontology>`}
            </pre>
            <div className="flex gap-2 justify-end">
              <Btn variant="ghost" onClick={owlModal.closeModal}>
                关闭
              </Btn>
              <Btn
                variant="primary"
                onClick={() => {
                  const blob = new Blob([document.querySelector("pre")?.textContent || ""], {
                    type: "application/xml",
                  });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement("a");
                  a.href = url;
                  a.download = "aether-phm-ontology.owl";
                  a.click();
                  URL.revokeObjectURL(url);
                }}
              >
                下载 OWL
              </Btn>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
