import { createFileRoute } from "@tanstack/react-router";
import { PageHeader, SectionHeader, Kpi, Btn, Badge } from "@/components/panel";
import { Modal, useModal } from "@/components/modal";
import { Bot, Wrench, Zap, ShieldCheck, X } from "lucide-react";
import { useState, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  useAgentTaskSubmit,
  useAgentTaskStatus,
  useAgentTaskResult,
  useAgentConfirm,
} from "@/hooks/use-agent";
import { useAuth } from "@/lib/auth";
import { apiClient } from "@/lib/api-client";

export const Route = createFileRoute("/agent")({
  component: Agent,
  head: () => ({ meta: [{ title: "Agent 编排 · Aether PHM" }] }),
});

const AGENT_TYPES = [
  {
    name: "故障诊断 Agent",
    icon: Wrench,
    type: "fault_diagnosis",
    desc: "基于知识图谱与 RAG 的故障诊断推理",
  },
  {
    name: "维修策略 Agent",
    icon: ShieldCheck,
    type: "maintenance_strategy",
    desc: "维修策略推荐与工单生成",
  },
  { name: "寿命预测 Agent", icon: Zap, type: "rul_prediction", desc: "剩余寿命预测方法建议" },
  { name: "知识审校 Agent", icon: Bot, type: "knowledge_review", desc: "知识条目审校与质量检测" },
];

const TOOLS = [
  { name: "RAG 混合检索", desc: "向量检索（Milvus）+ 关键词兜底检索已发布知识库" },
  {
    name: "图谱推理",
    desc: "在 Neo4j 知识图谱中解析实体并遍历关联关系（故障模式/维修策略/预测模型等）",
  },
  {
    name: "大模型生成",
    desc: "基于检索到的证据生成结论；未接入大模型时自动降级为证据摘要，不编造内容",
  },
];

function useAgentStats() {
  return useQuery({
    queryKey: ["agent", "stats"],
    queryFn: () =>
      apiClient.get<{
        calls24h: number;
        avgDurationSeconds: number | null;
        byType: Record<string, number>;
        availableAgentTypes: string[];
      }>("/agent/stats"),
    refetchInterval: 15000,
  });
}

