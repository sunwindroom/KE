import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from "react";
import { apiClient } from "./api-client";

interface UserInfo {
  userId: string;
  userName: string;
  role: string;
  domainScope: string[];
  maxClassificationLevel: string;
}

interface AuthContextType {
  user: UserInfo | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  hasDomain: (domain: string) => boolean;
  hasRole: (...roles: string[]) => boolean;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (token) {
      apiClient
        .get<UserInfo>("/auth/me")
        .then(setUser)
        .catch(() => {
          localStorage.removeItem("access_token");
          localStorage.removeItem("refresh_token");
        })
        .finally(() => setIsLoading(false));
    } else {
      setIsLoading(false);
    }
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const data = await apiClient.post<{
      access_token: string;
      refresh_token: string;
      expires_in: number;
    }>("/auth/login", { username, password }, true);
    localStorage.setItem("access_token", data.access_token);
    localStorage.setItem("refresh_token", data.refresh_token);
    const userInfo = await apiClient.get<UserInfo>("/auth/me");
    setUser(userInfo);
  }, []);

  const logout = useCallback(() => {
    const refreshToken = localStorage.getItem("refresh_token");
    // 尽力而为地通知后端吊销 token；即使这个请求失败，也要立刻清空本地状态。
    apiClient
      .post("/auth/logout", refreshToken ? { refresh_token: refreshToken } : undefined)
      .catch(() => {});
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    setUser(null);
  }, []);

  const hasDomain = useCallback(
    (domain: string) => user?.domainScope?.includes(domain) ?? false,
    [user],
  );

  const hasRole = useCallback((...roles: string[]) => roles.includes(user?.role ?? ""), [user]);

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        isLoading,
        login,
        logout,
        hasDomain,
        hasRole,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
