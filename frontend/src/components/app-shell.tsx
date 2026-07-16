import { Link, useRouterState, useNavigate } from "@tanstack/react-router";
import { useState, useRef, useEffect, type ReactNode } from "react";
import {
  LayoutDashboard,
  Database,
  Sparkles,
  Network,
  Search,
  Bot,
  Cpu,
  MessagesSquare,
  GitBranch,
  ShieldCheck,
  Settings2,
  SlidersHorizontal,
  Bell,
  Command,
  LogOut,
  User,
  KeyRound,
  X,
} from "lucide-react";
import { useAuth } from "../lib/auth";
import { apiClient } from "../lib/api-client";

type NavItem = { to: string; label: string; icon: typeof LayoutDashboard };

const CORE: NavItem[] = [
  { to: "/", label: "工作台", icon: LayoutDashboard },
  { to: "/ingestion", label: "数据接入", icon: Database },
  { to: "/extraction", label: "知识抽取", icon: Sparkles },
  { to: "/ontology", label: "本体图谱", icon: Network },
  { to: "/rag", label: "RAG 检索", icon: Search },
  { to: "/agent", label: "智能 Agent", icon: Bot },
];

const OPS: NavItem[] = [
  { to: "/finetune", label: "微调控制台", icon: Cpu },
  { to: "/qa", label: "智能问答", icon: MessagesSquare },
  { to: "/graph", label: "图谱可视化", icon: GitBranch },
  { to: "/governance", label: "知识治理", icon: ShieldCheck },
  { to: "/admin", label: "系统管理", icon: Settings2 },
];

// 仅系统管理员可见：生产环境配置中心（大模型 API、安全策略、基础设施连接等）。
const ADMIN_ONLY: NavItem[] = [{ to: "/settings", label: "系统设置", icon: SlidersHorizontal }];

const CRUMBS: Record<string, string> = {
  "/": "工作台概览",
  "/ingestion": "数据接入",
  "/extraction": "知识抽取与加工",
  "/ontology": "本体与知识图谱",
  "/rag": "RAG 检索增强",
  "/agent": "Agent 编排",
  "/finetune": "领域微调",
  "/qa": "智能问答",
  "/graph": "知识图谱可视化",
  "/governance": "知识运营与治理",
  "/admin": "系统管理",
  "/settings": "系统设置",
};

