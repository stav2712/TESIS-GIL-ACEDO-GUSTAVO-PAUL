import { useEffect, useState } from "react";
import { getSystemConfig, type SystemConfig } from "../api";

function ConfigCard({ title, value, description, icon }: { title: string; value: string | number; description: string; icon: string }) {
  return (
    <div className="rounded-2xl bg-white dark:bg-slate-900 border border-cyan-100 dark:border-slate-800 p-5 shadow-xl shadow-cyan-950/10">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-semibold text-slate-500 dark:text-slate-400">{title}</p>
        <span className="material-icons text-[#0083B0] dark:text-lime-300">{icon}</span>
      </div>
      <p className="text-3xl font-bold mt-3 text-slate-900 dark:text-white">{value}</p>
      <p className="text-sm text-slate-500 dark:text-slate-400 mt-2">{description}</p>
    </div>
  );
}

export default function SystemConfigPage() {
  const [config, setConfig] = useState<SystemConfig | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    getSystemConfig()
      .then(setConfig)
      .catch((ex) => setErr(ex instanceof Error ? ex.message : "No se pudo cargar configuración"));
  }, []);

  return (
    <>
      <section className="rounded-3xl bg-white dark:bg-slate-900 border border-cyan-100 dark:border-slate-800 p-6 shadow-xl shadow-cyan-950/10">
        <p className="text-sm uppercase tracking-[0.25em] text-[#0083B0] dark:text-lime-300 font-bold">Sistema</p>
        <h2 className="text-3xl font-bold text-slate-900 dark:text-white">Configuración operativa</h2>
        <p className="text-slate-500 dark:text-slate-400 mt-1">
          Lectura de parámetros.
        </p>
      </section>

      {err && <div className="mt-4 p-3 rounded-lg bg-red-100 text-red-700 border border-red-200">{err}</div>}

      {config && (
        <>
          <section className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-6">
            <ConfigCard
              title="Límite visual"
              value={config.query_display_max_rows}
              description="Valor global para todos los perfiles; las exportaciones no usan este límite visual."
              icon="table_rows"
            />
            <ConfigCard
              title="Límite exportación"
              value={config.export_max_rows === 0 ? "Sin límite" : config.export_max_rows}
              description={config.export_max_rows_meaning}
              icon="file_download"
            />
            <ConfigCard
              title="Timeout SQL"
              value={`${config.query_timeout_seconds}s`}
              description="Tiempo máximo para ejecución de consultas."
              icon="timer"
            />
          </section>

          <section className="mt-6 rounded-2xl bg-[#C6EB32] dark:bg-slate-900 border border-lime-200 dark:border-slate-800 p-5 shadow-xl shadow-cyan-950/10">
            <div className="flex items-center gap-2 text-[#005f80] dark:text-white">
              <span className="material-icons">settings_ethernet</span>
              <h3 className="font-bold text-lg">Endpoints internos</h3>
            </div>
            <dl className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4 text-sm">
              <div className="rounded-xl bg-white/75 dark:bg-slate-950 p-3">
                <dt className="text-slate-500 font-semibold">Query service</dt>
                <dd className="font-mono break-all mt-1">{config.query_url}</dd>
              </div>
              <div className="rounded-xl bg-white/75 dark:bg-slate-950 p-3">
                <dt className="text-slate-500 font-semibold">Terminology service</dt>
                <dd className="font-mono break-all mt-1">{config.terminology_url}</dd>
              </div>
              <div className="rounded-xl bg-white/75 dark:bg-slate-950 p-3">
                <dt className="text-slate-500 font-semibold">Translator configurado</dt>
                <dd className="mt-1 font-bold">{config.translator_url_configured ? "Sí" : "No"}</dd>
              </div>
              <div className="rounded-xl bg-white/75 dark:bg-slate-950 p-3">
                <dt className="text-slate-500 font-semibold">Perfil de esquema</dt>
                <dd className="font-mono break-all mt-1">{config.schema_profile_path}</dd>
              </div>
            </dl>
          </section>

          <section className="mt-6 rounded-2xl bg-white dark:bg-slate-900 border border-cyan-100 dark:border-slate-800 p-5 shadow-xl shadow-cyan-950/10">
            <div className="flex items-center gap-2">
              <span className="material-icons text-[#0083B0] dark:text-lime-300">dataset</span>
              <h3 className="font-bold text-lg">Vistas globalmente permitidas</h3>
            </div>
            <div className="mt-4 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
              {config.allowed_tables.map((t) => (
                <code key={t} className="text-xs rounded-lg bg-cyan-50 dark:bg-slate-950 p-2 break-all border border-cyan-100 dark:border-slate-800">
                  {t}
                </code>
              ))}
            </div>
          </section>
        </>
      )}
    </>
  );
}
