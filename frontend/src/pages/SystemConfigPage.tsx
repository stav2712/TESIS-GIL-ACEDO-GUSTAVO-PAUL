import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import {

  getSystemConfig,
  getSystemStatus,
  updateSystemConfig,
  type SystemConfig,
  type SystemServiceStatus,
} from "../api";
import { getAuthUser, hasPermission } from "../auth";

type ConfigDraft = {
  query_display_max_rows: number;
  export_max_rows: number;
  query_timeout_seconds: number;
};

const EXPORT_PRESETS = [0, 1000, 5000, 10000, 50000, 100000];

function formatRows(value: number) {
  return value.toLocaleString("es-PE");
}

function configToDraft(config: SystemConfig): ConfigDraft {
  return {
    query_display_max_rows: config.query_display_max_rows,
    export_max_rows: config.export_max_rows,
    query_timeout_seconds: config.query_timeout_seconds,
  };
}

function ConfigCard({ title, value, description, icon }: { title: string;
value: string | number; description: string; icon: string }) {
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

function Notice({ tone, icon, children }: { tone: "info" | "success" |
"warning" | "error"; icon: string; children: ReactNode }) {
  const styles = {
    info: "bg-cyan-50 text-[#005f80] border-cyan-100 dark:bg-slate-950 dark:text-slate-200 dark:border-slate-800",
    success: "bg-[#C6EB32]/30 text-[#005f80] border-[#C6EB32] dark:bg-lime-950/30 dark:text-lime-200 dark:border-lime-900",
    warning: "bg-amber-50 text-amber-900 border-amber-200 dark:bg-amber-950/30 dark:text-amber-100 dark:border-amber-900",

    error: "bg-red-100 text-red-700 border-red-200 dark:bg-red-950/30 dark:text-red-100 dark:border-red-900",
  } as const;

  return (
    <div className={["mt-4 p-3 rounded-xl border flex items-start gap-3 text-sm", styles[tone]].join(" ")}>
      <span className="material-icons text-base mt-0.5">{icon}</span>
      <div>{children}</div>
    </div>
  );
}

function NumberField({
  label,
  value,
  min,
  max,
  step = 1,
  helper,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  helper: string;
  onChange: (value: number) => void;
}) {
  return (
    <label className="block">
       <span className="text-sm font-bold text-slate-600 dark:text-slate-300">{label}</span>
       <input
          className="mt-1 w-full px-3 py-2.5 rounded-lg border border-cyan-100 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-[#0083B0]"
          type="number"
          min={min}
          max={max}
          step={step}
          value={Number.isFinite(value) ? value : 0}
          onChange={(e) => onChange(Number(e.target.value))}
       />
       <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">{helper}</p>
    </label>
  );
}

function StatusPill({ service }: { service: SystemServiceStatus }) {
  return (
    <div className="rounded-xl bg-white/75 dark:bg-slate-950 p-3 border border-white/60 dark:border-slate-800">

      <div className="flex items-center justify-between gap-2">
        <dt className="text-slate-500 dark:text-slate-400 font-semibold">{service.label}</dt>
        <span
           className={[
             "px-2 py-0.5 rounded-full text-[11px] font-bold",
             service.ok ? "bg-[#C6EB32]/50 text-[#005f80]" : "bg-red-100 text-red-700 dark:bg-red-950/40 dark:text-red-100",
           ].join(" ")}
        >
           {service.ok ? "OK" : "Revisar"}
        </span>
      </div>
      <dd className="font-mono break-all mt-1 text-xs text-slate-700 dark:text-slate-200">{service.configured_url}</dd>
      <p className="text-xs text-slate-500 dark:text-slate-400 mt-2">{service.detail}</p>
    </div>
  );
}

export default function SystemConfigPage() {
  const [config, setConfig] = useState<SystemConfig | null>(null);
  const [draft, setDraft] = useState<ConfigDraft | null>(null);
  const [services, setServices] = useState<SystemServiceStatus[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [statusErr, setStatusErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [checking, setChecking] = useState(false);
  const [lowTimeoutAccepted, setLowTimeoutAccepted] = useState(false);
  const user = getAuthUser();
  const canEditSystemConfig = user?.profile?.trim().toLowerCase() === "admin" || hasPermission("can_manage_profiles");

 async function loadConfig() {
   const next = await getSystemConfig();
   setConfig(next);
   setDraft(configToDraft(next));
 }

  async function loadStatus() {
    setChecking(true);
    setStatusErr(null);
    try {
      const status = await getSystemStatus();
      setServices(status.services);
    } catch (ex) {
      setStatusErr(ex instanceof Error ? ex.message : "No se pudo validar servicios internos");
    } finally {
      setChecking(false);
    }
  }

 useEffect(() => {
   loadConfig()
     .then(loadStatus)

      .catch((ex) => setErr(ex instanceof Error ? ex.message : "No se pudo cargar configuración"));
  }, []);

  const limits = config?.limits;
  const displayMin = limits?.query_display_max_rows.min ?? 50;
  const displayMax = limits?.query_display_max_rows.max ?? 100000;
  const exportMinEnabled = limits?.export_max_rows.min_when_enabled ?? 100;
  const exportMax = limits?.export_max_rows.max ?? 250000;
  const timeoutMin = limits?.query_timeout_seconds.min ?? 5;
  const timeoutMax = limits?.query_timeout_seconds.max ?? 900;
  const timeoutWarningBelow = limits?.query_timeout_seconds.warning_below ??
30;

  const timeoutIsLow = Boolean(draft && draft.query_timeout_seconds <
timeoutWarningBelow);
  const hasChanges = useMemo(() => {
    if (!config || !draft) return false;
    return (
       draft.query_display_max_rows !== config.query_display_max_rows ||
       draft.export_max_rows !== config.export_max_rows ||
       draft.query_timeout_seconds !== config.query_timeout_seconds
    );
  }, [config, draft]);

  function validateDraft(): string | null {
    if (!draft) return "La configuración aún no está lista.";

    if (draft.query_display_max_rows < displayMin ||
draft.query_display_max_rows > displayMax) {
      return `El límite visual debe estar entre ${formatRows(displayMin)} y ${formatRows(displayMax)}.`;
    }

    if (draft.export_max_rows < 0 || draft.export_max_rows > exportMax) {
      return `El límite de exportación debe ser 0 o estar como máximo en ${formatRows(exportMax)}.`;
    }

    if (draft.export_max_rows !== 0 && draft.export_max_rows <
exportMinEnabled) {
      return `Para exportación usa 0 si no quieres límite o un valor desde ${formatRows(exportMinEnabled)}.`;
    }

    if (draft.query_timeout_seconds < timeoutMin || draft.query_timeout_seconds
> timeoutMax) {
      return `El timeout SQL debe estar entre ${timeoutMin} y ${timeoutMax} segundos.`;
    }

    if (timeoutIsLow && !lowTimeoutAccepted) {
      return "Confirma la advertencia de timeout bajo antes de guardar.";
    }

      return null;
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    setMsg(null);

      if (!canEditSystemConfig) {
        setErr("Solo un administrador puede modificar la configuración operativa.");
        return;
      }

      const validation = validateDraft();
      if (validation) {
        setErr(validation);
        return;
      }

      if (!draft) return;

    try {
      setSaving(true);
      const saved = await updateSystemConfig({
        query_display_max_rows: draft.query_display_max_rows,
        export_max_rows: draft.export_max_rows,
        query_timeout_seconds: draft.query_timeout_seconds,
      });
      setConfig(saved);
      setDraft(configToDraft(saved));
      setLowTimeoutAccepted(false);
      setMsg("Configuración guardada. Se aplicará en las nuevas consultas, paginaciones y exportaciones.");
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "No se pudo guardar configuración");
    } finally {
      setSaving(false);
    }
  }

  function resetDraft() {
    if (!config) return;
    setDraft(configToDraft(config));
    setErr(null);
    setMsg(null);
    setLowTimeoutAccepted(false);
  }

  return (
    <>
       <section className="rounded-3xl bg-white dark:bg-slate-900 border border-cyan-100 dark:border-slate-800 p-6 shadow-xl shadow-cyan-950/10">
         <p className="text-sm uppercase tracking-[0.25em] text-[#0083B0] dark:text-lime-300 font-bold">Sistema</p>
         <h2 className="text-3xl font-bold text-slate-900 dark:text-white">Configuración operativa</h2>
         <p className="text-slate-500 dark:text-slate-400 mt-1">
           Ajusta límites globales de visualización, exportación y ejecución SQL
sin exponer secretos del entorno.

        </p>
      </section>

      {err && <Notice tone="error" icon="error_outline">{err}</Notice>}
      {msg && <Notice tone="success" icon="check_circle">{msg}</Notice>}

      {config && draft && (
        <>
           <section className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-6">
             <ConfigCard
               title="Límite visual"
               value={formatRows(config.query_display_max_rows)}
               description="Valor global para filas navegables/mostrables en UI; mínimo 50."
               icon="table_rows"
             />
             <ConfigCard
               title="Límite exportación"
               value={config.export_max_rows === 0 ? "Sin límite" :
formatRows(config.export_max_rows)}
               description={config.export_max_rows_meaning}
               icon="file_download"
             />
             <ConfigCard
               title="Timeout SQL"
               value={`${config.query_timeout_seconds}s`}
               description="Tiempo máximo de espera del orquestador al ejecutar SQL."
               icon="timer"
             />
           </section>

          {canEditSystemConfig ? (
          <form
             onSubmit={onSubmit}
             className="mt-6 rounded-2xl bg-white dark:bg-slate-900 border border-cyan-100 dark:border-slate-800 p-5 shadow-xl shadow-cyan-950/10"
          >
             <div className="flex items-center justify-between gap-3 flex-wrap">
               <div className="flex items-center gap-2">
                 <span className="material-icons text-[#0083B0] dark:text-lime-300">tune</span>
                 <div>
                   <h3 className="font-bold text-xl text-slate-900 dark:text-white">Parámetros editables</h3>
                   <p className="text-xs text-slate-500 dark:text-slate-400">
                      Guardar requiere perfil administrador o permiso de gestión
de perfiles.
                   </p>
                 </div>
               </div>

              {hasChanges && <span className="px-3 py-1 rounded-full bg-[#C6EB32]/35 text-[#005f80] text-xs font-bold">Cambios sin guardar</span>}
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 mt-5">
              <NumberField
                 label="Límite visual"
                 value={draft.query_display_max_rows}
                 min={displayMin}
                 max={displayMax}
                 step={50}
                 helper={`Mínimo ${formatRows(displayMin)}. Afecta solo vista y paginación, no exportación.`}
                 onChange={(value) => setDraft((d) => (d ? { ...d,
query_display_max_rows: value } : d))}
              />

              <div>
                <NumberField
                  label="Límite exportación"
                  value={draft.export_max_rows}
                  min={0}
                  max={exportMax}
                  step={100}
                  helper={`0 = sin límite. Si activas límite, usa al menos ${formatRows(exportMinEnabled)} filas.`}
                  onChange={(value) => setDraft((d) => (d ? { ...d,
export_max_rows: value } : d))}
                />
                <div className="flex flex-wrap gap-2 mt-3">
                  {EXPORT_PRESETS.map((preset) => (
                     <button
                       key={preset}
                       type="button"
                       onClick={() => setDraft((d) => (d ? { ...d,
export_max_rows: preset } : d))}
                       className={[
                         "px-3 py-1.5 rounded-full text-xs font-bold border transition",
                         draft.export_max_rows === preset
                           ? "bg-[#0083B0] text-white border-[#0083B0]"
                           : "bg-cyan-50 text-[#005f80] border-cyan-100 hover:bg-cyan-100 dark:bg-slate-950 dark:text-slate-200 dark:border-slate-800",
                       ].join(" ")}
                     >
                       {preset === 0 ? "Sin límite" : formatRows(preset)}
                     </button>
                  ))}
                </div>
              </div>

              <NumberField
                label="Timeout SQL"
                value={draft.query_timeout_seconds}
                min={timeoutMin}
                max={timeoutMax}
                step={5}
                helper={`Debajo de ${timeoutWarningBelow}s requiere confirmación porque puede cortar consultas válidas.`}

                onChange={(value) => {
                  setDraft((d) => (d ? { ...d, query_timeout_seconds: value } :
d));
                  setLowTimeoutAccepted(false);
                }}
              />
            </div>

            {timeoutIsLow && (
              <div className="mt-5 rounded-2xl border border-amber-200 dark:border-amber-900 bg-amber-50 dark:bg-amber-950/30 p-4">
                <div className="flex items-start gap-3">
                  <span className="material-icons text-amber-600 dark:text-amber-300">warning</span>
                  <div>
                     <h4 className="font-bold text-amber-900 dark:text-amber-100">Timeout SQL bajo</h4>
                     <p className="text-sm text-amber-800 dark:text-amber-100/90 mt-1">
                       Con {draft.query_timeout_seconds}s una consulta pesada
puede quedarse sin respuesta aunque la base de datos esté funcionando. Úsalo
solo si necesitas cortar rápido consultas largas.
                     </p>
                     <label className="mt-3 flex items-center gap-2 text-sm font-semibold text-amber-900 dark:text-amber-100">
                       <input
                         type="checkbox"
                         className="w-4 h-4 accent-amber-600"
                         checked={lowTimeoutAccepted}
                         onChange={(e) =>
setLowTimeoutAccepted(e.target.checked)}
                       />
                       Entiendo el riesgo y quiero guardar este timeout.
                     </label>
                  </div>
                </div>
              </div>
            )}

            {config.warnings?.length ? (
              <Notice tone="warning" icon="tips_and_updates">
                <ul className="list-disc pl-4 space-y-1">
                  {config.warnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              </Notice>
            ) : null}

            <div className="mt-6 flex justify-end gap-3 flex-wrap">
              <button
                type="button"
                onClick={resetDraft}
                disabled={!hasChanges || saving}
                className="px-5 py-3 rounded-lg bg-cyan-50 hover:bg-cyan-100 text-[#005f80] font-bold transition disabled:opacity-50 dark:bg-slate-950 dark:hover:bg-slate-800 dark:text-slate-200"
              >
                Revertir
              </button>
              <button
                type="submit"
                disabled={!hasChanges || saving}
                className="px-5 py-3 rounded-lg bg-[#0083B0] hover:bg-[#006a90] text-white font-bold transition disabled:opacity-60"
              >
                {saving ? "Guardando..." : "Guardar configuración"}
              </button>
            </div>
          </form>
          ) : (
            <Notice tone="info" icon="visibility">
              Puedes ver la configuración operativa, pero el formulario de parámetros editables está oculto porque tu perfil no tiene permisos administrativos.
            </Notice>
          )}

          <section className="mt-6 rounded-2xl bg-[#C6EB32] dark:bg-slate-900 border border-lime-200 dark:border-slate-800 p-5 shadow-xl shadow-cyan-950/10">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <div className="flex items-center gap-2 text-[#005f80] dark:text-white">
                <span className="material-icons">settings_ethernet</span>
                <div>
                  <h3 className="font-bold text-lg">Endpoints internos</h3>
                  <p className="text-xs text-[#005f80]/80 dark:text-slate-400">
                     Útiles para diagnóstico; el navegador no los llama
directamente.
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={loadStatus}
                disabled={checking}
                className="px-4 py-2 rounded-lg bg-white/80 hover:bg-white text-[#005f80] font-bold transition disabled:opacity-60 dark:bg-slate-950 dark:text-slate-100 dark:hover:bg-slate-800"
              >
                {checking ? "Validando..." : "Validar servicios"}
              </button>
            </div>

            {statusErr && <Notice tone="error"
icon="sync_problem">{statusErr}</Notice>}

            <dl className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 mt-4 text-sm">
              {services.length > 0 ? (
                services.map((service) => <StatusPill key={service.key}
service={service} />)
              ) : (
                <>
                  <div className="rounded-xl bg-white/75 dark:bg-slate-950 p-3">
                    <dt className="text-slate-500 font-semibold">Query

service</dt>
                      <dd className="font-mono break-all mt-1">{config.query_url}</dd>
                    </div>
                    <div className="rounded-xl bg-white/75 dark:bg-slate-950 p-3">
                      <dt className="text-slate-500 font-semibold">Terminology
service</dt>
                      <dd className="font-mono break-all mt-1">{config.terminology_url}</dd>
                    </div>
                    <div className="rounded-xl bg-white/75 dark:bg-slate-950 p-3">
                      <dt className="text-slate-500 font-semibold">Translator
configurado</dt>
                      <dd className="mt-1 font-bold">{config.translator_url_configured ? "Sí" : "No"}</dd>
                    </div>
                  </>
               )}
             </dl>
          </section>

          <section className="mt-6 rounded-2xl bg-white dark:bg-slate-900 border border-cyan-100 dark:border-slate-800 p-5 shadow-xl shadow-cyan-950/10">
            <div className="flex items-center gap-2">
              <span className="material-icons text-[#0083B0] dark:text-lime-300 mt-0.5">schema</span>
              <h3 className="font-bold text-lg text-slate-900 dark:text-white">Perfil de esquema activo</h3>
            </div>
            <div className="mt-4 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
                <code className="mt-3 block text-xs rounded-lg bg-cyan-50 dark:bg-slate-950 p-3 break-all border border-cyan-100 dark:border-slate-800">
                  {config.schema_profile_path}
                </code>
            </div>
          </section>

          <section className="mt-6 rounded-2xl bg-white dark:bg-slate-900 border border-cyan-100 dark:border-slate-800 p-5 shadow-xl shadow-cyan-950/10">
            <div className="flex items-center gap-2">
              <span className="material-icons text-[#0083B0] dark:text-lime-300">dataset</span>
              <h3 className="font-bold text-lg">Vistas globalmente
permitidas</h3>
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
