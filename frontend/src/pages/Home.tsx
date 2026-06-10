import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getAdminDashboard, type DashboardSummary } from "../api";
import { getAuthUser, hasPermission } from "../auth";

type ModuleCardProps = {
  to: string;
  icon: string;
  eyebrow: string;
  title: string;
  description: string;
  highlight?: string;
};

type StatCardProps = {
  title: string;
  value: string | number;
  description: string;
  icon: string;
};

function formatNumber(value: number | undefined): string {
  return new Intl.NumberFormat("es-PE").format(value ?? 0);
}

function StatCard({ title, value, description, icon }: StatCardProps) {
  return (
    <div className="group rounded-3xl border border-slate-200 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:shadow-xl dark:border-slate-800 dark:bg-slate-900">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-black text-slate-500 dark:text-slate-400">{title}</p>
          <p className="mt-3 text-3xl font-black tracking-tight text-slate-950 dark:text-white">{value}</p>
        </div>
        <div className="grid h-12 w-12 place-items-center rounded-2xl bg-cyan-50 text-[#0083B0] transition group-hover:bg-[#C6EB32] group-hover:text-[#006a90] dark:bg-slate-800 dark:text-lime-300">
          <span className="material-icons">{icon}</span>
        </div>
      </div>
      <p className="mt-3 text-sm font-medium leading-relaxed text-slate-500 dark:text-slate-400">{description}</p>
    </div>
  );
}

function ModuleCard({ to, icon, eyebrow, title, description, highlight }: ModuleCardProps) {
  return (
    <Link
      to={to}
      className="group relative overflow-hidden rounded-3xl border border-slate-200 bg-white p-5 shadow-sm transition hover:-translate-y-1 hover:border-[#C6EB32] hover:shadow-xl dark:border-slate-800 dark:bg-slate-900"
    >
      <div className="absolute -right-10 -top-10 h-28 w-28 rounded-full bg-cyan-100/70 transition group-hover:bg-lime-200/80 dark:bg-cyan-500/10 dark:group-hover:bg-lime-300/10" />
      <div className="relative flex items-start gap-4">
        <div className="grid h-14 w-14 shrink-0 place-items-center rounded-2xl bg-[#006f96] text-white shadow-lg shadow-cyan-950/20 transition group-hover:bg-[#C6EB32] group-hover:text-[#006a90]">
          <span className="material-icons text-3xl">{icon}</span>
        </div>
        <div className="min-w-0">
          <p className="text-[11px] font-black uppercase tracking-[0.22em] text-[#0083B0] dark:text-lime-300">{eyebrow}</p>
          <h3 className="mt-1 text-lg font-black text-slate-950 dark:text-white">{title}</h3>
          <p className="mt-2 text-sm font-medium leading-relaxed text-slate-500 dark:text-slate-400">{description}</p>
          {highlight && (
            <p className="mt-4 inline-flex items-center gap-2 rounded-full bg-slate-100 px-3 py-1.5 text-xs font-black text-slate-600 dark:bg-slate-800 dark:text-slate-300">
              <span className="material-icons text-[16px]">verified</span>
              {highlight}
            </p>
          )}
        </div>
      </div>
    </Link>
  );
}

function EmptyAccessCard() {
  return (
    <div className="rounded-3xl border border-dashed border-slate-300 bg-white p-8 text-center dark:border-slate-700 dark:bg-slate-900">
      <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-300">
        <span className="material-icons text-3xl">lock</span>
      </div>
      <h3 className="mt-4 text-xl font-black text-slate-950 dark:text-white">No tienes módulos habilitados</h3>
      <p className="mx-auto mt-2 max-w-xl text-sm font-medium leading-relaxed text-slate-500 dark:text-slate-400">
        Tu usuario inició sesión correctamente, pero el perfil actual no tiene permisos visibles. Solicita a un administrador que revise el perfil asignado.
      </p>
    </div>
  );
}

