export type ThemeMode = "light" | "dark";
export type DefaultThemeMode = "system" | ThemeMode;

const KEY = "empresa_reports_theme";

function systemTheme(): ThemeMode {
  if (typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: dark)").matches) {
    return "dark";
  }
  return "light";
}

function normalizeStoredTheme(value: string | null): ThemeMode | null {
  return value === "dark" || value === "light" ? value : null;
}

function resolveDefaultTheme(defaultTheme: DefaultThemeMode): ThemeMode {
  if (defaultTheme === "dark" || defaultTheme === "light") return defaultTheme;
  return systemTheme();
}

export function getStoredTheme(): ThemeMode | null {
  return normalizeStoredTheme(localStorage.getItem(KEY));
}

export function getTheme(defaultTheme: DefaultThemeMode = "light"): ThemeMode {
  return getStoredTheme() ?? resolveDefaultTheme(defaultTheme);
}

export function setTheme(mode: ThemeMode) {
  localStorage.setItem(KEY, mode);
  applyTheme(mode);
}

export function clearStoredTheme() {
  localStorage.removeItem(KEY);
}

export function applyTheme(mode: ThemeMode) {
  const root = document.documentElement;
  if (mode === "dark") root.classList.add("dark");
  else root.classList.remove("dark");
}

export function applyDefaultTheme(defaultTheme: DefaultThemeMode) {
  applyTheme(getTheme(defaultTheme));
}

export function toggleTheme(): ThemeMode {
  const next: ThemeMode = getTheme() === "dark" ? "light" : "dark";
  setTheme(next);
  return next;
}
