import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
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
  description: Record<Lang, string>;
  icon: string;
  group: "operation" | "workspace" | "admin";
  end?: boolean;
  permission?: string;
};

const MENU_ITEMS: MenuItem[] = [
  {
    to: "/",
    label: { es: "Inicio", en: "Home" },
    description: { es: "Resumen de la plataforma", en: "Platform overview" },
    icon: "space_dashboard",
    group: "operation",
    end: true,
  },
  {
    to: "/consultas",
    label: { es: "Consultas NL-to-SQL", en: "NL-to-SQL queries" },
    description: { es: "Genera reportes clínicos", en: "Generate clinical reports" },
    icon: "auto_awesome",
    group: "operation",
    permission: "can_query",
  },
  {
    to: "/historial-reportes",
    label: { es: "Historial", en: "History" },
    description: { es: "Reportes y conversaciones", en: "Reports and conversations" },
    icon: "history",
    group: "operation",
    permission: "can_query",
  },
  {
    to: "/historias-clinicas",
    label: { es: "Historias clínicas", en: "Clinical records" },
    description: { es: "Vista integral del paciente", en: "Patient-centered view" },
    icon: "assignment_ind",
    group: "workspace",
    permission: "can_view_clinical_history",
  },
  {
    to: "/plantillas",
    label: { es: "Plantillas", en: "Templates" },
    description: { es: "Consultas reutilizables", en: "Reusable prompts" },
    icon: "article",
    group: "workspace",
    permission: "can_use_templates",
  },
  {
    to: "/usuarios",
    label: { es: "Usuarios", en: "Users" },
    description: { es: "Altas, estados y perfiles", en: "Accounts and profiles" },
    icon: "group_add",
    group: "admin",
    permission: "can_manage_users",
  },
  {
    to: "/perfiles",
    label: { es: "Perfiles", en: "Profiles" },
    description: { es: "Permisos y vistas", en: "Permissions and views" },
    icon: "admin_panel_settings",
    group: "admin",
    permission: "can_manage_profiles",
  },
  {
    to: "/auditoria",
    label: { es: "Auditoría", en: "Audit" },
    description: { es: "Trazabilidad operativa", en: "Operational traceability" },
    icon: "manage_search",
    group: "admin",
    permission: "can_view_audit",
  },
  {
    to: "/configuracion",
    label: { es: "Configuración", en: "Settings" },
    description: { es: "Servicios y límites", en: "Services and limits" },
    icon: "settings",
    group: "admin",
    permission: "can_view_system_config",
  },
];

const TEXT: Record<
  Lang,
  {
    brandTitle: string;
    brandSubtitle: string;
    operation: string;
    workspace: string;
    admin: string;
    profile: string;
    noProfile: string;
    logout: string;
    theme: string;
    menu: string;
    close: string;
    collapse: string;
    expand: string;
    quickAction: string;
    askReport: string;
    platformMode: string;
  }
> = {
  es: {
    brandTitle: "CALIDAD Y SALUD T&F",
    brandSubtitle: "Plataforma NL-to-SQL",
    operation: "Operación",
    workspace: "Trabajo clínico",
    admin: "Administración",
    profile: "Perfil",
    noProfile: "Sin perfil asignado",
    logout: "Salir",
    theme: "Tema",
    menu: "Abrir menú",
    close: "Cerrar menú",
    collapse: "Ocultar barra lateral",
    expand: "Mostrar barra lateral",
    quickAction: "Acción rápida",
    askReport: "Crear reporte",
    platformMode: "Entorno seguro de reportes clínicos",
  },
  en: {
    brandTitle: "Veltra Clinic",
    brandSubtitle: "NL-to-SQL Platform",
    operation: "Operation",
    workspace: "Clinical workspace",
    admin: "Administration",
    profile: "Profile",
    noProfile: "No profile assigned",
    logout: "Log out",
    theme: "Theme",
    menu: "Open menu",
    close: "Close menu",
    collapse: "Collapse sidebar",
    expand: "Expand sidebar",
    quickAction: "Quick action",
    askReport: "Create report",
    platformMode: "Secure clinical reporting environment",
  },
};

const GROUPS: MenuItem["group"][] = ["operation", "workspace", "admin"];

function canSee(item: MenuItem): boolean {
  return !item.permission || hasPermission(item.permission);
}

