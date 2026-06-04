import { clearToken, getToken } from "./auth";

type NumericLimit = {
  min?: number;
  max?: number;
  min_when_enabled?: number;
  unlimited_value?: number;
  warning_below?: number;
  max_length?: number;
};

export type ConfigOption = {
  value: string;
  label: string;
};

export type PublicSystemConfig = {
  ui_language: "es" | "en";
  default_theme: "system" | "light" | "dark";
  institutional_notice: string;
};

export type SystemConfig = PublicSystemConfig & {
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
    query_display_max_rows?: NumericLimit;
    export_max_rows?: NumericLimit;
    query_timeout_seconds?: NumericLimit;
    institutional_notice?: NumericLimit;
  };
  warnings?: string[];
  options?: {
    ui_languages?: ConfigOption[];
    default_themes?: ConfigOption[];
  };
};

export type SystemConfigUpdatePayload = Partial<{
  query_display_max_rows: number;
  export_max_rows: number;
  query_timeout_seconds: number;
  ui_language: "es" | "en";
  default_theme: "system" | "light" | "dark";
  institutional_notice: string;
}>;

async function errorFromResponse(res: Response): Promise<Error> {
  let message = `No se pudo completar la operación. Código HTTP ${res.status}.`;
  try {
    const parsed = await res.json();
    const detail = parsed?.detail ?? parsed?.error;
    if (typeof detail === "string") message = detail;
    else if (detail?.error && typeof detail.error === "string") message = detail.error;
  } catch {
    const text = await res.text().catch(() => "");
    if (text && text.length < 250) message = text;
  }
  return new Error(message);
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const headers: HeadersInit = {
    ...(init?.body ? { "Content-Type": "application/json" } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(init?.headers ?? {}),
  };

  let res: Response;
  try {
    res = await fetch(url, { ...init, headers });
  } catch (error) {
    console.error("[system-config network error]", error);
    throw new Error("No se pudo conectar con el servidor. Verifica que los servicios estén ejecutándose.");
  }

  if (!res.ok) {
    if (res.status === 401) clearToken();
    throw await errorFromResponse(res);
  }

  return (await res.json()) as T;
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

export async function getPublicSystemConfig(): Promise<PublicSystemConfig> {
  return request<PublicSystemConfig>("/api/orchestrator/system/public-config");
}
