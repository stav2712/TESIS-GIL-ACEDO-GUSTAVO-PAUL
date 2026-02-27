import { getToken } from "./auth";

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
};

export type QueryResponse = {
  conversation_id: string;
  report_id: string;
  sql: string;
  timestamp: string;
  latency_ms: number;
  columns: string[];
  rows: Record<string, unknown>[];
  page: number;
  page_size: number;
  row_count: number;
  selected_report_id: string | null;
};

async function request<T>(url: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();

  // HeadersInit puede ser Headers | string[][] | Record<string,string>
  // Para poder setear claves sin pelear con tipos, usamos Headers.
  const headers = new Headers(init.headers);

  // Setea Content-Type por defecto si no existe ya
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  // Setea Authorization si hay token
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const res = await fetch(url, { ...init, headers });
  if (!res.ok) throw new Error(await res.text());
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
  await request(`/api/orchestrator/conversations/${conversationId}/delete`, { method: "POST" });
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
    body: JSON.stringify({ nl, conversation_id: conversationId, page, page_size: pageSize }),
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
  if (!res.ok) throw new Error(await res.text());
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
  if (!res.ok) throw new Error(await res.text());

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${reportId}.${format}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}