function normalizePublicConfig(config: PublicSystemConfig | null): PublicSystemConfig {
  return {
    ui_language: config?.ui_language === "en" ? "en" : "es",
    default_theme:
      config?.default_theme === "dark" || config?.default_theme === "light" ? config.default_theme : "system",
    institutional_notice: (config?.institutional_notice ?? "").trim(),
  };
}

function initials(name: string | null | undefined, username: string | null | undefined): string {
  const source = (name || username || "U").trim();
  const parts = source.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  return source.slice(0, 2).toUpperCase();
}

function groupTitle(group: MenuItem["group"], lang: Lang): string {
  const text = TEXT[lang];
  if (group === "operation") return text.operation;
  if (group === "workspace") return text.workspace;
  return text.admin;
}

export default function PlatformShell({ children, fullBleed = false }: ShellProps) {
  const user = getAuthUser();
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [publicConfig, setPublicConfig] = useState<PublicSystemConfig>(() => normalizePublicConfig(null));
  const [theme, setThemeLabel] = useState(() => getTheme());
  const [desktopCollapsed, setDesktopCollapsed] = useState(() => {
    if (typeof window === "undefined") return false;
    return window.localStorage.getItem("veltra-sidebar-collapsed") === "true";
  });

  const lang = publicConfig.ui_language;
  const text = TEXT[lang];
  const announcement = publicConfig.institutional_notice;

  const visibleMenu = useMemo(() => MENU_ITEMS.filter(canSee), []);
  const activeItem =
    visibleMenu.find((item) =>
      item.end ? location.pathname === item.to : location.pathname === item.to || location.pathname.startsWith(`${item.to}/`)
    ) ?? visibleMenu[0];

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

  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem("veltra-sidebar-collapsed", String(desktopCollapsed));
  }, [desktopCollapsed]);

  const logout = () => {
    clearToken();
    navigate("/login", { replace: true });
  };

  const navClass = ({ isActive }: { isActive: boolean }) =>
    [
      "group flex items-center gap-3 rounded-2xl px-3 py-3 text-sm font-bold transition",
      desktopCollapsed ? "lg:justify-center lg:gap-0 lg:px-0 lg:py-3.5" : "",
      isActive
        ? "bg-white text-[#006a90] shadow-lg shadow-cyan-950/20 dark:bg-slate-800 dark:text-lime-200"
        : "text-white/82 hover:bg-white/10 hover:text-white dark:text-slate-300 dark:hover:bg-slate-800/70",
    ].join(" ");

  return (
    <div className="h-screen overflow-hidden bg-slate-100 text-slate-900 dark:bg-slate-950 dark:text-slate-100 font-['Montserrat']">
      <div className="flex h-full min-h-0 overflow-hidden">
        <aside
          className={[
            "fixed inset-y-0 left-0 z-50 flex w-72 max-w-[86vw] flex-col border-r border-white/10 bg-[#006f96] px-4 py-4 text-white shadow-2xl shadow-slate-950/30 transition-[transform,width,padding] duration-300 dark:bg-slate-950 dark:border-slate-800 lg:static lg:max-w-none lg:translate-x-0",
            desktopCollapsed ? "lg:w-20 lg:px-3" : "lg:w-72 lg:px-4",
            mobileOpen ? "translate-x-0" : "-translate-x-full",
          ].join(" ")}
        >
          <div
            className={[
              "flex items-center justify-between gap-3 rounded-3xl bg-white/10 p-3 ring-1 ring-white/10",
              desktopCollapsed ? "lg:flex-col lg:items-center lg:justify-center lg:gap-2 lg:rounded-[1.75rem] lg:p-2" : "",
            ].join(" ")}
          >
            <Link
              to="/"
              className={[
                "flex min-w-0 items-center gap-3",
                desktopCollapsed ? "lg:w-full lg:justify-center lg:gap-0" : "",
              ].join(" ")}
              title={text.brandTitle}
            >
              <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-[#C6EB32] text-[#006a90] shadow-lg shadow-cyan-950/20">
                <span className="material-icons text-3xl">analytics</span>
              </div>
              <div className={["min-w-0 leading-tight", desktopCollapsed ? "lg:hidden" : ""].join(" ")}>
                <p className="truncate text-lg font-black tracking-tight">{text.brandTitle}</p>
                <p className="truncate text-xs font-bold uppercase tracking-[0.22em] text-lime-100">{text.brandSubtitle}</p>
              </div>
            </Link>
            <button
              type="button"
              className={[
                "hidden h-9 w-9 place-items-center rounded-full bg-white/10 text-white transition hover:bg-white/20 lg:grid",
                desktopCollapsed ? "lg:h-10 lg:w-10 lg:bg-white/15" : "",
              ].join(" ")}
              onClick={() => setDesktopCollapsed((value) => !value)}
              aria-label={desktopCollapsed ? text.expand : text.collapse}
              title={desktopCollapsed ? text.expand : text.collapse}
            >
              <span className="material-icons text-[20px]">
                {desktopCollapsed ? "keyboard_double_arrow_right" : "keyboard_double_arrow_left"}
              </span>
            </button>
            <button
              type="button"
              className="grid h-9 w-9 place-items-center rounded-full bg-white/10 text-white hover:bg-white/20 lg:hidden"
              onClick={() => setMobileOpen(false)}
              aria-label={text.close}
            >
              <span className="material-icons text-[20px]">close</span>
            </button>
          </div>

          {hasPermission("can_query") && (
            <div
              className={[
                "mt-4 rounded-3xl bg-[#C6EB32] p-4 text-[#005f80] shadow-xl shadow-cyan-950/20",
                desktopCollapsed ? "lg:hidden" : "",
              ].join(" ")}
            >
              <p className="text-xs font-black uppercase tracking-[0.22em] opacity-75">{text.quickAction}</p>
              <p className="mt-2 text-lg font-black leading-tight">{text.askReport}</p>
              <Link
                to="/consultas"
                className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-[#006f96] px-4 py-3 text-sm font-black text-white transition hover:bg-[#005a78]"
              >
                <span className="material-icons text-[20px]">arrow_forward</span>
                NL-to-SQL
              </Link>
            </div>
          )}

          <nav className="mt-4 min-h-0 flex-1 overflow-y-auto pr-1 scrollbar-subtle">
            {GROUPS.map((group) => {
              const items = visibleMenu.filter((item) => item.group === group);
              if (items.length === 0) return null;
              return (
                <div key={group} className={desktopCollapsed ? "mb-3" : "mb-5"}>
                  <p
                    className={[
                      "mb-2 px-3 text-[11px] font-black uppercase tracking-[0.25em] text-white/55",
                      desktopCollapsed ? "lg:hidden" : "",
                    ].join(" ")}
                  >
                    {groupTitle(group, lang)}
                  </p>
                  <div className="space-y-1.5">
                    {items.map((item) => (
                      <NavLink
                        key={item.to}
                        to={item.to}
                        end={item.end}
                        className={navClass}
                        title={`${item.label[lang]} — ${item.description[lang]}`}
                      >
                        <span className="material-icons text-[22px] opacity-95">{item.icon}</span>
                        <span className={["min-w-0", desktopCollapsed ? "lg:hidden" : ""].join(" ")}>
                          <span className="block truncate">{item.label[lang]}</span>
                          <span className="block truncate text-[11px] font-semibold opacity-65">{item.description[lang]}</span>
                        </span>
                      </NavLink>
                    ))}
                  </div>
                </div>
              );
            })}
          </nav>

          <div
            className={[
              "mt-3 rounded-3xl bg-white/10 p-3 ring-1 ring-white/10",
              desktopCollapsed ? "lg:rounded-2xl lg:p-2" : "",
            ].join(" ")}
          >
            <div className={["flex items-center gap-3", desktopCollapsed ? "lg:justify-center" : ""].join(" ")}>
              <div className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-white text-sm font-black text-[#006a90]">
                {initials(user?.full_name, user?.username)}
              </div>
              <div className={["min-w-0 flex-1", desktopCollapsed ? "lg:hidden" : ""].join(" ")}>
                <p className="truncate text-sm font-black">{user?.full_name || user?.username}</p>
                <p className="truncate text-xs font-semibold text-white/70">
                  {text.profile}: {user?.profile || text.noProfile}
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={logout}
              className={[
                "mt-3 inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-white/10 px-3 py-2.5 text-sm font-black text-white transition hover:bg-white/20",
                desktopCollapsed ? "lg:h-10 lg:px-0 lg:py-0" : "",
              ].join(" ")}
              title={text.logout}
            >
              <span className="material-icons text-[18px]">logout</span>
              <span className={desktopCollapsed ? "lg:hidden" : ""}>{text.logout}</span>
            </button>
          </div>
        </aside>

        {mobileOpen && (
          <button
            type="button"
            aria-label={text.close}
            className="fixed inset-0 z-40 bg-slate-950/60 backdrop-blur-sm lg:hidden"
            onClick={() => setMobileOpen(false)}
          />
        )}

        <div className="flex min-w-0 flex-1 flex-col bg-slate-100 dark:bg-slate-950">
          <header className="shrink-0 border-b border-slate-200/80 bg-white/85 px-4 py-3 shadow-sm backdrop-blur-xl dark:border-slate-800 dark:bg-slate-900/85 lg:px-6">
            <div className="flex items-center justify-between gap-3">
              <div className="flex min-w-0 items-center gap-3">
                <button
                  type="button"
                  className="grid h-10 w-10 place-items-center rounded-2xl border border-slate-200 bg-white text-slate-700 shadow-sm hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 lg:hidden"
                  onClick={() => setMobileOpen(true)}
                  aria-label={text.menu}
                >
                  <span className="material-icons">menu</span>
                </button>
{/*                 <button
                  type="button"
                  className="hidden h-10 w-10 place-items-center rounded-2xl border border-slate-200 bg-white text-slate-700 shadow-sm hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 lg:grid"
                  onClick={() => setDesktopCollapsed((value) => !value)}
                  aria-label={desktopCollapsed ? text.expand : text.collapse}
                  title={desktopCollapsed ? text.expand : text.collapse}
                >
                  <span className="material-icons">
                    {desktopCollapsed ? "keyboard_double_arrow_right" : "keyboard_double_arrow_left"}
                  </span>
                </button> */}
                <div className="min-w-0">
                  <p className="truncate text-sm font-black text-slate-500 dark:text-slate-400">{text.platformMode}</p>
                  <h1 className="truncate text-xl font-black tracking-tight text-slate-950 dark:text-white">
                    {activeItem?.label[lang] ?? text.brandTitle}
                  </h1>
                </div>
              </div>

              <div className="flex items-center gap-2">
                {announcement && (
                  <div className="hidden max-w-md items-center gap-2 rounded-2xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-bold text-amber-800 dark:border-amber-400/20 dark:bg-amber-400/10 dark:text-amber-100 xl:flex">
                    <span className="material-icons text-[18px]">campaign</span>
                    <span className="truncate">{announcement}</span>
                  </div>
                )}
                <button
                  onClick={() => setThemeLabel(toggleTheme())}
                  className="grid h-10 w-10 place-items-center rounded-2xl border border-slate-200 bg-white text-slate-700 shadow-sm transition hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
                  title={`${text.theme}: ${theme}`}
                  type="button"
                >
                  <span className="material-icons">brightness_6</span>
                </button>
                <div className="hidden items-center gap-2 rounded-2xl border border-slate-200 bg-white px-3 py-2 shadow-sm dark:border-slate-700 dark:bg-slate-800 sm:flex">
                  <div className="grid h-8 w-8 place-items-center rounded-xl bg-[#006f96] text-xs font-black text-white dark:bg-lime-300 dark:text-slate-950">
                    {initials(user?.full_name, user?.username)}
                  </div>
                  <div className="min-w-0 leading-tight">
                    <p className="max-w-36 truncate text-xs font-black text-slate-900 dark:text-white">
                      {user?.full_name || user?.username}
                    </p>
                    <p className="max-w-36 truncate text-[11px] font-semibold text-slate-500 dark:text-slate-400">
                      {user?.profile || text.noProfile}
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {announcement && (
              <div className="mt-3 flex items-start gap-2 rounded-2xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-bold text-amber-800 dark:border-amber-400/20 dark:bg-amber-400/10 dark:text-amber-100 xl:hidden">
                <span className="material-icons text-[18px]">campaign</span>
                <span>{announcement}</span>
              </div>
            )}
          </header>

          {fullBleed ? (
            <main className="flex-1 min-h-0 overflow-hidden bg-slate-100 dark:bg-slate-950">{children}</main>
          ) : (
            <main className="flex-1 min-h-0 overflow-y-auto bg-slate-100 px-4 py-5 dark:bg-slate-950 lg:px-6 lg:py-6">
              <div className="mx-auto max-w-7xl">{children}</div>
            </main>
          )}
        </div>
      </div>
    </div>
  );
}