function Agent() {
  const { user } = useAuth();
  const [showCreate, setShowCreate] = useState(false);
  const [presetAgentType, setPresetAgentType] = useState<string | undefined>(undefined);
  const [activeTaskId, setActiveTaskId] = useState<string | undefined>(undefined);
  const taskSubmit = useAgentTaskSubmit();
  const { data: taskStatus } = useAgentTaskStatus(activeTaskId);
  const { data: taskResult } = useAgentTaskResult(
    taskStatus?.status === "completed" ||
      taskStatus?.status === "waiting_confirmation" ||
      taskStatus?.status === "confirmed" ||
      taskStatus?.status === "rejected"
      ? activeTaskId
      : undefined,
  );
  const agentConfirm = useAgentConfirm();
  const { data: agentStats } = useAgentStats();
  const toolsModal = useModal();

  const handleSubmit = useCallback(
    (agentType: string, input: Record<string, unknown>) => {
      taskSubmit.mutate(
        { agent_type: agentType, input, submitter_id: user?.userId || "" },
        {
          onSuccess: (data) => {
            setActiveTaskId(data.taskId);
          },
        },
      );
    },
    [taskSubmit, user],
  );

  const handleConfirm = useCallback(
    (decision: "approved" | "rejected") => {
      if (!activeTaskId) return;
      agentConfirm.mutate({
        taskId: activeTaskId,
        confirmer_id: user?.userId || "",
        decision,
      });
    },
    [activeTaskId, agentConfirm, user],
  );

  return (
    <div className="animate-in-up p-8">
      <PageHeader
        eyebrow="M06 · Agent Orchestration"
        title="智能 Agent 编排"
        description="面向诊断、维修、预测与审校任务的多 Agent 协同：工具调用、图谱推理与人机协作闭环。"
        actions={
          <>
            <Btn variant="outline" onClick={toolsModal.openModal}>
              工具中心
            </Btn>
            <Btn
              variant="primary"
              onClick={() => {
                setPresetAgentType(undefined);
                setShowCreate(true);
              }}
            >
              创建 Agent
            </Btn>
          </>
        }
      />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
        <Kpi label="可用 Agent" value={String(AGENT_TYPES.length)} tone="primary" />
        <Kpi
          label="24H 调用"
          value={agentStats ? String(agentStats.calls24h) : "—"}
          tone="primary"
        />
        <Kpi
          label="平均耗时"
          value={agentStats?.avgDurationSeconds != null ? `${agentStats.avgDurationSeconds}s` : "—"}
          tone="primary"
        />
        <Kpi label="工具能力" value={String(TOOLS.length)} tone="primary" />
      </div>

      <div className="mt-8 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        {AGENT_TYPES.map((a) => (
          <div
            key={a.type}
            className="border border-border bg-card p-5 transition hover:border-primary/40"
          >
            <div className="mb-4 flex items-center justify-between">
              <a.icon className="size-5 text-primary" strokeWidth={1.5} />
              <Badge tone="success">可用</Badge>
            </div>
            <div className="text-sm font-bold">{a.name}</div>
            <div className="mt-1 text-[11px] text-muted-foreground">{a.desc}</div>
            <div className="mt-1 font-mono text-[9px] text-muted-foreground">
              24H 调用: {agentStats?.byType[a.type] ?? 0}
            </div>
            <div className="mt-4">
              <Btn
                variant="outline"
                onClick={() => {
                  setPresetAgentType(a.type);
                  setShowCreate(true);
                }}
              >
                发起任务
              </Btn>
            </div>
          </div>
        ))}
      </div>

      {activeTaskId && (
        <div className="mt-8">
          <SectionHeader
            title={`任务 ${activeTaskId}`}
            action={
              taskStatus ? (
                <Badge
                  tone={
                    taskStatus.status === "completed" || taskStatus.status === "confirmed"
                      ? "success"
                      : taskStatus.status === "running"
                        ? "primary"
                        : taskStatus.status === "rejected" || taskStatus.status === "failed"
                          ? "warning"
                          : "primary"
                  }
                >
                  {taskStatus.status}
                </Badge>
              ) : undefined
            }
          />
          <div className="border border-border bg-card/40 p-4 font-mono text-[11px] leading-relaxed">
            {taskStatus && <div className="mb-3">当前步骤: {taskStatus.currentStep || "—"}</div>}
            {taskResult && (
              <div className="space-y-2 mt-4">
                <div className="text-muted-foreground mb-2">执行轨迹:</div>
                {taskResult.trace.map((step, i) => (
                  <div key={i} className="border-b border-border/50 pb-2 last:border-none">
                    <Badge tone="primary">STEP {step.step}</Badge>{" "}
                    <span className="text-foreground/90">
                      {step.action}: {step.output}
                    </span>
                  </div>
                ))}
                <div className="mt-3 whitespace-pre-wrap text-foreground font-bold">
                  最终结果: {taskResult.finalResult}
                </div>
              </div>
            )}
            {taskStatus?.status === "waiting_confirmation" && (
              <div className="flex gap-2 mt-4">
                <Btn
                  variant="primary"
                  onClick={() => handleConfirm("approved")}
                  disabled={agentConfirm.isPending}
                >
                  确认采纳
                </Btn>
                <Btn
                  variant="outline"
                  onClick={() => handleConfirm("rejected")}
                  disabled={agentConfirm.isPending}
                >
                  驳回
                </Btn>
              </div>
            )}
            {taskStatus?.status === "confirmed" && (
              <div className="mt-3 text-success text-[10px]">✓ 专家已确认采纳该结论</div>
            )}
            {taskStatus?.status === "rejected" && (
              <div className="mt-3 text-destructive text-[10px]">✕ 专家已驳回该结论</div>
            )}
          </div>
        </div>
      )}

      {showCreate && (
        <CreateAgentModal
          defaultType={presetAgentType}
          onClose={() => setShowCreate(false)}
          onSubmit={handleSubmit}
        />
      )}

      {toolsModal.open && (
        <Modal title="工具中心" onClose={toolsModal.closeModal}>
          <div className="space-y-3">
            <div className="text-xs text-muted-foreground">Agent 编排任务实际调用的工具能力：</div>
            {TOOLS.map((t) => (
              <div key={t.name} className="border border-border bg-card/50 p-3">
                <div className="text-xs font-bold">{t.name}</div>
                <div className="mt-1 text-[11px] text-muted-foreground">{t.desc}</div>
              </div>
            ))}
            <div className="flex gap-2 justify-end">
              <Btn variant="ghost" onClick={toolsModal.closeModal}>
                关闭
              </Btn>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}

function CreateAgentModal({
  defaultType,
  onClose,
  onSubmit,
}: {
  defaultType?: string;
  onClose: () => void;
  onSubmit: (type: string, input: Record<string, unknown>) => void;
}) {
  const [agentType, setAgentType] = useState(defaultType || "fault_diagnosis");
  const [query, setQuery] = useState("");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-full max-w-md border border-border bg-card p-6">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-sm font-bold uppercase tracking-widest">创建 Agent 任务</h3>
          <button onClick={onClose}>
            <X className="size-4 text-muted-foreground" />
          </button>
        </div>
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
              Agent 类型
            </label>
            <select
              value={agentType}
              onChange={(e) => setAgentType(e.target.value)}
              className="w-full rounded border border-border bg-white/5 p-2 text-xs"
            >
              {AGENT_TYPES.map((a) => (
                <option key={a.type} value={a.type}>
                  {a.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
              输入查询
            </label>
            <textarea
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              rows={3}
              className="w-full rounded border border-border bg-white/5 p-2 text-xs"
              placeholder="描述你的任务需求，例如：GT-40 燃气轮机高温预警的故障原因"
            />
          </div>
          <Btn
            variant="primary"
            onClick={() => {
              onSubmit(agentType, { query });
              onClose();
            }}
            disabled={!query.trim()}
            className="w-full justify-center"
          >
            提交任务
          </Btn>
        </div>
      </div>
    </div>
  );
}
