import { createFileRoute } from "@tanstack/react-router";
import { PageHeader, SectionHeader, Kpi, Btn, Badge } from "@/components/panel";
import { Modal, useModal } from "@/components/modal";
import { X } from "lucide-react";
import { useState, useCallback } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { useAuth } from "@/lib/auth";

export const Route = createFileRoute("/finetune")({
  component: Finetune,
  head: () => ({ meta: [{ title: "领域微调 · Aether PHM" }] }),
});

function useFinetuneTasks() {
  return useQuery({
    queryKey: ["finetune", "tasks"],
    queryFn: () =>
      apiClient.get<
        Array<{
          taskId: string;
          model: string;
          stage: string;
          progress: number;
          status: string;
          meta: string;
        }>
      >("/finetune/tasks"),
    refetchInterval: 15000,
  });
}

function useCreateFinetuneTask() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (req: {
      model: string;
      stage: string;
      domain: string;
      datasetId?: string;
      submitterId: string;
    }) => apiClient.post<{ taskId: string; status: string }>("/finetune/task", req),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["finetune", "tasks"] }),
  });
}

interface RegisteredModelView {
  modelId: string;
  name: string;
  baseModel: string;
  sourceTaskId: string | null;
  version: string;
  stage: string | null;
  status: string;
  createdAt: string;
}

function useRegisteredModels() {
  return useQuery({
    queryKey: ["finetune", "models"],
    queryFn: () => apiClient.get<RegisteredModelView[]>("/finetune/models"),
  });
}

function useRegisterModel() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (req: {
      name: string;
      baseModel?: string;
      sourceTaskId?: string;
      version: string;
      stage?: string;
      submitterId: string;
    }) => apiClient.post<{ modelId: string; status: string }>("/finetune/models/register", req),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["finetune", "models"] }),
  });
}

