import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { clearToken, getAuthUser, hasPermission } from "../auth";
import { getPublicSystemConfig, type PublicSystemConfig } from "../systemConfigClient";
import { applyDefaultTheme, getTheme, toggleTheme } from "../theme";

type ShellProps = {
  children: ReactNode;
  fullBleed?: boolean;
};

type Lang = "es" | "en";

type MenuItem = {
  to: string;
  label: Record<Lang, string>;
  icon: string;
  end?: boolean;
  permission?: string;
};

const MENU_ITEMS: MenuItem[] = [
  { to: "/", label: { es: "Panel", en: "Dashboard" }, icon: "dashboard", end: true },
  { to: "/consultas", label: { es: "Consultas", en: "Queries" }, icon: "query_stats", permission: "can_query" },
  { to: "/historial-reportes", label: { es: "Historial", en: "History" }, icon: "history", permission: "can_query" },
  { to: "/historias-clinicas", label: { es: "Historias Clínicas", en: "Clinical Records" }, icon: "assignment_ind", permission: "can_view_clinical_history" },
  { to: "/plantillas", label: { es: "Plantillas", en: "Templates" }, icon: "article", permission: "can_use_templates" },
  { to: "/usuarios", label: { es: "Usuarios", en: "Users" }, icon: "group_add", permission: "can_manage_users" },
  { to: "/perfiles", label: { es: "Perfiles", en: "Profiles" }, icon: "admin_panel_settings", permission: "can_manage_profiles" },
  { to: "/auditoria", label: { es: "Auditoría", en: "Audit" }, icon: "manage_search", permission: "can_view_audit" },
  { to: "/configuracion", label: { es: "Configuración", en: "Settings" }, icon: "settings", permission: "can_view_system_config" },
];

const TEXT: Record<Lang, { profile: string; noProfile: string; logout: string; theme: string; systemSubtitle: string }> = {
  es: {
    profile: "Perfil",
    noProfile: "Sin perfil asignado",
    logout: "Salir",
    theme: "Tema",
    systemSubtitle: "VELTRA",
  },
  en: {
    profile: "Profile",
    noProfile: "No profile assigned",
    logout: "Log out",
    theme: "Theme",
    systemSubtitle: "VELTRA",
  },
};

function canSee(item: MenuItem): boolean {
  return !item.permission || hasPermission(item.permission);
}

function normalizePublicConfig(config: PublicSystemConfig | null): PublicSystemConfig {
  return {
    ui_language: config?.ui_language === "en" ? "en" : "es",
    default_theme: config?.default_theme === "dark" || config?.default_theme === "light" ? config.default_theme : "system",
    institutional_notice: (config?.institutional_notice ?? "").trim(),
  };
}

export default function PlatformShell({ children, fullBleed = false }: ShellProps) {
  const user = getAuthUser();
  const navigate = useNavigate();
  const [publicConfig, setPublicConfig] = useState<PublicSystemConfig>(() => normalizePublicConfig(null));
  const [theme, setThemeLabel] = useState(() => getTheme());

  const lang = publicConfig.ui_language;
  const text = TEXT[lang];
  const announcement = publicConfig.institutional_notice;

  async function loadPublicConfig() {
    try {
      const next = normalizePublicConfig(await getPublicSystemConfig());
      setPublicConfig(next);
      applyDefaultTheme(next.default_theme);
      setThemeLabel(getTheme(next.default_theme));
    } catch (error) {
      console.error("[system public config]", error);
    }
  }

  useEffect(() => {
    loadPublicConfig();
    const handler = () => loadPublicConfig();
    window.addEventListener("system-config-updated", handler);
    return () => window.removeEventListener("system-config-updated", handler);
  }, []);

  const logout = () => {
    clearToken();
    navigate("/login", { replace: true });
  };

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    [
      "inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-bold transition-colors duration-200",
      isActive
        ? "bg-[#C6EB32] text-[#005f80] shadow-sm"
        : "text-white/90 hover:text-white hover:bg-white/10 dark:text-slate-200 dark:hover:bg-slate-800",
    ].join(" ");

  return (
    <div className="h-screen overflow-hidden bg-[#0083B0] dark:bg-slate-950 font-['Montserrat'] text-slate-900 dark:text-slate-100 flex flex-col">
      <header className="shrink-0 z-50 bg-[#007aa3] dark:bg-slate-900 border-b border-white/10 dark:border-slate-800 shadow-md">
        <div className="px-4 py-3 flex flex-wrap gap-3 items-center justify-between">
          <Link to="/" className="flex items-center gap-3 text-white min-w-fit">
            <div className="w-10 h-10 rounded-full bg-[#C6EB32] text-[#006a90] flex items-center justify-center shadow-sm">
              <span className="material-icons">analytics</span>
            </div>
            <div className="leading-tight">
              <h1 className="text-xl font-bold tracking-tight">Clínica</h1>
              <p className="text-sm font-semibold tracking-[0.25em] -mt-1">{text.systemSubtitle}</p>
            </div>
          </Link>

          <nav className="flex flex-wrap gap-2 items-center justify-center">
            {MENU_ITEMS.filter(canSee).map((item) => (
              <NavLink key={item.to} to={item.to} end={item.end} className={linkClass}>
                <span className="material-icons text-[18px]">{item.icon}</span>
                <span>{item.label[lang]}</span>
              </NavLink>
            ))}
          </nav>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setThemeLabel(toggleTheme())}
              className="w-10 h-10 rounded-full bg-white/10 hover:bg-white/20 text-white flex items-center justify-center transition"
              title={`${text.theme}: ${theme}`}
              type="button"
            >
              <span className="material-icons">brightness_6</span>
            </button>

            <div className="hidden md:flex items-center gap-3 bg-white/10 rounded-full pl-3 pr-1 py-1 text-white">
              <div className="text-right leading-tight">
                <p className="text-sm font-bold">{user?.full_name || user?.username}</p>
                <p className="text-[11px] text-cyan-50">{user?.profile ? `${text.profile}: ${user.profile}` : text.noProfile}</p>
              </div>
              <div className="w-9 h-9 rounded-full bg-white/20 flex items-center justify-center">
                <span className="material-icons text-[20px]">person</span>
              </div>
            </div>

            <button
              onClick={logout}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-[#006a90] hover:bg-[#005c7d] dark:bg-slate-800 dark:hover:bg-slate-700 text-white text-sm font-bold transition"
              type="button"
            >
              <span className="material-icons text-[18px]">logout</span>
              <span className="hidden sm:inline">{text.logout}</span>
            </button>
          </div>
        </div>

        {announcement && (
          <div className="px-4 pb-3">
            <div className="rounded-xl bg-[#C6EB32]/20 border border-[#C6EB32]/40 text-white px-4 py-2 text-sm font-semibold flex items-center gap-2">
              <span className="material-icons text-[18px]">campaign</span>
              <span>{announcement}</span>
            </div>
          </div>
        )}
      </header>

      {fullBleed ? (
        <main className="flex-1 min-h-0 overflow-hidden bg-gray-100 dark:bg-slate-950">{children}</main>
      ) : (
        <main className="flex-1 min-h-0 overflow-y-auto bg-[#0083B0] dark:bg-slate-950">
          <div className="max-w-7xl mx-auto px-4 py-6 lg:py-8">{children}</div>
        </main>
      )}
    </div>
  );
}
