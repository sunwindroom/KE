import { createFileRoute } from "@tanstack/react-router";
import { PageHeader, SectionHeader, Kpi, Btn, Badge } from "@/components/panel";
import { Modal, useModal } from "@/components/modal";
import { X } from "lucide-react";
import { useState, useCallback } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { useAuth } from "@/lib/auth";

export const Route = createFileRoute("/admin")({
  component: Admin,
  head: () => ({ meta: [{ title: "系统管理 · Aether PHM" }] }),
});

// 角色枚举必须与后端 role_enum（backend/app/models/models.py）严格一致，
// 否则新建/编辑用户时数据库会直接拒绝写入（Postgres enum 约束）。
const ROLE_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "engineer", label: "知识工程师" },
  { value: "expert", label: "审核专家" },
  { value: "manager", label: "主管" },
  { value: "admin", label: "系统管理员" },
];
const ROLE_LABEL: Record<string, string> = Object.fromEntries(
  ROLE_OPTIONS.map((r) => [r.value, r.label]),
);

const CLASSIFICATION_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "public", label: "公开" },
  { value: "internal", label: "内部" },
  { value: "confidential", label: "秘密" },
  { value: "secret", label: "机密" },
];

const DOMAIN_OPTIONS = ["energy", "transportation", "aerospace", "general"];

interface AdminUser {
  userId: string;
  userName: string;
  role: string;
  domainScope: string[] | string;
  maxClassificationLevel?: string;
  lastLoginAt?: string;
}

function useUsers() {
  return useQuery({
    queryKey: ["admin", "users"],
    queryFn: () =>
      apiClient.get<{
        page: number;
        page_size: number;
        total: number;
        items: AdminUser[];
      }>("/admin/users"),
  });
}

function useCreateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (req: {
      user_id: string;
      user_name: string;
      password: string;
      role: string;
      domain_scope: string;
      max_classification_level: string;
    }) => apiClient.post<{ userId: string; status: string }>("/admin/users", req),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "users"] }),
  });
}

function useUpdateUserRole() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: string }) =>
      apiClient.put<{ userId: string; role: string }>(`/admin/users/${userId}/role`, { role }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "users"] }),
  });
}

function useUpdateUserPermission() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      userId,
      domain_scope,
      max_classification_level,
    }: {
      userId: string;
      domain_scope?: string;
      max_classification_level?: string;
    }) =>
      apiClient.put<{ userId: string }>(`/admin/users/${userId}/permission`, {
        domain_scope,
        max_classification_level,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "users"] }),
  });
}

function useServiceStatus() {
  return useQuery({
    queryKey: ["admin", "services"],
    queryFn: () =>
      apiClient.get<
        Array<{
          name: string;
          version: string;
          status: string;
          cpu: number;
        }>
      >("/admin/services"),
    refetchInterval: 30000,
  });
}

interface ModelRegistryEntry {
  name: string;
  kind: string;
  endpoint: string;
  model: string;
  apiKeyPreview: string;
  configured: boolean;
  status: string;
  note: string;
}

function useModelRegistry() {
  return useQuery({
    queryKey: ["admin", "model-registry"],
    queryFn: () => apiClient.get<ModelRegistryEntry[]>("/admin/model/registry"),
  });
}

function domainScopeToArray(scope: string[] | string | undefined): string[] {
  if (!scope) return [];
  if (Array.isArray(scope)) return scope;
  return scope.split(",").map((s) => s.trim()).filter(Boolean);
}

