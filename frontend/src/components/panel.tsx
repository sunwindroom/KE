import type { ReactNode } from "react";

export function SectionHeader({
  title, action,
}: { title: string; action?: ReactNode }) {
  return (
    <div className="mb-4 flex items-center justify-between">
      <h2 className="flex items-center gap-2 text-sm font-bold uppercase tracking-[0.18em]">
        <span className="size-1.5 bg-primary" />
        {title}
      </h2>
      {action}
    </div>
  );
}

export function PageHeader({
  eyebrow, title, description, actions,
}: { eyebrow: string; title: string; description: string; actions?: ReactNode }) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div>
        <div className="font-mono text-[10px] uppercase tracking-[0.3em] text-primary">{eyebrow}</div>
        <h1 className="mt-2 text-3xl font-extrabold tracking-tight">{title}</h1>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">{description}</p>
      </div>
      {actions && <div className="flex gap-2">{actions}</div>}
    </div>
  );
}

export function Kpi({
  label, value, meta, tone = "default",
}: { label: string; value: string; meta?: string; tone?: "default" | "success" | "warning" | "primary" }) {
  const toneCls =
    tone === "success" ? "text-success"
    : tone === "warning" ? "text-warning"
    : tone === "primary" ? "text-primary"
    : "text-muted-foreground";
  return (
    <div className="group border border-border bg-card p-5 transition-colors hover:border-primary/40">
      <div className="mb-1 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">{label}</div>
      <div className="flex items-baseline gap-2">
        <span className="font-mono text-3xl font-extrabold tracking-tight">{value}</span>
        {meta && <span className={"text-[10px] font-bold " + toneCls}>{meta}</span>}
      </div>
    </div>
  );
}

export function Btn({
  children, variant = "ghost", className = "", ...rest
}: {
  children: ReactNode; variant?: "primary" | "ghost" | "outline"; className?: string;
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const cls =
    variant === "primary"
      ? "bg-primary text-primary-foreground hover:bg-primary/90"
      : variant === "outline"
      ? "border border-primary/40 text-primary hover:bg-primary hover:text-primary-foreground"
      : "border border-border text-muted-foreground hover:text-foreground hover:border-primary/40";
  return (
    <button
      {...rest}
      className={`inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-[11px] font-bold uppercase tracking-widest transition ${cls} ${className}`}
    >
      {children}
    </button>
  );
}

export function Badge({
  children, tone = "default",
}: { children: ReactNode; tone?: "default" | "success" | "warning" | "primary" | "danger" }) {
  const map: Record<string, string> = {
    default: "border-border bg-white/5 text-muted-foreground",
    success: "border-success/30 bg-success/10 text-success",
    warning: "border-warning/30 bg-warning/10 text-warning",
    primary: "border-primary/30 bg-primary/10 text-primary",
    danger: "border-destructive/30 bg-destructive/10 text-destructive",
  };
  return (
    <span className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-widest ${map[tone]}`}>
      {children}
    </span>
  );
}
