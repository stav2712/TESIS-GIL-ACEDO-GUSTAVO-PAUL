export type ThemeMode = "light" | "dark";

const KEY = "empresa_reports_theme";

export function getTheme(): ThemeMode {
  const v = localStorage.getItem(KEY);
  return v === "dark" ? "dark" : "light";
}

export function setTheme(mode: ThemeMode) {
  localStorage.setItem(KEY, mode);
  applyTheme(mode);
}

export function applyTheme(mode: ThemeMode) {
  const root = document.documentElement;
  if (mode === "dark") root.classList.add("dark");
  else root.classList.remove("dark");
}

export function toggleTheme(): ThemeMode {
  const next: ThemeMode = getTheme() === "dark" ? "light" : "dark";
  setTheme(next);
  return next;
}