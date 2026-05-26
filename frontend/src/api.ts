import { clearToken, getToken } from "./auth";

export type Conversation = {
  conversation_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  deleted: boolean;
  selected_report_id: string | null;
  last_preview: string | null;
};

export type ReportMeta = {
  report_id: string;
  conversation_id: string;
  user_id?: number;
  username?: string | null;
  profile?: string | null;
  nl: string;
  sql: string;
  timestamp: string;
  latency_ms: number;
  feedback: "positive" | "negative" | null;
};

export type ConversationDetail = {
  conversation: Conversation;
  reports: ReportMeta[];
};

export type ReportData = {
  columns: string[];
  rows: Record<string, unknown>[];
  page: number;
  page_size: number;
  row_count: number;
  total_count?: number | null;
  display_total_count?: number | null;
  total_pages?: number | null;
  max_result_window?: number | null;
  max_result_window_exceeded?: boolean;
  result_message?: string | null;
};

export type QueryResponse = ReportData & {
  conversation_id: string;
  report_id: string;
  sql: string;
  timestamp: string;
  latency_ms: number;
  selected_report_id: string | null;
  can_view_sql?: boolean;
};

export type Profile = {
  id: number;
  name: string;
  description: string;
  permissions: Record<string, boolean>;
  allowed_tables: string[];
  // Se conserva por compatibilidad con perfiles creados antes, pero el límite visual real ahora es global.
  max_display_rows?: number;
  max_page_size: number;
  is_system: boolean;
};

export type ProfilePayload = {
  name?: string;
  description?: string;
  permissions?: Record<string, boolean>;
  allowed_tables?: string[];
  max_page_size?: number;
};

export type AppUser = {
  id: number;
  username: string;
  full_name: string | null;
  profile: string | null;
  profile_id: number | null;
  is_active: boolean;
  created_at?: string | null;
};

export type AuditReport = {
  report_id: string;
  conversation_id: string;
  user_id: number;
  username?: string | null;
  full_name?: string | null;
  profile?: string | null;
  nl: string;
  sql: string;
  timestamp: string;
  latency_ms: number;
  feedback: "positive" | "negative" | null;
};

export type AuditList = {
  rows: AuditReport[];
  total_count: number;
  page: number;
  page_size: number;
  total_pages: number;
};

export type DashboardSummary = {
  total_reports: number;
  total_conversations: number;
  unique_users: number;
  feedback_positive: number;
  feedback_negative: number;
  latest_reports: AuditReport[];
  top_users: { user_id: number; username?: string | null; reports: number; last_at?: string | null }[];
};

export type SystemConfig = {
  query_display_max_rows: number;
  export_max_rows: number;
  export_max_rows_meaning: string;
  export_page_size: number;
  query_timeout_seconds: number;
  translator_timeout_seconds: number;
  schema_profile_path: string;
  allowed_tables: string[];
  translator_url_configured: boolean;
  query_url: string;
  terminology_url: string;
};

async function errorFromResponse(res: Response): Promise<string> {
  const raw = await res.text();

  if (!raw) return `Error HTTP ${res.status}`;

  try {
    const parsed = JSON.parse(raw);
    const detail = parsed?.detail ?? parsed?.error ?? parsed;

    if (typeof detail === "string") {
      try {
        const nested = JSON.parse(detail);
        return nested?.detail?.error || nested?.detail || nested?.error || detail;
      } catch {
        return detail;
      }
    }

    if (typeof detail?.error === "string") {
      const extra = detail.detail ? `: ${detail.detail}` : "";
      return `${detail.error}${extra}`;
    }

    return JSON.stringify(detail, null, 2);
  } catch {
    return raw;
  }
}

function filenameFromDisposition(disposition: string | null, fallback: string) {
  if (!disposition) return fallback;

  const utf8 = disposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8?.[1]) return decodeURIComponent(utf8[1].replaceAll('"', ""));

  const ascii = disposition.match(/filename="?([^"]+)"?/i);
  if (ascii?.[1]) return ascii[1];

  return fallback;
}

async function request<T>(url: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(init.headers);

  if (!headers.has("Content-Type") && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const res = await fetch(url, { ...init, headers });

  if (!res.ok) {
    if (res.status === 401) clearToken();
    throw new Error(await errorFromResponse(res));
  }

  return (await res.json()) as T;
}

// Identity
export async function authLogin(username: string, password: string): Promise<string> {
  const data = await request<{ access_token: string }>("/api/identity/auth", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });

  return data.access_token;
}

export async function getMe(): Promise<AppUser> {
  return request<AppUser>("/api/identity/me");
}

export async function listUsers(q?: string): Promise<AppUser[]> {
  const params = q ? `?q=${encodeURIComponent(q)}` : "";
  return request<AppUser[]>(`/api/identity/users${params}`);
}