export default function Home() {
  const user = getAuthUser();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);

  const canQuery = hasPermission("can_query");
  const canExport = hasPermission("can_export");
  const canManageUsers = hasPermission("can_manage_users");
  const canManageProfiles = hasPermission("can_manage_profiles");
  const canViewAudit = hasPermission("can_view_audit");
  const canViewConfig = hasPermission("can_view_system_config");
  const canViewClinicalHistory = hasPermission("can_view_clinical_history");
  const canUseTemplates = hasPermission("can_use_templates");

  const primaryAction = useMemo(() => {
    if (canQuery) return { to: "/consultas", icon: "auto_awesome", label: "Generar reporte" };
    if (canViewClinicalHistory) return { to: "/historias-clinicas", icon: "assignment_ind", label: "Ver historias clínicas" };
    if (canViewAudit) return { to: "/auditoria", icon: "manage_search", label: "Revisar auditoría" };
    if (canViewConfig) return { to: "/configuracion", icon: "settings", label: "Ver configuración" };
    if (canManageUsers) return { to: "/usuarios", icon: "group_add", label: "Gestionar usuarios" };
    if (canManageProfiles) return { to: "/perfiles", icon: "admin_panel_settings", label: "Gestionar perfiles" };
    return null;
  }, [canQuery, canViewClinicalHistory, canViewAudit, canViewConfig, canManageUsers, canManageProfiles]);

  useEffect(() => {
    if (canViewAudit) {
      getAdminDashboard().then(setSummary).catch(() => setSummary(null));
    }
  }, [canViewAudit]);

  const modules = [
    canQuery
      ? {
          to: "/consultas",
          icon: "auto_awesome",
          eyebrow: "Motor NL-to-SQL",
          title: "Consultas inteligentes",
          description: canExport
            ? "Pregunta en lenguaje natural, revisa resultados paginados, exporta reportes y conserva trazabilidad."
            : "Pregunta en lenguaje natural y revisa reportes dentro de los límites de tu perfil.",
          highlight: "Módulo principal",
        }
      : null,
    canQuery
      ? {
          to: "/historial-reportes",
          icon: "history",
          eyebrow: "Memoria de trabajo",
          title: "Historial de reportes",
          description: "Recupera conversaciones, compara resultados anteriores y vuelve a abrir reportes generados.",
          highlight: "Conversaciones guardadas",
        }
      : null,
    canViewClinicalHistory
      ? {
          to: "/historias-clinicas",
          icon: "assignment_ind",
          eyebrow: "Paciente 360",
          title: "Historias clínicas",
          description: "Consulta datos clínicos de pacientes desde una sección separada del generador de reportes.",
          highlight: "Vista dedicada",
        }
      : null,
    canUseTemplates
      ? {
          to: "/plantillas",
          icon: "article",
          eyebrow: "Biblioteca",
          title: "Plantillas reutilizables",
          description: "Estandariza preguntas frecuentes, compártelas y reutilízalas como punto de partida.",
          highlight: "Ahorro de tiempo",
        }
      : null,
    canManageUsers
      ? {
          to: "/usuarios",
          icon: "group_add",
          eyebrow: "Identidad",
          title: "Usuarios",
          description: "Administra cuentas, estados y perfiles sin mezclar esta tarea con la operación clínica diaria.",
        }
      : null,
    canManageProfiles
      ? {
          to: "/perfiles",
          icon: "admin_panel_settings",
          eyebrow: "Gobierno de datos",
          title: "Perfiles y permisos",
          description: "Controla vistas permitidas, permisos funcionales, límites y reglas de columnas por perfil.",
        }
      : null,
    canViewAudit
      ? {
          to: "/auditoria",
          icon: "manage_search",
          eyebrow: "Observabilidad",
          title: "Auditoría",
          description: "Revisa consultas, SQL generado, latencia, feedback y usuarios responsables de cada operación.",
        }
      : null,
    canViewConfig
      ? {
          to: "/configuracion",
          icon: "settings",
          eyebrow: "Sistema",
          title: "Configuración operativa",
          description: "Consulta límites, servicios conectados, endpoints internos y estado general de la plataforma.",
        }
      : null,
  ].filter(Boolean) as ModuleCardProps[];

  const latestReports = summary?.latest_reports?.slice(0, 3) ?? [];

  return (
    <div className="space-y-6">
      <section className="relative overflow-hidden rounded-[2rem] border border-slate-200 bg-[#006f96] p-6 text-white shadow-xl shadow-cyan-950/10 dark:border-slate-800 dark:bg-slate-900 lg:p-8">
        <div className="absolute -right-24 -top-24 h-72 w-72 rounded-full bg-[#C6EB32]/25 blur-2xl" />
        <div className="absolute bottom-0 right-10 hidden h-36 w-36 rounded-full bg-white/10 lg:block" />
        <div className="relative grid gap-8 lg:grid-cols-[1.45fr_0.75fr] lg:items-center">
          <div>
            <p className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1.5 text-xs font-black uppercase tracking-[0.22em] text-lime-100 ring-1 ring-white/15">
              <span className="material-icons text-[17px]">verified_user</span>
              Plataforma clínica segura
            </p>
            <h2 className="mt-5 max-w-4xl text-3xl font-black leading-tight tracking-tight sm:text-4xl lg:text-5xl">
              Hola, {user?.full_name || user?.username}. Gestiona reportes, plantillas, auditoría y permisos desde un solo lugar.
            </h2>
            <p className="mt-4 max-w-3xl text-base font-medium leading-relaxed text-cyan-50/90">
              Sistema de generación de reportes NL-to-SQL.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              {primaryAction && (
                <Link
                  to={primaryAction.to}
                  className="inline-flex items-center gap-2 rounded-2xl bg-[#C6EB32] px-5 py-3 text-sm font-black text-[#005f80] shadow-lg shadow-cyan-950/20 transition hover:-translate-y-0.5 hover:bg-lime-200"
                >
                  <span className="material-icons text-[20px]">{primaryAction.icon}</span>
                  {primaryAction.label}
                </Link>
              )}
              {canQuery && (
                <Link
                  to="/historial-reportes"
                  className="inline-flex items-center gap-2 rounded-2xl bg-white/10 px-5 py-3 text-sm font-black text-white ring-1 ring-white/20 transition hover:bg-white/20"
                >
                  <span className="material-icons text-[20px]">history</span>
                  Historial
                </Link>
              )}
              {canUseTemplates && (
                <Link
                  to="/plantillas"
                  className="inline-flex items-center gap-2 rounded-2xl bg-white/10 px-5 py-3 text-sm font-black text-white ring-1 ring-white/20 transition hover:bg-white/20"
                >
                  <span className="material-icons text-[20px]">article</span>
                  Plantillas
                </Link>
              )}
            </div>
          </div>

          <div className="rounded-3xl bg-white/12 p-4 ring-1 ring-white/15 backdrop-blur">
            <p className="text-xs font-black uppercase tracking-[0.22em] text-lime-100">Tu espacio</p>
            <div className="mt-4 space-y-3">
              <div className="rounded-2xl bg-white p-4 text-slate-900 shadow-lg shadow-cyan-950/10 dark:bg-slate-800 dark:text-white">
                <p className="text-sm font-black">Perfil activo</p>
                <p className="mt-1 text-2xl font-black text-[#006f96] dark:text-lime-300">{user?.profile || "Sin perfil"}</p>
                <p className="mt-2 text-xs font-semibold text-slate-500 dark:text-slate-400">
                  Los módulos visibles dependen de los permisos configurados.
                </p>
              </div>
              <div className="grid grid-cols-2 gap-3">
{/*                 <div className="rounded-2xl bg-white/10 p-4 ring-1 ring-white/10">
                  <p className="text-xs font-bold text-cyan-50/75">Módulos</p>
                  <p className="mt-1 text-2xl font-black">{modules.length}</p>
                </div>
                <div className="rounded-2xl bg-white/10 p-4 ring-1 ring-white/10">
                  <p className="text-xs font-bold text-cyan-50/75">Límite por página</p>
                  <p className="mt-1 text-2xl font-black">{user?.max_page_size ?? 0}</p>
                </div> */}
              </div>
            </div>
          </div>
        </div>
      </section>

      {summary && (
        <section className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
          <StatCard title="Reportes generados" value={formatNumber(summary.total_reports)} description="Preguntas convertidas a SQL y registradas." icon="bar_chart" />
          <StatCard title="Conversaciones" value={formatNumber(summary.total_conversations)} description="Hilos de análisis disponibles en historial." icon="forum" />
          <StatCard title="Usuarios en logs" value={formatNumber(summary.unique_users)} description="Usuarios con actividad en auditoría." icon="groups" />
          <StatCard title="Feedback" value={`${summary.feedback_positive}/${summary.feedback_negative}`} description="Valoraciones positivas y negativas." icon="thumbs_up_down" />
        </section>
      )}

      <section className="grid gap-6 xl:grid-cols-[1.35fr_0.65fr]">
        <div className="rounded-[2rem] border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900 lg:p-6">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="text-xs font-black uppercase tracking-[0.22em] text-[#0083B0] dark:text-lime-300">Centro de módulos</p>
              <h3 className="mt-1 text-2xl font-black text-slate-950 dark:text-white">Áreas disponibles para tu perfil</h3>
            </div>
            <p className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-black text-slate-500 dark:bg-slate-800 dark:text-slate-400">
              {modules.length} módulos activos
            </p>
          </div>

          {modules.length > 0 ? (
            <div className="mt-5 grid grid-cols-1 gap-4 lg:grid-cols-2">
              {modules.map((module) => (
                <ModuleCard key={module.to} {...module} />
              ))}
            </div>
          ) : (
            <div className="mt-5">
              <EmptyAccessCard />
            </div>
          )}
        </div>

        <aside className="space-y-4">
          <div className="rounded-[2rem] border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
            <p className="text-xs font-black uppercase tracking-[0.22em] text-[#0083B0] dark:text-lime-300">Flujo recomendado</p>
            <div className="mt-5 space-y-4">
              {[
                ["1", "Pregunta", "Ingresa una solicitud clínica o administrativa."],
                ["2", "Valida", "Revisa columnas, filas, SQL visible según permiso y latencia."],
                ["3", "Reutiliza", "Guarda reportes, usa plantillas y revisa auditoría."],
              ].map(([step, title, description]) => (
                <div key={step} className="flex gap-3">
                  <div className="grid h-9 w-9 shrink-0 place-items-center rounded-2xl bg-[#006f96] text-sm font-black text-white dark:bg-lime-300 dark:text-slate-950">
                    {step}
                  </div>
                  <div>
                    <p className="font-black text-slate-950 dark:text-white">{title}</p>
                    <p className="text-sm font-medium leading-relaxed text-slate-500 dark:text-slate-400">{description}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-[2rem] border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-xs font-black uppercase tracking-[0.22em] text-[#0083B0] dark:text-lime-300">Actividad reciente</p>
                <h3 className="mt-1 text-lg font-black text-slate-950 dark:text-white">Últimos reportes</h3>
              </div>
              {canViewAudit && (
                <Link to="/auditoria" className="text-sm font-black text-[#0083B0] hover:underline dark:text-lime-300">
                  Ver todo
                </Link>
              )}
            </div>
            <div className="mt-4 space-y-3">
              {latestReports.length > 0 ? (
                latestReports.map((report) => (
                  <div key={report.report_id} className="rounded-2xl bg-slate-50 p-3 dark:bg-slate-800/70">
                    <p className="line-clamp-2 text-sm font-bold text-slate-800 dark:text-slate-100">{report.nl}</p>
                    <p className="mt-2 text-xs font-semibold text-slate-500 dark:text-slate-400">
                      {report.username || "usuario"} · {new Date(report.timestamp).toLocaleString("es-PE")}
                    </p>
                  </div>
                ))
              ) : (
                <p className="rounded-2xl bg-slate-50 p-4 text-sm font-medium text-slate-500 dark:bg-slate-800/70 dark:text-slate-400">
                  {canViewAudit ? "Aún no hay actividad para mostrar." : "La actividad reciente se muestra solo a perfiles con permiso de auditoría."}
                </p>
              )}
            </div>
          </div>
        </aside>
      </section>
    </div>
  );
}
