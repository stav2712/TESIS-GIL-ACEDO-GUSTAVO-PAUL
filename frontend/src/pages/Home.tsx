import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getAdminDashboard, type DashboardSummary } from "../api";
import { getAuthUser, hasPermission } from "../auth";

function MetricCard({
  title,
  value,
  description,
  icon,
}: {
  title: string;
  value: string | number;
  description: string;
  icon: string;
}) {
  return (
    <div className="rounded-2xl bg-white dark:bg-slate-900 border border-cyan-100 dark:border-slate-800 p-5 shadow-lg shadow-cyan-950/10">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-semibold text-slate-500 dark:text-slate-400">{title}</p>
        <span className="material-icons text-[#0083B0] dark:text-lime-300">{icon}</span>
      </div>
      <p className="text-3xl font-bold mt-3 text-slate-900 dark:text-white">{value}</p>
      <p className="text-sm text-slate-500 dark:text-slate-400 mt-2">{description}</p>
    </div>
  );
}

function ModuleLink({
  to,
  icon,
  title,
  description,
}: {
  to: string;
  icon: string;
  title: string;
  description: string;
}) {
  return (
    <Link
      to={to}
      className="group rounded-2xl bg-white dark:bg-slate-900 border border-cyan-100 dark:border-slate-800 p-5 shadow-lg shadow-cyan-950/10 hover:-translate-y-0.5 hover:shadow-xl hover:border-[#C6EB32] transition"
    >
      <div className="flex items-start gap-4">
        <div className="w-12 h-12 rounded-2xl bg-[#C6EB32] text-[#006a90] flex items-center justify-center shrink-0">
          <span className="material-icons text-3xl">{icon}</span>
        </div>
        <div>
          <h3 className="font-bold text-lg text-slate-900 dark:text-white group-hover:text-[#0083B0] dark:group-hover:text-lime-300">
            {title}
          </h3>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">{description}</p>
        </div>
      </div>
    </Link>
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

  const primaryAction = useMemo(() => {
    if (canQuery) {
      return {
        to: "/consultas",
        icon: "query_stats",
        label: "Ir a consultas",
        tone: "primary" as const,
      };
    }

    if (canViewAudit) {
      return {
        to: "/auditoria",
        icon: "manage_search",
        label: "Ver auditoría",
        tone: "primary" as const,
      };
    }

    if (canViewConfig) {
      return {
        to: "/configuracion",
        icon: "settings",
        label: "Ver configuración",
        tone: "primary" as const,
      };
    }

    if (canManageUsers) {
      return {
        to: "/usuarios",
        icon: "group_add",
        label: "Gestionar usuarios",
        tone: "primary" as const,
      };
    }

    if (canManageProfiles) {
      return {
        to: "/perfiles",
        icon: "admin_panel_settings",
        label: "Gestionar perfiles",
        tone: "primary" as const,
      };
    }

    return null;
  }, [canQuery, canViewAudit, canViewConfig, canManageUsers, canManageProfiles]);

  useEffect(() => {
    if (canViewAudit) {
      getAdminDashboard().then(setSummary).catch(() => setSummary(null));
    }
  }, [canViewAudit]);

  const queryDescription = canExport
    ? "Pregunta en lenguaje natural, revisa un reporte organizado y exporta resultados."
    : "Pregunta en lenguaje natural y revisa un reporte organizado según tu perfil.";

  return (
    <>
      <section className="rounded-3xl bg-[#C6EB32] dark:bg-slate-900 border border-lime-200 dark:border-slate-700 p-6 lg:p-8 shadow-xl shadow-cyan-950/20 overflow-hidden relative">
        <div className="absolute -right-16 -top-16 w-48 h-48 rounded-full bg-white/25 dark:bg-white/5" />
        <div className="absolute -right-4 bottom-4 w-28 h-28 rounded-full bg-white/20 dark:bg-white/5" />

        <div className="relative">
          <p className="text-sm uppercase tracking-[0.3em] text-[#006a90] dark:text-lime-300 font-bold">Dashboard principal</p>
          <h2 className="text-3xl lg:text-4xl font-bold mt-2 text-[#005f80] dark:text-white">
            Hola, {user?.full_name || user?.username}.
          </h2>
          <p className="text-[#005f80]/90 dark:text-slate-300 mt-3 max-w-3xl font-medium">
            Accede únicamente a los módulos habilitados para tu perfil: consultas, historial de reportes, plantillas, administración,
            auditoría y configuración operativa.
          </p>
          <div className="mt-5 flex flex-wrap gap-3">
            {primaryAction && (
              <Link
                to={primaryAction.to}
                className="inline-flex items-center gap-2 px-5 py-3 rounded-lg bg-[#0083B0] hover:bg-[#006a90] text-white font-bold transition"
              >
                <span className="material-icons">{primaryAction.icon}</span>
                {primaryAction.label}
              </Link>
            )}

            {canQuery && (
              <Link
                to="/historial-reportes"
                className="inline-flex items-center gap-2 px-5 py-3 rounded-lg bg-white/80 hover:bg-white text-[#006a90] font-bold transition"
              >
                <span className="material-icons">history</span>
                Ver historial
              </Link>
            )}

            {canQuery && (
              <Link
                to="/plantillas"
                className="inline-flex items-center gap-2 px-5 py-3 rounded-lg bg-white/80 hover:bg-white text-[#006a90] font-bold transition"
              >
                <span className="material-icons">article</span>
                Ver plantillas
              </Link>
            )}
          </div>
        </div>
      </section>

      {summary && (
        <section className="grid grid-cols-1 md:grid-cols-4 gap-4 mt-6">
          <MetricCard title="Reportes generados" value={summary.total_reports} description="Preguntas convertidas a SQL." icon="bar_chart" />
          <MetricCard title="Conversaciones" value={summary.total_conversations} description="Hilos activos de consulta." icon="forum" />
          <MetricCard title="Usuarios en logs" value={summary.unique_users} description="Usuarios que realizaron preguntas." icon="groups" />
          <MetricCard
            title="Feedback"
            value={`${summary.feedback_positive}/${summary.feedback_negative}`}
            description="Positivos / negativos."
            icon="thumbs_up_down"
          />
        </section>
      )}

      <section className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mt-6">
        {canQuery && (
          <ModuleLink
            to="/consultas"
            icon="query_stats"
            title="Consultas"
            description={queryDescription}
          />
        )}

        {canQuery && (
          <ModuleLink
            to="/historial-reportes"
            icon="history"
            title="Historial de reportes"
            description="Consulta reportes generados anteriormente en un panel independiente, ordenado y exportable."
          />
        )}

        {canQuery && (
          <ModuleLink
            to="/plantillas"
            icon="article"
            title="Plantillas"
            description="Guarda, comparte, copia y ejecuta consultas frecuentes."
          />
        )}

        {canManageUsers && (
          <ModuleLink to="/usuarios" icon="group_add" title="Usuarios" description="Crea usuarios, cambia estado y perfil asignado." />
        )}

        {canManageProfiles && (
          <ModuleLink
            to="/perfiles"
            icon="admin_panel_settings"
            title="Perfiles y permisos"
            description="Configura permisos, límites de consulta y vistas permitidas por perfil."
          />
        )}

        {canViewAudit && (
          <ModuleLink
            to="/auditoria"
            icon="manage_search"
            title="Auditoría"
            description="Revisa quién preguntó, qué preguntó, cuándo y qué SQL se generó."
          />
        )}

        {canViewConfig && (
          <ModuleLink
            to="/configuracion"
            icon="settings"
            title="Configuración"
            description="Consulta límites, endpoints internos, perfil de esquema y vistas permitidas."
          />
        )}
      </section>
    </>
  );
}
