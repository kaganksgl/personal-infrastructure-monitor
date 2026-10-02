import type {
  Agent,
  AgentCreated,
  Alert,
  AlertRule,
  AuthStatus,
  CatalogEntry,
  HistoryResponse,
  LatestSample,
  MetricName,
  StatsResponse,
  User,
} from "../types/api";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

type Listener = () => void;
const unauthorizedListeners = new Set<Listener>();

/** Lets the auth context react when any request discovers the session expired. */
export function onUnauthorized(listener: Listener): () => void {
  unauthorizedListeners.add(listener);
  return () => unauthorizedListeners.delete(listener);
}

function errorMessage(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg);
  }
  return fallback;
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    ...init,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      // Required by the backend's CSRF check for state-changing requests.
      "X-Requested-With": "infrawatch",
      ...init.headers,
    },
  });
  if (response.status === 204) return undefined as T;
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith("/auth/")) {
      unauthorizedListeners.forEach((l) => l());
    }
    throw new ApiError(response.status, errorMessage(body, response.statusText));
  }
  return body as T;
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export type Window = { range: string } | { start: string; end?: string };

function windowQuery(window: Window, metrics: MetricName[]): string {
  const params = new URLSearchParams({ metrics: metrics.join(",") });
  if ("range" in window) params.set("range", window.range);
  else {
    params.set("start", window.start);
    if (window.end) params.set("end", window.end);
  }
  return params.toString();
}

export const api = {
  authStatus: () => request<AuthStatus>("/auth/status"),
  me: () => request<User>("/auth/me"),
  login: (username: string, password: string) => post<User>("/auth/login", { username, password }),
  register: (username: string, password: string) =>
    post<User>("/auth/register", { username, password }),
  logout: () => post<void>("/auth/logout"),

  agents: () => request<Agent[]>("/agents"),
  agent: (id: string) => request<Agent>(`/agents/${encodeURIComponent(id)}`),
  createAgent: (agent_id: string, display_name?: string) =>
    post<AgentCreated>("/agents", { agent_id, display_name: display_name || null }),
  deleteAgent: (id: string) =>
    request<void>(`/agents/${encodeURIComponent(id)}`, { method: "DELETE" }),
  rotateKey: (id: string) => post<AgentCreated>(`/agents/${encodeURIComponent(id)}/rotate-key`),

  catalog: () => request<CatalogEntry[]>("/metrics/catalog"),
  history: (id: string, window: Window, metrics: MetricName[]) =>
    request<HistoryResponse>(`/metrics/${encodeURIComponent(id)}?${windowQuery(window, metrics)}`),
  stats: (id: string, window: Window, metrics: MetricName[]) =>
    request<StatsResponse>(
      `/metrics/${encodeURIComponent(id)}/stats?${windowQuery(window, metrics)}`,
    ),
  latest: (id: string) => request<LatestSample>(`/metrics/${encodeURIComponent(id)}/latest`),

  alerts: (params: Record<string, string> = {}) =>
    request<Alert[]>(`/alerts?${new URLSearchParams(params)}`),
  acknowledge: (id: number) => post<Alert>(`/alerts/${id}/acknowledge`),
  rules: () => request<AlertRule[]>("/alerts/rules"),
  createRule: (rule: Omit<AlertRule, "id" | "created_at">) => post<AlertRule>("/alerts/rules", rule),
  updateRule: (id: number, changes: Partial<AlertRule>) =>
    request<AlertRule>(`/alerts/rules/${id}`, { method: "PATCH", body: JSON.stringify(changes) }),
  deleteRule: (id: number) => request<void>(`/alerts/rules/${id}`, { method: "DELETE" }),
};