function Finetune() {
  const { user } = useAuth();
  const [showCreate, setShowCreate] = useState(false);
  const [registeringTaskId, setRegisteringTaskId] = useState<string | null>(null);
  const datasetModal = useModal();
  const { data: tasks, isLoading: tasksLoading, refetch: refetchTasks, isFetching: tasksFetching } = useFinetuneTasks();
  const { data: models, isLoading: modelsLoading } = useRegisteredModels();
  const createTask = useCreateFinetuneTask();

  const displayTasks = tasks ?? [];

  return (
    <div className="animate-in-up p-8">
      <PageHeader
        eyebrow="M07 · Domain Fine-tuning"
        title="领域微调控制台"
        description="基于知识库高质量语料的指令与偏好数据构造，对基座大模型进行领域微调、评测与灰度发布。"
        actions={
          <>
            <Btn variant="outline" onClick={datasetModal.openModal}>
              数据集
            </Btn>
            <Btn variant="primary" onClick={() => setShowCreate(true)}>
              新建训练
            </Btn>
          </>
        }
      />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
        <Kpi label="训练任务" value={String(displayTasks.length)} tone="primary" />
        <Kpi label="最优准确率" value="—" tone="success" />
        <Kpi label="发布版本" value="—" tone="primary" />
        <Kpi label="GPU 时长" value="—" tone="primary" />
      </div>

      <div className="mt-8 grid grid-cols-1 gap-8 xl:grid-cols-2">
        <div>
          <SectionHeader
            title="训练任务"
            action={
              <Btn variant="outline" onClick={() => refetchTasks()} disabled={tasksFetching}>
                {tasksFetching ? "刷新中…" : "刷新"}
              </Btn>
            }
          />
          <div className="space-y-2">
            {tasksLoading ? (
              <div className="border border-border bg-card/40 p-6 text-center text-[11px] text-muted-foreground">
                加载中…
              </div>
            ) : displayTasks.length === 0 ? (
              <div className="border border-border bg-card/40 p-6 text-center text-[11px] text-muted-foreground">
                暂无训练任务，点击右上角「新建训练」提交第一个微调任务
              </div>
            ) : (
              displayTasks.map((t) => (
                <div key={t.taskId} className="border border-border bg-card p-4">
                  <div className="mb-2 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs font-bold text-primary">{t.taskId}</span>
                      <Badge
                        tone={
                          t.status === "completed"
                            ? "success"
                            : t.status === "running"
                              ? "primary"
                              : t.status === "failed"
                                ? "warning"
                                : "warning"
                        }
                      >
                        {t.stage}
                      </Badge>
                      <span className="text-xs text-muted-foreground">{t.model}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-[10px] text-muted-foreground">{t.meta}</span>
                      {t.status === "completed" && (
                        <Btn variant="ghost" onClick={() => setRegisteringTaskId(t.taskId)}>
                          注册为模型
                        </Btn>
                      )}
                    </div>
                  </div>
                  <div className="h-1 w-full overflow-hidden rounded-full bg-white/5">
                    <div
                      className={`h-full ${t.status === "completed" ? "bg-success" : t.status === "queued" ? "bg-warning" : "bg-primary"}`}
                      style={{ width: `${t.progress}%` }}
                    />
                  </div>
                </div>
              ))
            )}
          </div>

          <SectionHeader title="已注册模型" />
          <div className="overflow-hidden border border-border">
            <table className="w-full text-left text-[11px]">
              <thead className="border-b border-border bg-card">
                <tr>
                  {["模型", "来源任务", "版本", "状态"].map((h) => (
                    <th key={h} className="p-3 font-bold uppercase tracking-tighter text-muted-foreground">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {modelsLoading ? (
                  <tr>
                    <td className="p-4 text-center text-muted-foreground" colSpan={4}>
                      加载中…
                    </td>
                  </tr>
                ) : !models || models.length === 0 ? (
                  <tr>
                    <td className="p-4 text-center text-muted-foreground" colSpan={4}>
                      暂无已注册模型
                    </td>
                  </tr>
                ) : (
                  models.map((m) => (
                    <tr key={m.modelId} className="hover:bg-white/5">
                      <td className="p-3 font-mono text-primary">{m.name}</td>
                      <td className="p-3 font-mono text-muted-foreground">{m.sourceTaskId || "—"}</td>
                      <td className="p-3 font-mono">{m.version}</td>
                      <td className="p-3">
                        <Badge tone={m.status === "production" ? "success" : "primary"}>{m.status}</Badge>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div>
          <SectionHeader title="领域评测集" action={<Badge tone="primary">v2.4</Badge>} />
          <div className="overflow-hidden border border-border">
            <table className="w-full text-left text-[11px]">
              <thead className="border-b border-border bg-card">
                <tr>
                  {["评测集", "样本", "基线", "微调后", "增益"].map((h) => (
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
                {[
                  { n: "故障诊断 QA", s: "1,824", b: "72.1", f: "89.4", d: "+17.3" },
                  { n: "维修策略推荐", s: "912", b: "68.5", f: "86.2", d: "+17.7" },
                  { n: "寿命预测知识", s: "614", b: "70.3", f: "84.1", d: "+13.8" },
                  { n: "术语标准化", s: "2,401", b: "81.2", f: "94.6", d: "+13.4" },
                ].map((r) => (
                  <tr key={r.n} className="hover:bg-white/5">
                    <td className="p-3 font-medium">{r.n}</td>
                    <td className="p-3 font-mono text-muted-foreground">{r.s}</td>
                    <td className="p-3 font-mono">{r.b}</td>
                    <td className="p-3 font-mono text-primary">{r.f}</td>
                    <td className="p-3 font-mono text-success">{r.d}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {showCreate && (
        <CreateFinetuneModal
          onClose={() => setShowCreate(false)}
          onSubmit={(req) => {
            createTask.mutate(
              { ...req, submitterId: user?.userId || "" },
              { onSuccess: () => setShowCreate(false) },
            );
          }}
          isPending={createTask.isPending}
        />
      )}

      {registeringTaskId && (
        <RegisterModelModal
          taskId={registeringTaskId}
          task={displayTasks.find((t) => t.taskId === registeringTaskId)}
          onClose={() => setRegisteringTaskId(null)}
        />
      )}

      {datasetModal.open && (
        <Modal title="训练数据集" onClose={datasetModal.closeModal}>
          <div className="space-y-4">
            <div className="text-xs text-muted-foreground">
              管理微调训练所用的指令数据集和偏好数据集。当前数据集管理尚未接入独立的数据集服务，
              下表为示意参考，实际训练数据请通过知识库导出后离线构建。
            </div>
            <div className="overflow-hidden border border-border">
              <table className="w-full text-left text-[11px]">
                <thead className="border-b border-border bg-card">
                  <tr>
                    {["数据集", "类型", "样本数", "状态"].map((h) => (
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
                  {[
                    { n: "PHM-SFT-v2.4", t: "指令微调", s: "4,821", st: "success" },
                    { n: "PHM-DPO-v1.2", t: "偏好对齐", s: "1,204", st: "success" },
                    { n: "PHM-RLHF-v0.8", t: "人类反馈", s: "612", st: "warning" },
                    { n: "PHM-Eval-v2.4", t: "评测集", s: "5,751", st: "success" },
                  ].map((r) => (
                    <tr key={r.n} className="hover:bg-white/5">
                      <td className="p-3 font-mono text-primary">{r.n}</td>
                      <td className="p-3">{r.t}</td>
                      <td className="p-3 font-mono">{r.s}</td>
                      <td className="p-3">
                        <Badge tone={r.st as "success" | "warning"}>
                          {r.st === "success" ? "就绪" : "构建中"}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex justify-end gap-2">
              <Btn variant="ghost" onClick={datasetModal.closeModal}>
                关闭
              </Btn>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}

function RegisterModelModal({
  taskId,
  task,
  onClose,
}: {
  taskId: string;
  task?: { model: string; stage: string };
  onClose: () => void;
}) {
  const { user } = useAuth();
  const [name, setName] = useState(`${task?.model ?? "model"}-${task?.stage ?? "sft"}-${taskId.slice(-4).toLowerCase()}`);
  const [version, setVersion] = useState("v1");
  const registerModel = useRegisterModel();

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-full max-w-md border border-border bg-card p-6">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-sm font-bold uppercase tracking-widest">注册为模型 · {taskId}</h3>
          <button onClick={onClose}>
            <X className="size-4 text-muted-foreground" />
          </button>
        </div>
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
              模型名称
            </label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full rounded border border-border bg-white/5 p-2 text-xs"
            />
          </div>
          <div>
            <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
              版本号
            </label>
            <input
              value={version}
              onChange={(e) => setVersion(e.target.value)}
              className="w-full rounded border border-border bg-white/5 p-2 text-xs"
            />
          </div>
          {registerModel.isError && (
            <div className="text-[10px] text-destructive">{(registerModel.error as Error).message}</div>
          )}
          <Btn
            variant="primary"
            onClick={() =>
              registerModel.mutate(
                {
                  name,
                  baseModel: task?.model,
                  sourceTaskId: taskId,
                  version,
                  stage: task?.stage,
                  submitterId: user?.userId || "",
                },
                { onSuccess: onClose },
              )
            }
            disabled={!name || !version || registerModel.isPending}
            className="w-full justify-center"
          >
            {registerModel.isPending ? "注册中…" : "确认注册"}
          </Btn>
        </div>
      </div>
    </div>
  );
}

function CreateFinetuneModal({
  onClose,
  onSubmit,
  isPending,
}: {
  onClose: () => void;
  onSubmit: (req: { model: string; stage: string; domain: string }) => void;
  isPending: boolean;
}) {
  const [model, setModel] = useState("Qwen2.5-14B-Base");
  const [stage, setStage] = useState("SFT");
  const [domain, setDomain] = useState("aerospace");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-full max-w-md border border-border bg-card p-6">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-sm font-bold uppercase tracking-widest">新建训练任务</h3>
          <button onClick={onClose}>
            <X className="size-4 text-muted-foreground" />
          </button>
        </div>
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
              基座模型
            </label>
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="w-full rounded border border-border bg-white/5 p-2 text-xs"
            >
              <option value="Qwen2.5-14B-Base">Qwen2.5-14B-Base</option>
              <option value="Qwen2.5-7B">Qwen2.5-7B</option>
              <option value="Llama-3.1-8B">Llama-3.1-8B</option>
            </select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                训练阶段
              </label>
              <select
                value={stage}
                onChange={(e) => setStage(e.target.value)}
                className="w-full rounded border border-border bg-white/5 p-2 text-xs"
              >
                <option value="SFT">SFT</option>
                <option value="DPO">DPO</option>
                <option value="RLHF">RLHF</option>
              </select>
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
          </div>
          <Btn
            variant="primary"
            onClick={() => onSubmit({ model, stage, domain })}
            disabled={isPending}
            className="w-full justify-center"
          >
            {isPending ? "创建中…" : "创建训练任务"}
          </Btn>
        </div>
      </div>
    </div>
  );
}
