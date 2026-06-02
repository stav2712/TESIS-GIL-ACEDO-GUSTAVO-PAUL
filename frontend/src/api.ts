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
  full_name?: string | null;
  profile?: string | null;
  nl: string;
  sql: string;
  timestamp: string;
  latency_ms: number;
  feedback: "positive" | "negative" | null;
  nl_normalized?: string | null;
  schema_profile?: string | null;
  resolved_terms?: unknown[];
  resolved_values?: unknown[];
  translator_strategy?: string | null;
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
  suppressed_columns?: string[];
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

export type QueryJobStatus = "queued" | "running" | "completed" | "failed" | "abandoned";

export type QueryJobStart = {
  job_id: string;
  conversation_id: string;
  status: QueryJobStatus;
};

export type QueryJob = {
  job_id: string;
  conversation_id: string;
  nl: string;
  page: number;
  page_size: number;
  status: QueryJobStatus;
  report_id: string | null;
  error: string | null;
  result: QueryResponse | null;
  created_at: string;
  updated_at: string;
  finished_at: string | null;
};

export type ColumnPermissionRule = {
  hidden?: string[];
  forbidden?: string[];
};

export type ColumnPermissions = Record<string, ColumnPermissionRule>;
export type TableAccessMode = "all" | "custom";

export type Profile = {
  id: number;
  name: string;
  description: string;
  permissions: Record<string, boolean>;
  allowed_tables: string[];
  table_access_mode?: TableAccessMode;
  column_permissions?: ColumnPermissions;
  max_display_rows?: number;
  max_page_size: number;
  is_system: boolean;
};

export type ProfilePayload = {
  name?: string;
  description?: string;
  permissions?: Record<string, boolean>;
  allowed_tables?: string[];
  table_access_mode?: TableAccessMode;
  column_permissions?: ColumnPermissions;
  max_page_size?: number;
};

