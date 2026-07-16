const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";

// 普通 JSON 请求的超时时间；文件上传单独给更长的超时（见 upload()），
// 避免大文件在慢网络下还没传完就被判定为失败。
const DEFAULT_TIMEOUT_MS = 30_000;
const UPLOAD_TIMEOUT_MS = 180_000;

interface ApiResponse<T = unknown> {
  code: number;
  message: string;
  data: T;
  request_id?: string;
  timestamp?: string;
}

/**
 * 包一层 fetch：
 * 1) 用 AbortController 加超时，避免后端/依赖服务挂起时请求无限期卡住（用户只会看到转圈，
 *    既不成功也不报错）；
 * 2) 把浏览器原生抛出的网络级错误（TypeError: Failed to fetch / NetworkError，通常意味着
 *    后端未启动、地址配置错误、CORS 拒绝或断网）转换成能自诊断的中文提示，而不是把原始的
 *    "Failed to fetch" 直接抛给用户——那对定位问题没有任何帮助。
 */
async function fetchWithDiagnostics(url: string, init: RequestInit, timeoutMs: number): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new Error(`请求超时（超过 ${Math.round(timeoutMs / 1000)} 秒未响应），请检查后端服务是否正常运行`);
    }
    // fetch() 对网络层错误（连接被拒绝/DNS 失败/CORS 预检被拒/混合内容被浏览器拦截等）
    // 统一抛出 TypeError，浏览器不会告诉我们具体原因，因此这里给出可能原因列表帮助排查，
    // 而不是让用户只看到一句无法采取任何行动的 "Failed to fetch"。
    if (err instanceof TypeError) {
      throw new Error(
        `无法连接后端服务（${url}）。可能原因：1) 后端服务未启动或地址配置错误（当前 VITE_API_BASE_URL=${API_BASE_URL}）；` +
          `2) 后端 CORS_ORIGINS 未包含当前前端域名；3) 网络不通或被防火墙/代理拦截。`,
      );
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  private getAuthHeaders(): Record<string, string> {
    const token = localStorage.getItem("access_token");
    return token ? { Authorization: `Bearer ${token}` } : {};
  }

  private async handleResponse<T>(response: Response): Promise<T> {
    if (response.status === 401) {
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
      window.location.href = "/login";
      throw new Error("认证已过期，请重新登录");
    }

    // 服务器/反向代理在某些错误场景下（502/504 网关错误、413 请求体过大等）可能返回非 JSON
    // 的纯文本或 HTML 响应体。之前这里直接调用 response.json()，解析失败会抛出
    // "Unexpected token < in JSON..." 这种同样难以理解的错误，这里改为优雅降级。
    let json: ApiResponse<T> | null = null;
    try {
      json = await response.json();
    } catch {
      if (!response.ok) {
        throw new Error(`请求失败（HTTP ${response.status} ${response.statusText || ""}）`.trim());
      }
      throw new Error("响应格式错误：服务器未返回有效的 JSON 数据");
    }

    if (!json || json.code !== 0) {
      throw new Error(json?.message || `请求失败（HTTP ${response.status}）`);
    }
    return json.data;
  }

  private async tryRefreshToken(): Promise<boolean> {
    const refreshToken = localStorage.getItem("refresh_token");
    if (!refreshToken) return false;
    try {
      const resp = await fetchWithDiagnostics(
        `${this.baseUrl}/auth/refresh`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: refreshToken }),
        },
        DEFAULT_TIMEOUT_MS,
      );
      if (!resp.ok) return false;
      const json: ApiResponse<{ access_token: string; refresh_token: string }> = await resp.json();
      if (json.code !== 0) return false;
      localStorage.setItem("access_token", json.data.access_token);
      localStorage.setItem("refresh_token", json.data.refresh_token);
      return true;
    } catch {
      return false;
    }
  }

  async get<T = unknown>(
    path: string,
    params?: Record<string, string | number | boolean | undefined>,
  ): Promise<T> {
    const url = new URL(`${this.baseUrl}${path}`);
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined) url.searchParams.set(key, String(value));
      });
    }
    let response = await fetchWithDiagnostics(url.toString(), { headers: this.getAuthHeaders() }, DEFAULT_TIMEOUT_MS);
    if (response.status === 401) {
      const refreshed = await this.tryRefreshToken();
      if (refreshed) {
        response = await fetchWithDiagnostics(url.toString(), { headers: this.getAuthHeaders() }, DEFAULT_TIMEOUT_MS);
      }
    }
    return this.handleResponse<T>(response);
  }

  async post<T = unknown>(path: string, body?: unknown, skipRefresh = false): Promise<T> {
    const doFetch = () =>
      fetchWithDiagnostics(
        `${this.baseUrl}${path}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json", ...this.getAuthHeaders() },
          body: body ? JSON.stringify(body) : undefined,
        },
        DEFAULT_TIMEOUT_MS,
      );

    let response = await doFetch();
    if (!skipRefresh && response.status === 401) {
      const refreshed = await this.tryRefreshToken();
      if (refreshed) {
        response = await doFetch();
      }
    }
    if (skipRefresh && response.status === 401) {
      const json: ApiResponse<T> = await response
        .json()
        .catch(() => ({ code: 40100, message: "用户名或密码错误", data: null as T }));
      throw new Error(json.message || "用户名或密码错误");
    }
    return this.handleResponse<T>(response);
  }

  async put<T = unknown>(path: string, body?: unknown): Promise<T> {
    const doFetch = () =>
      fetchWithDiagnostics(
        `${this.baseUrl}${path}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json", ...this.getAuthHeaders() },
          body: body ? JSON.stringify(body) : undefined,
        },
        DEFAULT_TIMEOUT_MS,
      );

    let response = await doFetch();
    if (response.status === 401) {
      const refreshed = await this.tryRefreshToken();
      if (refreshed) {
        response = await doFetch();
      }
    }
    return this.handleResponse<T>(response);
  }

  async upload<T = unknown>(path: string, formData: FormData): Promise<T> {
    // 注意：不要手动设置 Content-Type，浏览器会自动带上正确的 multipart 边界（boundary）。
    const doFetch = () =>
      fetchWithDiagnostics(
        `${this.baseUrl}${path}`,
        {
          method: "POST",
          headers: this.getAuthHeaders(),
          body: formData,
        },
        UPLOAD_TIMEOUT_MS,
      );

    let response = await doFetch();
    if (response.status === 401) {
      const refreshed = await this.tryRefreshToken();
      if (refreshed) {
        response = await doFetch();
      }
    }
    return this.handleResponse<T>(response);
  }
}

export const apiClient = new ApiClient(API_BASE_URL);
