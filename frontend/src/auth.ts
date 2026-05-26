const TOKEN_KEY = "empresa_reports_token_v3";
const LEGACY_TOKEN_KEYS = ["empresa_reports_token", "empresa_reports_token_v2"];

export type AuthUser = {
  user_id: number;
  username: string;
  full_name?: string | null;
  profile?: string | null;
  profile_id?: number | null;
  permissions: Record<string, boolean>;
  allowed_tables: string[];
  max_display_rows: number;
  max_page_size: number;
};

type JwtPayload = {
  sub?: string;
  username?: string;
  full_name?: string | null;
  profile?: string | null;
  profile_id?: number | null;
  permissions?: Record<string, boolean>;
  allowed_tables?: string[];
  max_display_rows?: number;
  max_page_size?: number;
  acl_version?: number;
  exp?: number;
};

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
  LEGACY_TOKEN_KEYS.forEach((key) => localStorage.removeItem(key));
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
  LEGACY_TOKEN_KEYS.forEach((key) => localStorage.removeItem(key));
}

function base64UrlDecode(input: string): string {
  const normalized = input.replace(/-/g, "+").replace(/_/g, "/");
  const padded = normalized.padEnd(normalized.length + ((4 - (normalized.length % 4)) % 4), "=");

  return decodeURIComponent(
    atob(padded)
      .split("")
      .map((c) => `%${c.charCodeAt(0).toString(16).padStart(2, "0")}`)
      .join("")
  );
}

function decodePayload(token: string): JwtPayload | null {
  try {
    const [, payload] = token.split(".");
    if (!payload) return null;
    return JSON.parse(base64UrlDecode(payload)) as JwtPayload;
  } catch {
    return null;
  }
}

function isExpired(payload: JwtPayload): boolean {
  if (!payload.exp) return true;
  return payload.exp * 1000 <= Date.now();
}

export function getAuthUser(): AuthUser | null {
  const token = getToken();
  if (!token) return null;

  const payload = decodePayload(token);

  // Fuerza login si queda un JWT viejo del sistema anterior o un token corrupto.
  // Desde v3 el perfil es la única fuente de autorización.
  if (
    !payload ||
    !payload.sub ||
    !payload.username ||
    !payload.permissions ||
    Number(payload.acl_version ?? 0) < 3 ||
    isExpired(payload)
  ) {
    clearToken();
    return null;
  }

  return {
    user_id: Number(payload.sub),
    username: payload.username,
    full_name: payload.full_name ?? null,
    profile: payload.profile ?? null,
    profile_id: payload.profile_id ?? null,
    permissions: payload.permissions ?? {},
    allowed_tables: payload.allowed_tables ?? [],
    max_display_rows: Number(payload.max_display_rows ?? 5000),
    max_page_size: Number(payload.max_page_size ?? 50),
  };
}

export function isAuthed(): boolean {
  return getAuthUser() !== null;
}

export function hasPermission(permission: string): boolean {
  const user = getAuthUser();
  if (!user) return false;
  return !!user.permissions?.[permission];
}