export type AppUser = {
  id: number;
  username: string;
  full_name: string | null;
  email?: string | null;
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

type NumericLimit = {
  min: number;
  max: number;
  min_when_enabled?: number;
  unlimited_value?: number;
  warning_below?: number;
};

export type SystemConfig = {
  query_display_max_rows: number;
  export_max_rows: number;
  export_max_rows_meaning: string;
  export_page_size: number;
  query_timeout_seconds: number;
  email_enabled?: boolean;
  email_from?: string | null;
  translator_timeout_seconds: number;
  schema_profile_path: string;
  allowed_tables: string[];
  translator_url_configured: boolean;
  query_url: string;
  terminology_url: string;
  limits?: {
    query_display_max_rows: NumericLimit;
    export_max_rows: NumericLimit;
    query_timeout_seconds: NumericLimit;
  };
  warnings?: string[];
};

export type SystemSchema = {
  tables: Record<string, string[]>;
  errors?: Record<string, string>;
};

export type SystemConfigUpdatePayload = Partial<{
  query_display_max_rows: number;
  export_max_rows: number;
  query_timeout_seconds: number;
}>;

export type SystemServiceStatus = {
  key: "query" | "terminology" | "translator" | string;
  label: string;
  configured_url: string;
  health_url: string;
  ok: boolean;
  status_code?: number | null;
  detail: string;
  checked_at: string;
};

export type SystemStatus = {
  services: SystemServiceStatus[];
};

export type TemplateVisibility = "private" | "shared";
export type TemplateStatus = "draft" | "published";

export type PlatformTemplate = {
  template_id: string;
  title: string;
  description: string | null;
  nl: string;
  tags: string[];
  visibility: TemplateVisibility;
  status: TemplateStatus;
  owner_user_id: number;
  owner_username?: string | null;
  owner_full_name?: string | null;
  owner_profile?: string | null;
  use_count: number;
  fork_count: number;
  created_at: string;
  updated_at: string;
  last_used_at: string | null;
  can_edit: boolean;
  can_delete: boolean;
};

export type PlatformTemplatePayload = {
  title: string;
  description?: string | null;
  nl: string;
  tags?: string[];
  visibility?: TemplateVisibility;
  status?: TemplateStatus;
};

export type PlatformTemplateList = {
  rows: PlatformTemplate[];
  total_count: number;
};

export class ApiError extends Error {
  status: number;
  technicalDetail: unknown;

  constructor(message: string, status: number, technicalDetail: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.technicalDetail = technicalDetail;
  }
}

type RawValidationError = {
  type?: string;
  loc?: unknown[];
  msg?: string;
  input?: unknown;
  ctx?: Record<string, unknown>;
};

function fieldLabel(loc: unknown): string {
  const parts = Array.isArray(loc) ? loc : [];
  const last = String(parts[parts.length - 1] ?? "campo");
  const labels: Record<string, string> = {
    username: "usuario",
    password: "contraseña",
    full_name: "nombre completo",
    email: "correo electrónico",
    profile_id: "perfil",
    name: "nombre",
    title: "título",
    description: "descripción",
    permissions: "permisos",
    allowed_tables: "vistas permitidas",
    table_access_mode: "modo de acceso a vistas",
    column_permissions: "permisos por columna",
    max_page_size: "tamaño de página",
    nl: "consulta",
    conversation_id: "conversación",
    report_id: "reporte",
    template_id: "plantilla",
    tags: "etiquetas",
    visibility: "visibilidad",
    status: "estado",
    value: "valor",
    formats: "formatos",
    page: "página",
    page_size: "tamaño de página",
    query_display_max_rows: "límite de visualización",
    export_max_rows: "límite de exportación",
    query_timeout_seconds: "tiempo máximo de consulta",
  };
  return labels[last] ?? last;
}

function messageFromValidationErrors(errors: RawValidationError[]): string {
  if (!errors.length) {
    return "Revisa los campos ingresados. Hay datos obligatorios o con formato inválido.";
  }

  const first = errors[0];
  const field = fieldLabel(first.loc);
  const type = String(first.type ?? "");
  const minLength = first.ctx?.min_length;
  const maxLength = first.ctx?.max_length;

  if (type === "missing") return `El campo ${field} es obligatorio.`;

  if (type.includes("string_too_short")) {
    if (field === "contraseña") return "La contraseña debe tener al menos 6 caracteres.";
    if (field === "usuario") return "El usuario debe tener al menos 3 caracteres.";
    return typeof minLength === "number"
      ? `El campo ${field} debe tener al menos ${minLength} caracteres.`
      : `El campo ${field} es demasiado corto.`;
  }

  if (type.includes("string_too_long")) {
    return typeof maxLength === "number"
      ? `El campo ${field} supera el tamaño máximo de ${maxLength} caracteres.`
      : `El campo ${field} supera el tamaño máximo permitido.`;
  }

  if (
    type.includes("int") ||
    type.includes("float") ||
    type.includes("number") ||
    type.includes("greater_than") ||
    type.includes("less_than")
  ) {
    return `El campo ${field} debe tener un valor numérico válido dentro del rango permitido.`;
  }

  if (type.includes("bool")) return `El campo ${field} debe tener un valor válido.`;
  return "Revisa los campos ingresados. Hay datos obligatorios o con formato inválido.";
}

function looksTechnical(text: string): boolean {
  const compact = text.trim();
  if (!compact) return true;
  if (compact.startsWith("[") || compact.startsWith("{") || compact.includes('"loc"') || compact.includes('"type"')) return true;
  if (/Traceback|SQLAlchemy|psycopg|SELECT\s|INSERT\s|UPDATE\s|DELETE\s|DROP\s|ALTER\s|stack|Exception/i.test(compact)) return true;
  return compact.length > 350;
}

function friendlyFromStatus(status: number): string {
  if (status === 400) return "No se pudo procesar la solicitud. Revisa los datos ingresados.";
  if (status === 401) return "Tu sesión expiró o no es válida. Inicia sesión nuevamente.";
  if (status === 403) return "No tienes permisos para realizar esta operación.";
  if (status === 404) return "No se encontró el recurso solicitado.";
  if (status === 409) return "No se pudo completar la operación porque el registro ya existe o está en uso.";
  if (status === 422) return "Revisa los campos ingresados. Hay datos obligatorios o con formato inválido.";
  if (status === 502) return "No se pudo conectar con uno de los servicios internos. Verifica que el sistema esté iniciado.";
  if (status === 503) return "El servicio no está disponible temporalmente. Revisa la configuración o intenta nuevamente.";
  if (status === 504) return "La operación tardó demasiado y fue cancelada. Intenta con una consulta más específica.";
  if (status >= 500) return "No se pudo completar la operación por un error interno. Inténtalo nuevamente o contacta al administrador.";
  return `No se pudo completar la operación. Código HTTP ${status}.`;
}

function extractDetail(parsed: unknown): unknown {
  if (parsed && typeof parsed === "object") {
    const obj = parsed as Record<string, unknown>;
    return obj.detail ?? obj.error ?? parsed;
  }
  return parsed;
}

function friendlyMessageFromPayload(status: number, parsed: unknown, raw: string): string {
  const detail = extractDetail(parsed);

  if (Array.isArray(detail)) {
    return messageFromValidationErrors(detail as RawValidationError[]);
  }

  if (detail && typeof detail === "object") {
    const obj = detail as Record<string, unknown>;
    const nestedDetail = obj.detail;
    const nestedError = obj.error;

    if (Array.isArray(nestedDetail)) {
      return messageFromValidationErrors(nestedDetail as RawValidationError[]);
    }

    if (typeof nestedError === "string" && !looksTechnical(nestedError)) return nestedError;
    if (typeof nestedDetail === "string" && !looksTechnical(nestedDetail)) return nestedDetail;
    return friendlyFromStatus(status);
  }

  if (typeof detail === "string") {
    const text = detail.trim();
    try {
      const nested = JSON.parse(text);
      return friendlyMessageFromPayload(status, nested, text);
    } catch {
      if (!looksTechnical(text)) return text;
    }
  }

  if (raw && !looksTechnical(raw)) return raw;
  return friendlyFromStatus(status);
}

function parseRawError(raw: string): unknown {
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return raw;
  }
}

