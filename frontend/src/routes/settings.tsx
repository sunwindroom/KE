import { createFileRoute } from "@tanstack/react-router";
import { useState, useMemo, useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  SlidersHorizontal,
  Sparkles,
  Waypoints,
  ShieldCheck,
  UploadCloud,
  Globe2,
  Database,
  GitBranch,
  Boxes,
  Package,
  Radio,
  AppWindow,
  CheckCircle2,
  XCircle,
  Loader2,
  RotateCcw,
  Save,
  Eraser,
} from "lucide-react";
import { PageHeader, SectionHeader, Btn, Badge } from "@/components/panel";
import { PermissionGuard } from "@/components/permission-guard";
import { apiClient } from "@/lib/api-client";

export const Route = createFileRoute("/settings")({
  component: SettingsPage,
  head: () => ({ meta: [{ title: "系统设置 · Aether PHM" }] }),
});

// ------------------------------------------------------------------------------------
// 类型定义 & 数据获取
// ------------------------------------------------------------------------------------

interface CategoryMeta {
  key: string;
  label: string;
  description: string;
  restartRequired: boolean;
}

interface FieldMeta {
  key: string;
  label: string;
  type: "string" | "int" | "float" | "bool" | "list" | "secret";
  description: string;
  secret: boolean;
  restartRequired: boolean;
  placeholder: string;
  value: string | number | boolean;
  configured: boolean;
}

const CATEGORY_ICONS: Record<string, typeof SlidersHorizontal> = {
  llm: Sparkles,
  embedding: Waypoints,
  security: ShieldCheck,
  upload: UploadCloud,
  cors: Globe2,
  database: Database,
  graph_neo4j: GitBranch,
  vector_milvus: Boxes,
  storage_minio: Package,
  cache_redis: Radio,
  mq_rabbitmq: Radio,
  app: AppWindow,
};

// 支持“测试连接”的分类：大模型/向量模型走专用接口（真实发一次对话/embedding 请求），
// 基础设施类走通用连通性探测接口。
const TESTABLE_INFRA = new Set([
  "database",
  "graph_neo4j",
  "vector_milvus",
  "storage_minio",
  "cache_redis",
  "mq_rabbitmq",
]);

function useCategories() {
  return useQuery({
    queryKey: ["settings", "categories"],
    queryFn: () => apiClient.get<CategoryMeta[]>("/admin/config/categories"),
  });
}

function useCategoryFields(category: string) {
  return useQuery({
    queryKey: ["settings", "fields", category],
    queryFn: () =>
      apiClient.get<{ category: string; fields: FieldMeta[] }>(`/admin/config/${category}`),
    enabled: !!category,
  });
}

// ------------------------------------------------------------------------------------
// 主页面
// ------------------------------------------------------------------------------------

function SettingsPage() {
  const { data: categories, isLoading } = useCategories();
  const [active, setActive] = useState<string>("llm");

  return (
    <PermissionGuard
      roles={["admin"]}
      fallback={
        <div className="p-10">
          <PageHeader
            eyebrow="ACCESS DENIED"
            title="系统设置"
            description="仅系统管理员可以访问生产环境配置。"
          />
        </div>
      }
    >
      <div className="p-8">
        <PageHeader
          eyebrow="PRODUCTION CONFIGURATION"
          title="系统设置"
          description="在此页面完成大模型 API、向量模型、安全策略与全部基础设施的生产配置——无需登录服务器修改 .env 或 docker-compose 文件。"
        />

        <div className="flex gap-6">
          <div className="w-64 shrink-0 space-y-1">
            {isLoading && <div className="text-xs text-muted-foreground">加载分类中…</div>}
            {categories?.map((c) => {
              const Icon = CATEGORY_ICONS[c.key] ?? SlidersHorizontal;
              const activeCls =
                active === c.key
                  ? "border-primary/25 bg-primary/10 text-primary font-medium"
                  : "border-transparent text-muted-foreground hover:bg-white/5 hover:text-foreground";
              return (
                <button
                  key={c.key}
                  onClick={() => setActive(c.key)}
                  className={`flex w-full items-center gap-3 rounded border px-3 py-2 text-left text-sm transition-colors ${activeCls}`}
                >
                  <Icon className="size-4 shrink-0" strokeWidth={1.75} />
                  <span className="flex-1">{c.label}</span>
                  {c.restartRequired ? (
                    <span className="size-1.5 rounded-full bg-warning" title="修改后需重启才生效" />
                  ) : (
                    <span className="size-1.5 rounded-full bg-success" title="修改后立即生效" />
                  )}
                </button>
              );
            })}
            <div className="mt-4 space-y-1.5 border-t border-border px-3 pt-4 text-[10px] text-muted-foreground">
              <div className="flex items-center gap-1.5">
                <span className="size-1.5 rounded-full bg-success" /> 立即生效，无需重启
              </div>
              <div className="flex items-center gap-1.5">
                <span className="size-1.5 rounded-full bg-warning" /> 保存后需重启后端服务
              </div>
            </div>
          </div>

          <div className="min-w-0 flex-1">
            {categories?.find((c) => c.key === active) && (
              <CategoryPanel category={categories.find((c) => c.key === active)!} />
            )}
          </div>
        </div>
      </div>
    </PermissionGuard>
  );
}