function Admin() {
  useAuth();
  const [showCreateUser, setShowCreateUser] = useState(false);
  const [editingUser, setEditingUser] = useState<AdminUser | null>(null);
  const modelModal = useModal();
  const { data: usersPage, isLoading: usersLoading, isError: usersError, refetch: refetchUsers, isFetching: usersFetching } = useUsers();
  const { data: services, isLoading: servicesLoading } = useServiceStatus();
  const createUser = useCreateUser();

  const handleCreateUser = useCallback(
    (req: Parameters<typeof createUser.mutate>[0]) => {
      createUser.mutate(req, { onSuccess: () => setShowCreateUser(false) });
    },
    [createUser],
  );

  const users = usersPage?.items ?? [];
  const servicesList = services ?? [];

  return (
    <div className="animate-in-up p-8">
      <PageHeader
        eyebrow="M11 · System Administration"
        title="系统管理"
        description="租户、角色、权限、服务实例与模型接入的集中配置面板，支持细粒度权限模型与运行状态监控。"
        actions={
          <>
            <Btn variant="outline" onClick={modelModal.openModal}>
              模型接入配置
            </Btn>
            <Btn variant="primary" onClick={() => setShowCreateUser(true)}>
              新建用户
            </Btn>
          </>
        }
      />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
        <Kpi label="用户总数" value={usersPage ? String(usersPage.total) : "—"} tone="primary" />
        <Kpi label="本页用户" value={String(users.length)} tone="success" />
        <Kpi
          label="服务实例"
          value={servicesList.length ? `${servicesList.length} / ${servicesList.length}` : "—"}
          tone="success"
        />
        <Kpi
          label="平均 CPU"
          value={
            servicesList.length
              ? `${Math.round(servicesList.reduce((a, s) => a + s.cpu, 0) / servicesList.length)}%`
              : "—"
          }
          tone="primary"
        />
      </div>

      <div className="mt-8 grid grid-cols-1 gap-8 xl:grid-cols-3">
        <div className="xl:col-span-2">
          <SectionHeader
            title="用户与角色"
            action={
              <Btn variant="outline" onClick={() => refetchUsers()} disabled={usersFetching}>
                {usersFetching ? "刷新中…" : "刷新"}
              </Btn>
            }
          />
          <div className="overflow-hidden border border-border">
            <table className="w-full text-left text-[11px]">
              <thead className="border-b border-border bg-card">
                <tr>
                  {["用户", "角色", "领域", "最近登录", ""].map((h) => (
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
                {usersLoading ? (
                  <tr>
                    <td className="p-4 text-center text-muted-foreground" colSpan={5}>
                      加载中…
                    </td>
                  </tr>
                ) : usersError ? (
                  <tr>
                    <td className="p-4 text-center text-destructive" colSpan={5}>
                      加载用户列表失败，请重试
                    </td>
                  </tr>
                ) : users.length === 0 ? (
                  <tr>
                    <td className="p-4 text-center text-muted-foreground" colSpan={5}>
                      暂无用户，点击右上角「新建用户」创建第一个账号
                    </td>
                  </tr>
                ) : (
                  users.map((r) => (
                    <tr key={r.userId} className="hover:bg-white/5">
                      <td className="p-3 font-medium">{r.userName}</td>
                      <td className="p-3">
                        <Badge tone="primary">{ROLE_LABEL[r.role] ?? r.role}</Badge>
                      </td>
                      <td className="p-3 text-muted-foreground">
                        {domainScopeToArray(r.domainScope).join(", ") || "—"}
                      </td>
                      <td className="p-3 font-mono text-muted-foreground">{r.lastLoginAt || "—"}</td>
                      <td className="p-3 text-right">
                        <Btn variant="ghost" onClick={() => setEditingUser(r)}>
                          编辑
                        </Btn>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <SectionHeader title="服务实例" />
          {servicesLoading ? (
            <div className="border border-border bg-card/40 p-4 text-center text-[11px] text-muted-foreground">
              加载中…
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              {servicesList.map((s) => (
                <div key={s.name} className="border border-border bg-card p-3">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-[11px] font-bold text-primary">{s.name}</span>
                    <Badge tone={s.status === "OK" ? "success" : "warning"}>{s.status}</Badge>
                  </div>
                  <div className="mt-1 font-mono text-[9px] text-muted-foreground">v{s.version}</div>
                  <div className="mt-3 h-1 w-full overflow-hidden rounded-full bg-white/5">
                    <div
                      className={`h-full ${s.cpu > 70 ? "bg-warning" : "bg-primary"}`}
                      style={{ width: `${s.cpu}%` }}
                    />
                  </div>
                  <div className="mt-1 font-mono text-[9px] text-muted-foreground">CPU {s.cpu}%</div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div>
          <SectionHeader title="权限模型" />
          <div className="border border-border bg-card/40 p-4 text-[11px] leading-relaxed">
            <div className="mb-3 text-muted-foreground">
              基于 RBAC + 领域 + 密级三维授权，接入时强制注入{" "}
              <span className="font-mono text-primary">SecurityContext</span>。
            </div>
            <ul className="space-y-2 text-foreground/90">
              {[
                "① 角色：知识工程师 / 审核专家 / 主管 / 系统管理员",
                "② 领域：能源 / 航空 / 轨交 / 通用（可多选）",
                "③ 密级：公开 / 内部 / 秘密 / 机密",
                "④ 资源级 ACL：知识条目、图谱子图、模型、Agent",
                "⑤ 全链路审计：任何变更均生成不可篡改事件",
              ].map((l) => (
                <li key={l} className="border-b border-border/50 pb-2 last:border-none">
                  {l}
                </li>
              ))}
            </ul>
          </div>

          <SectionHeader title="模型接入状态" />
          <ModelRegistrySummary />
        </div>
      </div>

      {showCreateUser && (
        <CreateUserModal
          onClose={() => setShowCreateUser(false)}
          onSubmit={handleCreateUser}
          isPending={createUser.isPending}
          errorMessage={createUser.isError ? (createUser.error as Error).message : undefined}
        />
      )}

      {editingUser && <EditUserModal user={editingUser} onClose={() => setEditingUser(null)} />}

      {modelModal.open && <ModelRegistryModal onClose={modelModal.closeModal} />}
    </div>
  );
}

function ModelRegistrySummary() {
  const { data: registry, isLoading } = useModelRegistry();
  if (isLoading) {
    return (
      <div className="border border-border bg-card/40 p-4 text-center text-[11px] text-muted-foreground">
        加载中…
      </div>
    );
  }
  return (
    <div className="space-y-2 border border-border bg-card/40 p-4 font-mono text-[10px]">
      {(registry ?? []).map((m) => (
        <div
          key={m.kind}
          className="flex items-center justify-between border-b border-border/50 pb-2 last:border-none"
        >
          <span className="text-muted-foreground">{m.name}</span>
          <Badge tone={m.configured ? "success" : "warning"}>
            {m.configured ? "已接入" : "规则降级"}
          </Badge>
        </div>
      ))}
    </div>
  );
}

function ModelRegistryModal({ onClose }: { onClose: () => void }) {
  const { data: registry, isLoading, isError } = useModelRegistry();
  return (
    <Modal title="模型接入配置" onClose={onClose}>
      <div className="space-y-4">
        <div className="text-xs text-muted-foreground">
          LLM / Embedding 服务通过部署环境变量（<span className="font-mono">LLM_ENDPOINT</span>、
          <span className="font-mono">LLM_API_KEY</span>、<span className="font-mono">EMBEDDING_ENDPOINT</span>
          ）注入，出于安全考虑密钥不通过前端写入或明文展示；此处仅展示当前生效的接入状态，供运维核对部署是否正确。
        </div>
        {isLoading ? (
          <div className="p-4 text-center text-xs text-muted-foreground">加载中…</div>
        ) : isError ? (
          <div className="p-4 text-center text-xs text-destructive">加载模型配置失败</div>
        ) : (
          <div className="space-y-2">
            {(registry ?? []).map((m) => (
              <div key={m.kind} className="border border-border bg-card/40 p-3">
                <div className="flex items-center justify-between">
                  <div className="text-xs font-bold">{m.name}</div>
                  <Badge tone={m.configured ? "success" : "warning"}>
                    {m.configured ? "已配置" : "未配置 · 规则降级"}
                  </Badge>
                </div>
                <div className="mt-1 font-mono text-[10px] text-muted-foreground">
                  endpoint: {m.endpoint} · model: {m.model}
                </div>
                {m.apiKeyPreview && (
                  <div className="font-mono text-[10px] text-muted-foreground">
                    key: {m.apiKeyPreview}
                  </div>
                )}
                <div className="mt-1 text-[10px] text-muted-foreground/80">{m.note}</div>
              </div>
            ))}
          </div>
        )}
        <div className="flex justify-end">
          <Btn variant="ghost" onClick={onClose}>
            关闭
          </Btn>
        </div>
      </div>
    </Modal>
  );
}

function CreateUserModal({
  onClose,
  onSubmit,
  isPending,
  errorMessage,
}: {
  onClose: () => void;
  onSubmit: (req: {
    user_id: string;
    user_name: string;
    password: string;
    role: string;
    domain_scope: string;
    max_classification_level: string;
  }) => void;
  isPending: boolean;
  errorMessage?: string;
}) {
  const [userId, setUserId] = useState("");
  const [userName, setUserName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("engineer");
  const [classificationLevel, setClassificationLevel] = useState("internal");
  const [domainScope, setDomainScope] = useState<string[]>([]);

  const toggleDomain = (d: string) => {
    setDomainScope((prev) => (prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d]));
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-full max-w-md border border-border bg-card p-6">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-sm font-bold uppercase tracking-widest">新建用户</h3>
          <button onClick={onClose}>
            <X className="size-4 text-muted-foreground" />
          </button>
        </div>
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
              用户 ID
            </label>
            <input
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              className="w-full rounded border border-border bg-white/5 p-2 text-xs"
              placeholder="唯一标识符，如 zhangwei"
            />
          </div>
          <div>
            <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
              用户名
            </label>
            <input
              value={userName}
              onChange={(e) => setUserName(e.target.value)}
              className="w-full rounded border border-border bg-white/5 p-2 text-xs"
            />
          </div>
          <div>
            <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
              密码
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded border border-border bg-white/5 p-2 text-xs"
            />
          </div>
          <div>
            <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
              角色
            </label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              className="w-full rounded border border-border bg-white/5 p-2 text-xs"
            >
              {ROLE_OPTIONS.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
              最高密级
            </label>
            <select
              value={classificationLevel}
              onChange={(e) => setClassificationLevel(e.target.value)}
              className="w-full rounded border border-border bg-white/5 p-2 text-xs"
            >
              {CLASSIFICATION_OPTIONS.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
              领域权限
            </label>
            <div className="flex flex-wrap gap-1.5">
              {DOMAIN_OPTIONS.map((d) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => toggleDomain(d)}
                  className={`rounded border px-2 py-1 text-[10px] transition ${
                    domainScope.includes(d)
                      ? "border-primary/40 bg-primary/10 text-primary"
                      : "border-border hover:border-primary/40"
                  }`}
                >
                  {d}
                </button>
              ))}
            </div>
          </div>
          {errorMessage && <div className="text-[10px] text-destructive">{errorMessage}</div>}
          <Btn
            variant="primary"
            onClick={() =>
              onSubmit({
                user_id: userId,
                user_name: userName,
                password,
                role,
                domain_scope: domainScope.join(","),
                max_classification_level: classificationLevel,
              })
            }
            disabled={!userId || !userName || !password || isPending}
            className="w-full justify-center"
          >
            {isPending ? "创建中…" : "创建用户"}
          </Btn>
        </div>
      </div>
    </div>
  );
}

function EditUserModal({ user, onClose }: { user: AdminUser; onClose: () => void }) {
  const [role, setRole] = useState(user.role);
  const [classificationLevel, setClassificationLevel] = useState(
    user.maxClassificationLevel || "internal",
  );
  const [domainScope, setDomainScope] = useState<string[]>(domainScopeToArray(user.domainScope));
  const updateRole = useUpdateUserRole();
  const updatePermission = useUpdateUserPermission();

  const toggleDomain = (d: string) => {
    setDomainScope((prev) => (prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d]));
  };

  const isPending = updateRole.isPending || updatePermission.isPending;
  const errorMessage =
    (updateRole.isError && (updateRole.error as Error).message) ||
    (updatePermission.isError && (updatePermission.error as Error).message) ||
    undefined;

  const handleSave = () => {
    const tasks: Promise<unknown>[] = [];
    if (role !== user.role) {
      tasks.push(updateRole.mutateAsync({ userId: user.userId, role }));
    }
    tasks.push(
      updatePermission.mutateAsync({
        userId: user.userId,
        domain_scope: domainScope.join(","),
        max_classification_level: classificationLevel,
      }),
    );
    Promise.all(tasks).then(onClose).catch(() => {});
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-full max-w-md border border-border bg-card p-6">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-sm font-bold uppercase tracking-widest">
            编辑用户 · {user.userName}
          </h3>
          <button onClick={onClose}>
            <X className="size-4 text-muted-foreground" />
          </button>
        </div>
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
              角色
            </label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              className="w-full rounded border border-border bg-white/5 p-2 text-xs"
            >
              {ROLE_OPTIONS.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
              最高密级
            </label>
            <select
              value={classificationLevel}
              onChange={(e) => setClassificationLevel(e.target.value)}
              className="w-full rounded border border-border bg-white/5 p-2 text-xs"
            >
              {CLASSIFICATION_OPTIONS.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
              领域权限
            </label>
            <div className="flex flex-wrap gap-1.5">
              {DOMAIN_OPTIONS.map((d) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => toggleDomain(d)}
                  className={`rounded border px-2 py-1 text-[10px] transition ${
                    domainScope.includes(d)
                      ? "border-primary/40 bg-primary/10 text-primary"
                      : "border-border hover:border-primary/40"
                  }`}
                >
                  {d}
                </button>
              ))}
            </div>
          </div>
          {errorMessage && <div className="text-[10px] text-destructive">{errorMessage}</div>}
          <Btn
            variant="primary"
            onClick={handleSave}
            disabled={isPending}
            className="w-full justify-center"
          >
            {isPending ? "保存中…" : "保存修改"}
          </Btn>
        </div>
      </div>
    </div>
  );
}
