import { useEffect, useState } from "react";
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

  useEffect(() => {
    if (hasPermission("can_view_audit")) {
      getAdminDashboard().then(setSummary).catch(() => setSummary(null));
    }
  }, []);

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
            Esta pantalla organiza el sistema como plataforma: consultas NL-to-SQL, administración de usuarios,
            perfiles con restricciones, auditoría y configuración operativa.
          </p>
          <div className="mt-5 flex flex-wrap gap-3">
            <Link
              to="/consultas"
              className="inline-flex items-center gap-2 px-5 py-3 rounded-lg bg-[#0083B0] hover:bg-[#006a90] text-white font-bold transition"
            >
              <span className="material-icons">query_stats</span>
              Ir a consultas
            </Link>
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
        <ModuleLink
          to="/consultas"
          icon="query_stats"
          title="Módulo de consultas"
          description="Pregunta en lenguaje natural, revisa resultados paginados y exporta reportes."
        />

        {hasPermission("can_manage_users") && (
          <ModuleLink to="/usuarios" icon="group_add" title="Usuarios" description="Crea usuarios, cambia estado y perfil asignado." />
        )}

        {hasPermission("can_manage_profiles") && (
          <ModuleLink
            to="/perfiles"
            icon="admin_panel_settings"
            title="Perfiles y permisos"
            description="Configura permisos, límites de consulta y vistas permitidas por perfil."
          />
        )}

        {hasPermission("can_view_audit") && (
          <ModuleLink
            to="/auditoria"
            icon="manage_search"
            title="Auditoría"
            description="Revisa quién preguntó, qué preguntó, cuándo y qué SQL se generó."
          />
        )}

        {hasPermission("can_view_system_config") && (
          <ModuleLink
            to="/configuracion"
            icon="settings"
            title="Configuración del sistema"
            description="Consulta límites, endpoints internos, perfil de esquema y vistas permitidas."
          />
        )}
      </section>
    </>
  );
}
