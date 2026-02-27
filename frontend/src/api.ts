import { getToken } from "./auth";

export type QueryResponse = {
  report_id: string;
  sql: string;
  latency_ms: number;
  columns: string[];
  rows: Record<string, unknown>[];
  page: number;
  page_size: number;
  row_count: number;
};

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const token = getToken();

  // HeadersInit es una unión (Headers | string[][] | Record<string,string>)
  // así que lo más seguro es normalizarlo a Headers.
  const headers = new Headers(init?.headers);

  // Aseguramos JSON por defecto (y permitimos que el caller lo sobreescriba si quiere)
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  // Solo el orquestador requiere token, pero podemos enviarlo siempre sin problema
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(url, { ...init, headers });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }

  return (await res.json()) as T;
}

// Identity (/auth)
export async function authLogin(username: string, password: string): Promise<string> {
  const data = await request<{ access_token: string; token_type: string }>(
    "/api/identity/auth",
    { method: "POST", body: JSON.stringify({ username, password }) }
  );
  return data.access_token;
}

// Orchestrator
export async function runQuery(nl: string, page: number, pageSize: number): Promise<QueryResponse> {
  return request<QueryResponse>("/api/orchestrator/query", {
    method: "POST",
    body: JSON.stringify({ nl, page, page_size: pageSize }),
  });
}

export async function sendFeedback(reportId: string, value: "up" | "down"): Promise<void> {
  await request<{ ok: boolean }>(`/api/orchestrator/reports/${reportId}/feedback`, {
    method: "POST",
    body: JSON.stringify({ value }),
  });
}

export async function downloadExport(reportId: string, format: "csv" | "xlsx" | "pdf"): Promise<void> {
  const token = getToken();

  const headers = new Headers();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`/api/orchestrator/reports/${reportId}/export?format=${format}`, {
    headers: token ? headers : undefined,
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }

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