async function errorFromResponse(res: Response, url: string): Promise<ApiError> {
  const raw = await res.text();
  const parsed = parseRawError(raw);
  const message = raw ? friendlyMessageFromPayload(res.status, parsed, raw) : friendlyFromStatus(res.status);

  console.error("[API error]", {
    url,
    status: res.status,
    statusText: res.statusText,
    detail: parsed,
  });

  return new ApiError(message, res.status, parsed);
}

export function toUserErrorMessage(error: unknown, fallback = "No se pudo completar la operación."): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return looksTechnical(error.message) ? fallback : error.message;
  return fallback;
}

function sanitizeErrorText(text: string | null | undefined, fallback = "No se pudo completar la operación."): string | null {
  if (!text) return null;
  try {
    const parsed = JSON.parse(text);
    return friendlyMessageFromPayload(500, parsed, text);
  } catch {
    return looksTechnical(text) ? fallback : text;
  }
}

function sanitizeQueryJob(job: QueryJob): QueryJob {
  return {
    ...job,
    error: sanitizeErrorText(job.error, "No se pudo generar el reporte. Reformula la pregunta o intenta nuevamente."),
  };
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

  let res: Response;
  try {
    res = await fetch(url, { ...init, headers });
  } catch (error) {
    console.error("[API network error]", { url, error });
    throw new ApiError("No se pudo conectar con el servidor. Verifica que los servicios estén ejecutándose.", 0, error);
  }

  if (!res.ok) {
    if (res.status === 401) clearToken();
    throw await errorFromResponse(res, url);
  }

  if (res.status === 204) return undefined as T;
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
  email?: string | null;
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
    email: string | null;
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

export async function updateProfile(profileId: number, payload: ProfilePayload): Promise<Profile> {
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
export async function runQuery(nl: string, conversationId: string | null, page: number, pageSize: number): Promise<QueryResponse> {
  return request<QueryResponse>("/api/orchestrator/query", {
    method: "POST",
    body: JSON.stringify({ nl, conversation_id: conversationId, page, page_size: pageSize }),
  });
}

export async function startQueryJob(
  nl: string,
  conversationId: string | null,
  page: number,
  pageSize: number
): Promise<QueryJobStart> {
  return request<QueryJobStart>("/api/orchestrator/query-jobs", {
    method: "POST",
    body: JSON.stringify({ nl, conversation_id: conversationId, page, page_size: pageSize }),
  });
}

export async function getQueryJob(jobId: string): Promise<QueryJob> {
  const job = await request<QueryJob>(`/api/orchestrator/query-jobs/${jobId}`);
  return sanitizeQueryJob(job);
}

export async function listActiveQueryJobs(): Promise<QueryJob[]> {
  const jobs = await request<QueryJob[]>("/api/orchestrator/query-jobs");
  return jobs.map(sanitizeQueryJob);
}

// Reports
export async function getReportMeta(reportId: string): Promise<ReportMeta> {
  return request<ReportMeta>(`/api/orchestrator/reports/${reportId}/meta`);
}

export async function getReportData(reportId: string, page: number, pageSize: number): Promise<ReportData> {
  const token = getToken();
  const url = `/api/orchestrator/reports/${reportId}/data?page=${page}&page_size=${pageSize}`;

  let res: Response;
  try {
    res = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : undefined });
  } catch (error) {
    console.error("[API network error]", { url, error });
    throw new ApiError("No se pudo conectar con el servidor. Verifica que los servicios estén ejecutándose.", 0, error);
  }

  if (!res.ok) {
    if (res.status === 401) clearToken();
    throw await errorFromResponse(res, url);
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
  const url = `/api/orchestrator/reports/${reportId}/export?format=${format}`;

  let res: Response;
  try {
    res = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : undefined });
  } catch (error) {
    console.error("[API network error]", { url, error });
    throw new ApiError("No se pudo conectar con el servidor. Verifica que los servicios estén ejecutándose.", 0, error);
  }

  if (!res.ok) {
    if (res.status === 401) clearToken();
    throw await errorFromResponse(res, url);
  }

  const blob = await res.blob();
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = filenameFromDisposition(res.headers.get("Content-Disposition"), `reporte-${reportId}.${format}`);
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(objectUrl);
}