// ------------------------------------------------------------------------------------
// 分类面板：加载字段 + 表单 + 保存 / 重置 / 测试连接
// ------------------------------------------------------------------------------------

type FormValue = string | number | boolean;

function CategoryPanel({ category }: { category: CategoryMeta }) {
  const { data, isLoading, isError } = useCategoryFields(category.key);
  const queryClient = useQueryClient();

  const [form, setForm] = useState<Record<string, FormValue>>({});
  const [secretDrafts, setSecretDrafts] = useState<Record<string, string>>({});
  const [saveResult, setSaveResult] = useState<{
    ok: boolean;
    message: string;
    restart?: string[];
  } | null>(null);
  const [testResult, setTestResult] = useState<{
    ok: boolean;
    message: string;
    latency?: number | null;
  } | null>(null);

  useEffect(() => {
    setForm({});
    setSecretDrafts({});
    setSaveResult(null);
    setTestResult(null);
  }, [category.key]);

  useEffect(() => {
    if (!data) return;
    const initial: Record<string, FormValue> = {};
    for (const f of data.fields) {
      if (!f.secret) initial[f.key] = f.value as FormValue;
    }
    setForm(initial);
  }, [data]);

  const saveMutation = useMutation({
    mutationFn: (values: Record<string, unknown>) =>
      apiClient.put<{ restartRequired: string[]; message: string }>(
        `/admin/config/${category.key}`,
        { values },
      ),
    onSuccess: (res) => {
      setSaveResult({ ok: true, message: res.message, restart: res.restartRequired });
      setSecretDrafts({});
      queryClient.invalidateQueries({ queryKey: ["settings", "fields", category.key] });
    },
    onError: (err: Error) => setSaveResult({ ok: false, message: err.message }),
  });

  const resetMutation = useMutation({
    mutationFn: () => apiClient.post<{ message: string }>(`/admin/config/${category.key}/reset`),
    onSuccess: (res) => {
      setSaveResult({ ok: true, message: res.message });
      setSecretDrafts({});
      queryClient.invalidateQueries({ queryKey: ["settings", "fields", category.key] });
    },
  });

  const testLLMMutation = useMutation({
    mutationFn: () =>
      apiClient.post<{ success: boolean; message: string; latencyMs: number | null }>(
        "/admin/config/llm/test",
        {
          endpoint: form["LLM_ENDPOINT"],
          api_key: secretDrafts["LLM_API_KEY"] || undefined,
          model: form["LLM_MODEL_NAME"],
        },
      ),
    onSuccess: (res) =>
      setTestResult({ ok: res.success, message: res.message, latency: res.latencyMs }),
    onError: (err: Error) => setTestResult({ ok: false, message: err.message }),
  });

  const testEmbeddingMutation = useMutation({
    mutationFn: () =>
      apiClient.post<{ success: boolean; message: string; latencyMs: number | null }>(
        "/admin/config/embedding/test",
        {
          endpoint: form["EMBEDDING_ENDPOINT"],
          api_key: secretDrafts["EMBEDDING_API_KEY"] || undefined,
          model: form["EMBEDDING_MODEL_NAME"],
        },
      ),
    onSuccess: (res) =>
      setTestResult({ ok: res.success, message: res.message, latency: res.latencyMs }),
    onError: (err: Error) => setTestResult({ ok: false, message: err.message }),
  });

  const testInfraMutation = useMutation({
    mutationFn: () =>
      apiClient.post<{ success: boolean; message: string; latencyMs: number | null }>(
        `/admin/config/${category.key}/test`,
        { values: { ...form, ...secretDrafts } },
      ),
    onSuccess: (res) =>
      setTestResult({ ok: res.success, message: res.message, latency: res.latencyMs }),
    onError: (err: Error) => setTestResult({ ok: false, message: err.message }),
  });

  const canTest =
    category.key === "llm" || category.key === "embedding" || TESTABLE_INFRA.has(category.key);
  const isTesting =
    testLLMMutation.isPending || testEmbeddingMutation.isPending || testInfraMutation.isPending;

  function runTest() {
    setTestResult(null);
    if (category.key === "llm") testLLMMutation.mutate();
    else if (category.key === "embedding") testEmbeddingMutation.mutate();
    else testInfraMutation.mutate();
  }

  function handleSave() {
    setSaveResult(null);
    const values: Record<string, unknown> = { ...form };
    for (const [k, v] of Object.entries(secretDrafts)) {
      if (v !== "") values[k] = v;
    }
    saveMutation.mutate(values);
  }

  if (isLoading) {
    return (
      <div className="border border-border bg-card p-8 text-sm text-muted-foreground">
        加载配置中…
      </div>
    );
  }
  if (isError || !data) {
    return (
      <div className="border border-destructive/30 bg-destructive/5 p-8 text-sm text-destructive">
        配置加载失败，请刷新重试。
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="border border-border bg-card p-6">
        <SectionHeader
          title={category.label}
          action={
            <div className="flex gap-2">
              {canTest && (
                <Btn variant="outline" onClick={runTest} disabled={isTesting}>
                  {isTesting ? (
                    <Loader2 className="size-3 animate-spin" />
                  ) : (
                    <Waypoints className="size-3" />
                  )}
                  测试连接
                </Btn>
              )}
              <Btn
                variant="ghost"
                onClick={() => resetMutation.mutate()}
                disabled={resetMutation.isPending}
              >
                <RotateCcw className="size-3" />
                恢复默认
              </Btn>
              <Btn variant="primary" onClick={handleSave} disabled={saveMutation.isPending}>
                {saveMutation.isPending ? (
                  <Loader2 className="size-3 animate-spin" />
                ) : (
                  <Save className="size-3" />
                )}
                保存
              </Btn>
            </div>
          }
        />
        <p className="mb-5 -mt-2 text-xs text-muted-foreground">{category.description}</p>

        {testResult && (
          <div
            className={`mb-4 flex items-start gap-2 rounded border px-3 py-2 text-xs ${
              testResult.ok
                ? "border-success/30 bg-success/10 text-success"
                : "border-destructive/30 bg-destructive/10 text-destructive"
            }`}
          >
            {testResult.ok ? (
              <CheckCircle2 className="mt-0.5 size-3.5 shrink-0" />
            ) : (
              <XCircle className="mt-0.5 size-3.5 shrink-0" />
            )}
            <span>
              {testResult.message}
              {testResult.latency != null && (
                <span className="ml-2 font-mono">({testResult.latency}ms)</span>
              )}
            </span>
          </div>
        )}

        {saveResult && (
          <div
            className={`mb-4 rounded border px-3 py-2 text-xs ${
              saveResult.ok
                ? "border-success/30 bg-success/10 text-success"
                : "border-destructive/30 bg-destructive/10 text-destructive"
            }`}
          >
            {saveResult.message}
            {saveResult.restart && saveResult.restart.length > 0 && (
              <div className="mt-1 text-warning">
                需要重启后端服务才能生效的字段：{saveResult.restart.join("、")}
              </div>
            )}
          </div>
        )}

        <div className="space-y-4">
          {data.fields.map((f) => (
            <FieldRow
              key={f.key}
              field={f}
              value={form[f.key]}
              secretDraft={secretDrafts[f.key] ?? ""}
              onChange={(v) => setForm((s) => ({ ...s, [f.key]: v }))}
              onSecretChange={(v) => setSecretDrafts((s) => ({ ...s, [f.key]: v }))}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------------------------
// 单个字段输入控件
// ------------------------------------------------------------------------------------

function FieldRow({
  field,
  value,
  secretDraft,
  onChange,
  onSecretChange,
}: {
  field: FieldMeta;
  value: FormValue | undefined;
  secretDraft: string;
  onChange: (v: FormValue) => void;
  onSecretChange: (v: string) => void;
}) {
  const inputCls =
    "w-full rounded border border-border bg-background px-3 py-2 text-sm outline-none transition focus:border-primary/50";

  return (
    <div className="grid grid-cols-[220px_1fr] items-start gap-4 border-b border-border/60 pb-4 last:border-0 last:pb-0">
      <div>
        <div className="flex items-center gap-2 text-sm font-medium">
          {field.label}
          {field.restartRequired && <Badge tone="warning">重启生效</Badge>}
        </div>
        <div className="mt-1 font-mono text-[10px] text-muted-foreground">{field.key}</div>
        {field.description && (
          <p className="mt-1 text-xs text-muted-foreground">{field.description}</p>
        )}
      </div>

      <div>
        {field.secret ? (
          <div className="flex items-center gap-2">
            <input
              type="password"
              autoComplete="new-password"
              className={inputCls}
              placeholder={
                secretDraft === "__CLEAR__"
                  ? "将在保存时清除"
                  : field.configured
                    ? `当前已配置（${field.value}），留空则不修改`
                    : field.placeholder || "尚未配置，输入后保存"
              }
              value={secretDraft === "__CLEAR__" ? "" : secretDraft}
              disabled={secretDraft === "__CLEAR__"}
              onChange={(e) => onSecretChange(e.target.value)}
            />
            {field.configured && (
              <button
                type="button"
                title="清除已保存的密钥"
                onClick={() => onSecretChange(secretDraft === "__CLEAR__" ? "" : "__CLEAR__")}
                className={`shrink-0 rounded border p-2 transition ${
                  secretDraft === "__CLEAR__"
                    ? "border-destructive/40 bg-destructive/10 text-destructive"
                    : "border-border text-muted-foreground hover:border-destructive/40 hover:text-destructive"
                }`}
              >
                <Eraser className="size-3.5" />
              </button>
            )}
          </div>
        ) : field.type === "bool" ? (
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={Boolean(value)}
              onChange={(e) => onChange(e.target.checked)}
              className="size-4 accent-primary"
            />
            {value ? "已启用" : "已关闭"}
          </label>
        ) : field.type === "int" || field.type === "float" ? (
          <input
            type="number"
            step={field.type === "float" ? "0.01" : "1"}
            className={inputCls}
            value={value === undefined ? "" : String(value)}
            onChange={(e) =>
              onChange(
                field.type === "int"
                  ? parseInt(e.target.value || "0", 10)
                  : parseFloat(e.target.value || "0"),
              )
            }
          />
        ) : field.type === "list" ? (
          <input
            type="text"
            className={inputCls}
            placeholder={field.placeholder}
            value={value === undefined ? "" : String(value)}
            onChange={(e) => onChange(e.target.value)}
          />
        ) : (
          <input
            type="text"
            className={inputCls}
            placeholder={field.placeholder}
            value={value === undefined ? "" : String(value)}
            onChange={(e) => onChange(e.target.value)}
          />
        )}
      </div>
    </div>
  );
}
