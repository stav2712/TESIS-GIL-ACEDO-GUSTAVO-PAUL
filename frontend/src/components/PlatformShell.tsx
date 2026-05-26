import type { ReactNode } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { clearToken, getAuthUser, hasPermission } from "../auth";
import { getTheme, toggleTheme } from "../theme";

type ShellProps = {
  children: ReactNode;
  fullBleed?: boolean;
};

type MenuItem = {
  to: string;
  label: string;
  icon: string;
  end?: boolean;
  permission?: string;
};

const MENU_ITEMS: MenuItem[] = [
  { to: "/", label: "Panel", icon: "dashboard", end: true },
  { to: "/consultas", label: "Consultas", icon: "query_stats", permission: "can_query" },
  { to: "/usuarios", label: "Usuarios", icon: "group_add", permission: "can_manage_users" },
  { to: "/perfiles", label: "Perfiles", icon: "admin_panel_settings", permission: "can_manage_profiles" },
  { to: "/auditoria", label: "Auditoría", icon: "manage_search", permission: "can_view_audit" },
  { to: "/configuracion", label: "Configuración", icon: "settings", permission: "can_view_system_config" },
];

function canSee(item: MenuItem): boolean {
  return !item.permission || hasPermission(item.permission);
}

export default function PlatformShell({ children, fullBleed = false }: ShellProps) {
  const user = getAuthUser();
  const navigate = useNavigate();
  const theme = getTheme();

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
              <h1 className="text-xl font-bold tracking-tight">empresa</h1>
              <p className="text-sm font-semibold tracking-[0.25em] -mt-1">REPORTS</p>
            </div>
          </Link>

          <nav className="flex flex-wrap gap-2 items-center justify-center">
            {MENU_ITEMS.filter(canSee).map((item) => (
              <NavLink key={item.to} to={item.to} end={item.end} className={linkClass}>
                <span className="material-icons text-[18px]">{item.icon}</span>
                <span>{item.label}</span>
              </NavLink>
            ))}
          </nav>

          <div className="flex items-center gap-2">
            <button
              onClick={() => toggleTheme()}
              className="w-10 h-10 rounded-full bg-white/10 hover:bg-white/20 text-white flex items-center justify-center transition"
              title={`Tema: ${theme}`}
              type="button"
            >
              <span className="material-icons">brightness_6</span>
            </button>

            <div className="hidden md:flex items-center gap-3 bg-white/10 rounded-full pl-3 pr-1 py-1 text-white">
              <div className="text-right leading-tight">
                <p className="text-sm font-bold">{user?.full_name || user?.username}</p>
                <p className="text-[11px] text-cyan-50">
                  {user?.profile ? `Perfil: ${user.profile}` : "Sin perfil asignado"}
                </p>
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
              <span className="hidden sm:inline">Salir</span>
            </button>
          </div>
        </div>
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