export type ReportEmailResponse = {
  ok: boolean;
  to: string;
  formats: ("csv" | "xlsx" | "pdf")[];
  attachments: string[];
};

export async function sendReportEmail(reportId: string, formats: ("csv" | "xlsx" | "pdf")[]): Promise<ReportEmailResponse> {
  return request<ReportEmailResponse>(`/api/orchestrator/reports/${reportId}/email`, {
    method: "POST",
    body: JSON.stringify({ formats }),
  });
}

// Platform templates
export async function listPlatformTemplates(params: { q?: string; tag?: string; mine?: boolean } = {}): Promise<PlatformTemplateList> {
  const sp = new URLSearchParams();
  if (params.q?.trim()) sp.set("q", params.q.trim());
  if (params.tag?.trim()) sp.set("tag", params.tag.trim());
  if (params.mine) sp.set("mine", "true");
  const query = sp.toString();
  return request<PlatformTemplateList>(`/api/platform/templates${query ? `?${query}` : ""}`);
}

export async function createPlatformTemplate(payload: PlatformTemplatePayload): Promise<PlatformTemplate> {
  return request<PlatformTemplate>("/api/platform/templates", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updatePlatformTemplate(templateId: string, payload: Partial<PlatformTemplatePayload>): Promise<PlatformTemplate> {
  return request<PlatformTemplate>(`/api/platform/templates/${templateId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function deletePlatformTemplate(templateId: string): Promise<void> {
  await request(`/api/platform/templates/${templateId}`, {
    method: "DELETE",
  });
}

export async function recordPlatformTemplateUse(templateId: string): Promise<void> {
  await request(`/api/platform/templates/${templateId}/use`, {
    method: "POST",
  });
}

export async function forkPlatformTemplate(templateId: string): Promise<PlatformTemplate> {
  return request<PlatformTemplate>(`/api/platform/templates/${templateId}/fork`, {
    method: "POST",
  });
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

export async function updateSystemConfig(payload: SystemConfigUpdatePayload): Promise<SystemConfig> {
  return request<SystemConfig>("/api/orchestrator/system/config", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function getSystemSchema(): Promise<SystemSchema> {
  return request<SystemSchema>("/api/orchestrator/system/schema");
}

export async function getSystemStatus(): Promise<SystemStatus> {
  return request<SystemStatus>("/api/orchestrator/system/status");
}
