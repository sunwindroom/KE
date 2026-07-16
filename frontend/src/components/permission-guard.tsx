import type { ReactNode } from "react";
import { useAuth } from "../lib/auth";

interface PermissionGuardProps {
  children: ReactNode;
  roles?: string[];
  domain?: string;
  fallback?: ReactNode;
}

export function PermissionGuard({ children, roles, domain, fallback = null }: PermissionGuardProps) {
  const { user, hasRole, hasDomain } = useAuth();

  if (!user) return <>{fallback}</>;

  if (roles && !hasRole(...roles)) return <>{fallback}</>;
  if (domain && !hasDomain(domain)) return <>{fallback}</>;

  return <>{children}</>;
}