export async function createUser(payload: {
  username: string;
  password: string;
  full_name?: string | null;
  profile_id?: number | null;
}): Promise<AppUser> {
  return request<AppUser>("/api/identity/users", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateUser(
  userId: number,
  payload: Partial<{
    username: string;
    password: string;
    full_name: string | null;
    profile_id: number | null;
    is_active: boolean;
  }>
): Promise<AppUser> {
  return request<AppUser>(`/api/identity/users/${userId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function listProfiles(): Promise<Profile[]> {
  return request<Profile[]>("/api/identity/profiles");
}

export async function createProfile(payload: ProfilePayload & { name: string }): Promise<Profile> {
  return request<Profile>("/api/identity/profiles", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateProfile(
  profileId: number,
  payload: ProfilePayload
): Promise<Profile> {
  return request<Profile>(`/api/identity/profiles/${profileId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

// Conversations
export async function listConversations(): Promise<Conversation[]> {
  return request<Conversation[]>("/api/orchestrator/conversations");
}

export async function createConversation(title?: string): Promise<Conversation> {
  return request<Conversation>("/api/orchestrator/conversations", {
    method: "POST",
    body: JSON.stringify({ title: title ?? null }),
  });
}

export async function getConversation(conversationId: string): Promise<ConversationDetail> {
  return request<ConversationDetail>(`/api/orchestrator/conversations/${conversationId}`);
}

export async function renameConversation(conversationId: string, title: string): Promise<void> {
  await request(`/api/orchestrator/conversations/${conversationId}/rename`, {
    method: "POST",
    body: JSON.stringify({ title }),
  });
}

export async function deleteConversation(conversationId: string): Promise<void> {
  await request(`/api/orchestrator/conversations/${conversationId}/delete`, {
    method: "POST",
  });
}

export async function selectConversationReport(conversationId: string, reportId: string): Promise<void> {
  await request(`/api/orchestrator/conversations/${conversationId}/select`, {
    method: "POST",
    body: JSON.stringify({ report_id: reportId }),
  });
}

// Query
export async function runQuery(
  nl: string,
  conversationId: string | null,
  page: number,
  pageSize: number
): Promise<QueryResponse> {
  return request<QueryResponse>("/api/orchestrator/query", {
    method: "POST",
    body: JSON.stringify({
      nl,
      conversation_id: conversationId,
      page,
      page_size: pageSize,
    }),
  });
}

// Reports
export async function getReportMeta(reportId: string): Promise<ReportMeta> {
  return request<ReportMeta>(`/api/orchestrator/reports/${reportId}/meta`);
}

export async function getReportData(reportId: string, page: number, pageSize: number): Promise<ReportData> {
  const token = getToken();

  const res = await fetch(`/api/orchestrator/reports/${reportId}/data?page=${page}&page_size=${pageSize}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });

  if (!res.ok) {
    if (res.status === 401) clearToken();
    throw new Error(await errorFromResponse(res));
  }

  return (await res.json()) as ReportData;
}

export async function sendFeedback(reportId: string, value: "up" | "down"): Promise<void> {
  await request(`/api/orchestrator/reports/${reportId}/feedback`, {
    method: "POST",
    body: JSON.stringify({ value }),
  });
}

export async function downloadExport(reportId: string, format: "csv" | "xlsx" | "pdf"): Promise<void> {
  const token = getToken();

  const res = await fetch(`/api/orchestrator/reports/${reportId}/export?format=${format}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });

  if (!res.ok) {
    if (res.status === 401) clearToken();
    throw new Error(await errorFromResponse(res));
  }

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");

  a.href = url;
  a.download = filenameFromDisposition(res.headers.get("Content-Disposition"), `reporte-${reportId}.${format}`);

  document.body.appendChild(a);
  a.click();
  a.remove();

  URL.revokeObjectURL(url);
}

// Admin/platform
export async function getAdminDashboard(): Promise<DashboardSummary> {
  return request<DashboardSummary>("/api/orchestrator/admin/dashboard");
}

export async function listAuditReports(params: {
  page: number;
  page_size: number;
  user_id?: number | null;
  q?: string | null;
}): Promise<AuditList> {
  const sp = new URLSearchParams();
  sp.set("page", String(params.page));
  sp.set("page_size", String(params.page_size));
  if (params.user_id) sp.set("user_id", String(params.user_id));
  if (params.q) sp.set("q", params.q);
  return request<AuditList>(`/api/orchestrator/admin/audit/reports?${sp.toString()}`);
}

export async function getSystemConfig(): Promise<SystemConfig> {
  return request<SystemConfig>("/api/orchestrator/system/config");
}