function NavLink({ item, active }: { item: NavItem; active: boolean }) {
  const Icon = item.icon;
  return (
    <Link
      to={item.to}
      className={
        "flex items-center gap-3 rounded px-3 py-2 text-sm transition-colors " +
        (active
          ? "border border-primary/25 bg-primary/10 text-primary font-medium"
          : "border border-transparent text-muted-foreground hover:bg-white/5 hover:text-foreground")
      }
    >
      <Icon className="size-4 shrink-0" strokeWidth={1.75} />
      <span>{item.label}</span>
    </Link>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const crumb = CRUMBS[pathname] ?? "模块";
  const { hasRole } = useAuth();

  return (
    <div className="flex h-screen w-full bg-background text-foreground">
      {/* Sidebar */}
      <nav className="flex w-64 shrink-0 flex-col border-r border-border bg-sidebar">
        <Link to="/" className="flex items-center gap-3 border-b border-sidebar-border p-5">
          <div className="grid size-7 place-items-center rounded-sm bg-primary shadow-glow-sm">
            <div className="size-2.5 rotate-45 border-2 border-primary-foreground" />
          </div>
          <div>
            <div className="text-[15px] font-extrabold uppercase tracking-tight leading-none">
              Aether PHM
            </div>
            <div className="mt-1 font-mono text-[9px] uppercase tracking-[0.2em] text-muted-foreground">
              Knowledge · Engineering
            </div>
          </div>
        </Link>

        <div className="flex-1 space-y-1 overflow-y-auto px-3 py-5">
          <div className="mb-2 px-3 text-[10px] font-bold uppercase tracking-[0.22em] text-muted-foreground">
            核心平台
          </div>
          {CORE.map((i) => (
            <NavLink key={i.to} item={i} active={pathname === i.to} />
          ))}
          <div className="mt-6 mb-2 px-3 text-[10px] font-bold uppercase tracking-[0.22em] text-muted-foreground">
            分析与治理
          </div>
          {OPS.map((i) => (
            <NavLink key={i.to} item={i} active={pathname === i.to} />
          ))}
          {hasRole("admin") && (
            <>
              <div className="mt-6 mb-2 px-3 text-[10px] font-bold uppercase tracking-[0.22em] text-muted-foreground">
                管理员专属
              </div>
              {ADMIN_ONLY.map((i) => (
                <NavLink key={i.to} item={i} active={pathname === i.to} />
              ))}
            </>
          )}
        </div>

        <div className="border-t border-sidebar-border p-4">
          <div className="rounded border border-border bg-card/40 p-3">
            <div className="mb-2 font-mono text-[9px] uppercase tracking-[0.2em] text-muted-foreground">
              System Status
            </div>
            <div className="flex items-center gap-2">
              <span className="size-1.5 animate-pulse rounded-full bg-success" />
              <span className="font-mono text-[11px]">Core-Indexer Active</span>
            </div>
          </div>
          <UserMenu />
        </div>
      </nav>

      {/* Main */}
      <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <header className="z-10 flex h-14 shrink-0 items-center justify-between border-b border-border bg-background/80 px-8 backdrop-blur">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span>工作台</span>
            <span className="opacity-50">/</span>
            <span className="font-medium text-foreground">{crumb}</span>
          </div>
          <div className="flex items-center gap-3">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground/60" />
              <input
                type="text"
                placeholder="搜索知识条目、实体或指令…"
                className="w-72 rounded border border-border bg-white/5 py-1.5 pl-8 pr-16 text-xs placeholder:text-muted-foreground/60 focus:border-primary/50 focus:outline-none"
              />
              <span className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 rounded border border-border bg-background px-1.5 py-0.5 font-mono text-[9px] text-muted-foreground">
                ⌘K
              </span>
            </div>
            <button className="grid size-8 place-items-center rounded border border-border hover:bg-white/5">
              <Command className="size-3.5 text-muted-foreground" />
            </button>
            <button className="relative grid size-8 place-items-center rounded border border-border hover:bg-white/5">
              <Bell className="size-3.5 text-muted-foreground" />
              <span className="absolute right-1.5 top-1.5 size-1.5 rounded-full bg-warning" />
            </button>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto">{children}</div>
      </main>
    </div>
  );
}

function ChangePasswordModal({ onClose }: { onClose: () => void }) {
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);
  const [isPending, setIsPending] = useState(false);
  const { logout } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async () => {
    setError("");
    if (newPassword.length < 8) {
      setError("新密码长度至少为 8 位");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("两次输入的新密码不一致");
      return;
    }
    setIsPending(true);
    try {
      await apiClient.post("/auth/change-password", {
        old_password: oldPassword,
        new_password: newPassword,
      });
      setSuccess(true);
      setTimeout(() => {
        logout();
        navigate({ to: "/login" });
      }, 1200);
    } catch (e) {
      setError((e as Error).message || "修改失败");
    } finally {
      setIsPending(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-full max-w-sm border border-border bg-card p-6">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-sm font-bold uppercase tracking-widest">修改密码</h3>
          <button onClick={onClose}>
            <X className="size-4 text-muted-foreground" />
          </button>
        </div>
        <div className="space-y-3">
          <input
            type="password"
            value={oldPassword}
            onChange={(e) => setOldPassword(e.target.value)}
            placeholder="当前密码"
            className="w-full rounded border border-border bg-white/5 p-2 text-xs"
          />
          <input
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            placeholder="新密码（至少 8 位）"
            className="w-full rounded border border-border bg-white/5 p-2 text-xs"
          />
          <input
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            placeholder="确认新密码"
            className="w-full rounded border border-border bg-white/5 p-2 text-xs"
          />
          {error && <div className="text-[11px] text-destructive">{error}</div>}
          {success && <div className="text-[11px] text-success">密码已更新，即将退出登录…</div>}
          <button
            onClick={handleSubmit}
            disabled={!oldPassword || !newPassword || !confirmPassword || isPending}
            className="w-full rounded bg-primary py-2 text-xs font-bold uppercase tracking-widest text-primary-foreground disabled:opacity-50"
          >
            {isPending ? "提交中…" : "确认修改"}
          </button>
        </div>
      </div>
    </div>
  );
}

function UserMenu() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [showChangePassword, setShowChangePassword] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const handleLogout = () => {
    logout();
    navigate({ to: "/login" });
  };

  return (
    <div className="mt-3 relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-3 rounded px-1 py-1 hover:bg-white/5 transition"
      >
        <div className="grid size-8 place-items-center rounded-full border border-border bg-primary/10">
          <User className="size-4 text-primary" />
        </div>
        <div className="text-xs text-left flex-1 min-w-0">
          <div className="font-medium truncate">{user?.userName || "用户"}</div>
          <div className="font-mono text-[9px] uppercase tracking-wider text-muted-foreground truncate">
            {user?.role || "v2.4.0-stable"}
          </div>
        </div>
      </button>
      {open && (
        <div className="absolute bottom-full left-0 mb-1 w-full rounded border border-border bg-card shadow-lg z-50">
          <button
            onClick={() => {
              setShowChangePassword(true);
              setOpen(false);
            }}
            className="flex w-full items-center gap-2 px-3 py-2 text-xs text-muted-foreground hover:bg-white/5 hover:text-foreground transition"
          >
            <KeyRound className="size-3.5" />
            修改密码
          </button>
          <button
            onClick={handleLogout}
            className="flex w-full items-center gap-2 px-3 py-2 text-xs text-muted-foreground hover:bg-white/5 hover:text-foreground transition"
          >
            <LogOut className="size-3.5" />
            退出登录
          </button>
        </div>
      )}
      {showChangePassword && <ChangePasswordModal onClose={() => setShowChangePassword(false)} />}
    </div>
  );
}
