import { useEffect, useMemo, useState } from "react";
import { clearToken, getToken } from "../auth";

type PagedData = {
  columns: string[];
  rows: Record<string, unknown>[];
  page: number;
  page_size: number;
  row_count: number;
  total_count?: number | null;
  display_total_count?: number | null;
  total_pages?: number | null;
  max_result_window?: number | null;
  max_result_window_exceeded?: boolean;
  result_message?: string | null;
  suppressed_columns?: string[];
};

type PatientHistoryResponse = {
  patient: Record<string, unknown>;
  patient_suppressed_columns?: string[];
  events: PagedData;
};

const PATIENT_PAGE_SIZE = 20;
const EVENTS_PAGE_SIZE = 25;

function formatValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "boolean") return value ? "Sí" : "No";
  if (typeof value === "number") return value.toLocaleString("es-PE");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function formatDate(value: unknown) {
  if (typeof value !== "string" || !value) return formatValue(value);
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("es-PE");
}

function getText(row: Record<string, unknown>, key: string) {
  return formatValue(row[key]);
}

function getPatientId(row: Record<string, unknown>): number | null {
  const raw = row.id_paciente;
  if (typeof raw === "number" && Number.isFinite(raw)) return raw;
  const parsed = Number(raw);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function isDateKey(key: string) {
  return key.includes("fecha") || key.endsWith("_at");
}

async function apiRequest<T>(url: string): Promise<T> {
  const token = getToken();
  const headers = token ? { Authorization: `Bearer ${token}` } : undefined;
  let res: Response;

  try {
    res = await fetch(url, { headers });
  } catch (error) {
    console.error("[clinical-history network error]", error);
    throw new Error("No se pudo conectar con el servidor. Verifica que los servicios estén ejecutándose.");
  }

  if (!res.ok) {
    if (res.status === 401) clearToken();
    let message = `No se pudo completar la operación. Código HTTP ${res.status}.`;
    try {
      const parsed = await res.json();
      const detail = parsed?.detail ?? parsed?.error;
      if (typeof detail === "string") message = detail;
      else if (detail?.error && typeof detail.error === "string") message = detail.error;
    } catch {
      const text = await res.text().catch(() => "");
      if (text && text.length < 250) message = text;
    }
    throw new Error(message);
  }

  return (await res.json()) as T;
}

function totalRows(data: PagedData | null) {
  if (!data) return 0;
  return data.total_count ?? data.display_total_count ?? data.row_count ?? 0;
}

export default function ClinicalHistoryPage() {
  const [patients, setPatients] = useState<PagedData | null>(null);
  const [patientPage, setPatientPage] = useState(1);
  const [patientQ, setPatientQ] = useState("");
  const [selectedPatientId, setSelectedPatientId] = useState<number | null>(null);
  const [history, setHistory] = useState<PatientHistoryResponse | null>(null);
  const [eventQ, setEventQ] = useState("");
  const [eventsPage, setEventsPage] = useState(1);
  const [loadingPatients, setLoadingPatients] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const selectedPatientName = useMemo(() => {
    if (!history?.patient) return "Selecciona un paciente";
    return getText(history.patient, "nombre_completo");
  }, [history]);

  async function loadPatients(nextPage = 1) {
    setLoadingPatients(true);
    setErr(null);
    try {
      const sp = new URLSearchParams();
      sp.set("page", String(nextPage));
      sp.set("page_size", String(PATIENT_PAGE_SIZE));
      if (patientQ.trim()) sp.set("q", patientQ.trim());
      const data = await apiRequest<PagedData>(`/api/orchestrator/clinical-history/patients?${sp.toString()}`);
      setPatients(data);
      setPatientPage(data.page ?? nextPage);
      if (!selectedPatientId && data.rows.length) {
        const firstId = getPatientId(data.rows[0]);
        if (firstId) await loadHistory(firstId, 1, eventQ);
      }
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "No se pudieron cargar pacientes");
    } finally {
      setLoadingPatients(false);
    }
  }

  async function loadHistory(patientId: number, nextEventsPage = 1, nextEventQ = eventQ) {
    setLoadingHistory(true);
    setErr(null);
    try {
      const sp = new URLSearchParams();
      sp.set("events_page", String(nextEventsPage));
      sp.set("events_page_size", String(EVENTS_PAGE_SIZE));
      if (nextEventQ.trim()) sp.set("event_q", nextEventQ.trim());
      const data = await apiRequest<PatientHistoryResponse>(`/api/orchestrator/clinical-history/patients/${patientId}?${sp.toString()}`);
      setSelectedPatientId(patientId);
      setHistory(data);
      setEventsPage(data.events.page ?? nextEventsPage);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "No se pudo cargar la historia clínica");
    } finally {
      setLoadingHistory(false);
    }
  }

  useEffect(() => {
    loadPatients(1).catch((ex) => setErr(ex instanceof Error ? ex.message : "No se pudieron cargar pacientes"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <>
      <section className="rounded-3xl bg-white dark:bg-slate-900 border border-cyan-100 dark:border-slate-800 p-6 shadow-xl shadow-cyan-950/10">
        <p className="text-sm uppercase tracking-[0.25em] text-[#0083B0] dark:text-lime-300 font-bold">Historias clínicas</p>
        <h2 className="text-3xl font-bold text-slate-900 dark:text-white">Revisión de pacientes</h2>
        <p className="text-slate-500 dark:text-slate-400 mt-1">
          Consulta pacientes y revisa sus eventos clínicos consolidados.
        </p>
      </section>

      {err && <div className="mt-4 p-3 rounded-lg bg-red-100 text-red-700 border border-red-200">{err}</div>}

      <section className="grid grid-cols-1 xl:grid-cols-[430px_minmax(0,1fr)] gap-6 mt-6">
        <aside className="rounded-2xl bg-white dark:bg-slate-900 border border-cyan-100 dark:border-slate-800 shadow-xl shadow-cyan-950/10 overflow-hidden h-fit">
          <div className="p-4 border-b border-cyan-100 dark:border-slate-800 bg-[#C6EB32] dark:bg-slate-900">
            <h3 className="font-bold text-lg text-[#005f80] dark:text-white">Pacientes</h3>
            <p className="text-xs text-[#005f80]/80 dark:text-slate-400 mt-1">Busca por nombre, ID, género, ciudad o estado.</p>
            <div className="mt-3 flex gap-2">
              <div className="relative flex-1">
                <span className="material-icons absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">search</span>
                <input
                  className="w-full pl-10 pr-3 py-2.5 rounded-lg border border-cyan-100 dark:border-slate-700 bg-white dark:bg-slate-950 focus:outline-none focus:ring-2 focus:ring-[#0083B0]"
                  value={patientQ}
                  onChange={(e) => setPatientQ(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") loadPatients(1);
                  }}
                  placeholder="Ej. Juan, F, Boston, 123"
                />
              </div>
              <button
                className="px-4 py-2.5 rounded-lg bg-[#0083B0] hover:bg-[#006a90] text-white font-bold transition disabled:opacity-60"
                disabled={loadingPatients}
                onClick={() => loadPatients(1)}
                type="button"
              >
                Buscar
              </button>
            </div>
          </div>

          <div className="p-3 flex items-center justify-between gap-2 text-sm text-slate-500 dark:text-slate-400">
            <span>{totalRows(patients).toLocaleString("es-PE")} pacientes</span>
            {patients?.max_result_window_exceeded && <span className="text-amber-700 dark:text-amber-300">Límite visual aplicado</span>}
          </div>

          <div className="max-h-[62vh] overflow-y-auto divide-y divide-cyan-50 dark:divide-slate-800">
            {loadingPatients && <div className="p-4 text-sm text-slate-500">Cargando pacientes...</div>}
            {!loadingPatients && patients?.rows.length === 0 && <div className="p-4 text-sm text-slate-500">No se encontraron pacientes.</div>}
            {patients?.rows.map((row) => {
              const patientId = getPatientId(row);
              const active = patientId === selectedPatientId;
              return (
                <button
                  key={`${row.id_paciente}-${row.id_paciente_fuente ?? ""}`}
                  className={[
                    "w-full text-left p-4 transition",
                    active ? "bg-cyan-50 dark:bg-slate-800" : "hover:bg-cyan-50/70 dark:hover:bg-slate-800/70",
                  ].join(" ")}
                  disabled={!patientId}
                  onClick={() => patientId && loadHistory(patientId, 1, eventQ)}
                  type="button"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="font-bold text-slate-900 dark:text-white truncate">{getText(row, "nombre_completo")}</p>
                      <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                        ID {getText(row, "id_paciente")} · Fuente {getText(row, "id_paciente_fuente")}
                      </p>
                    </div>
                    <span className="px-2 py-1 rounded-full bg-[#C6EB32]/45 text-[#005f80] text-xs font-bold whitespace-nowrap">
                      {getText(row, "edad_actual")} años
                    </span>
                  </div>
                  <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-600 dark:text-slate-300">
                    <span>Género: {getText(row, "genero_estandar")}</span>
                    <span>Ciudad: {getText(row, "ciudad")}</span>
                    <span>Dx: {getText(row, "total_diagnosticos")}</span>
                    <span>Último: {formatDate(row.fecha_ultimo_encuentro)}</span>
                  </div>
                </button>
              );
            })}
          </div>

          <div className="p-3 border-t border-cyan-100 dark:border-slate-800 flex items-center justify-between gap-2">
            <button
              className="px-3 py-2 rounded-lg bg-cyan-50 hover:bg-cyan-100 dark:bg-slate-800 dark:hover:bg-slate-700 disabled:opacity-40 font-semibold"
              disabled={!patients || patientPage <= 1 || loadingPatients}
              onClick={() => loadPatients(patientPage - 1)}
              type="button"
            >
              Anterior
            </button>
            <span className="text-sm text-slate-500 dark:text-slate-400">Página {patients?.page ?? 1} de {patients?.total_pages ?? 1}</span>
            <button
              className="px-3 py-2 rounded-lg bg-cyan-50 hover:bg-cyan-100 dark:bg-slate-800 dark:hover:bg-slate-700 disabled:opacity-40 font-semibold"
              disabled={!patients || patientPage >= (patients.total_pages ?? 1) || loadingPatients}
              onClick={() => loadPatients(patientPage + 1)}
              type="button"
            >
              Siguiente
            </button>
          </div>
        </aside>

        <section className="rounded-2xl bg-white dark:bg-slate-900 border border-cyan-100 dark:border-slate-800 shadow-xl shadow-cyan-950/10 overflow-hidden min-w-0">
          <div className="p-5 border-b border-cyan-100 dark:border-slate-800 flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-[0.25em] text-[#0083B0] dark:text-lime-300 font-bold">Paciente seleccionado</p>
              <h3 className="text-2xl font-bold text-slate-900 dark:text-white mt-1">{selectedPatientName}</h3>
              <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                {history?.patient ? `ID ${getText(history.patient, "id_paciente")} · ${getText(history.patient, "genero_estandar")} · ${getText(history.patient, "edad_actual")} años` : "Elige un paciente para ver el resumen y eventos."}
              </p>
            </div>
            {loadingHistory && <span className="px-3 py-1 rounded-full bg-cyan-50 dark:bg-slate-800 text-[#0083B0] dark:text-lime-300 text-xs font-bold">Cargando...</span>}
          </div>

          {!history ? (
            <div className="p-8 text-center text-slate-500 dark:text-slate-400">Selecciona un paciente de la lista para revisar su historia clínica.</div>
          ) : (
            <div className="p-5">
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
                {[
                  ["Nacimiento", formatDate(history.patient.fecha_nacimiento)],
                  ["Fallecido", getText(history.patient, "fallecido")],
                  ["Encuentros", getText(history.patient, "total_encuentros")],
                  ["Diagnósticos", getText(history.patient, "total_diagnosticos")],
                  ["Medicamentos", getText(history.patient, "total_medicamentos")],
                  ["Mediciones", getText(history.patient, "total_mediciones")],
                  ["Observaciones", getText(history.patient, "total_observaciones")],
                  ["Alergias", getText(history.patient, "total_alergias")],
                ].map(([label, value]) => (
                  <div key={label} className="rounded-xl border border-cyan-100 dark:border-slate-800 bg-cyan-50/50 dark:bg-slate-950 p-3">
                    <p className="text-xs text-slate-500 dark:text-slate-400 font-bold uppercase tracking-wide">{label}</p>
                    <p className="mt-1 font-extrabold text-slate-900 dark:text-white">{value}</p>
                  </div>
                ))}
              </div>

              <div className="mt-5 rounded-2xl border border-cyan-100 dark:border-slate-800 overflow-hidden">
                <div className="px-4 py-3 bg-[#0083B0] text-white flex items-center justify-between gap-3 flex-wrap">
                  <div>
                    <h4 className="font-bold">Datos generales</h4>
                    {history.patient_suppressed_columns?.length ? (
                      <p className="text-xs text-cyan-50">Columnas ocultas por perfil: {history.patient_suppressed_columns.join(", ")}</p>
                    ) : null}
                  </div>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-2 p-4 text-sm">
                  {Object.entries(history.patient).map(([key, value]) => (
                    <div key={key} className="grid grid-cols-[170px_minmax(0,1fr)] gap-3 border-b border-cyan-50 dark:border-slate-800 py-2">
                      <span className="font-bold text-slate-500 dark:text-slate-400 break-all">{key}</span>
                      <span className="text-slate-900 dark:text-slate-100 break-words">{isDateKey(key) ? formatDate(value) : formatValue(value)}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h4 className="font-bold text-xl text-slate-900 dark:text-white">Eventos clínicos</h4>
                  <p className="text-sm text-slate-500 dark:text-slate-400">
                    {totalRows(history.events).toLocaleString("es-PE")} eventos encontrados
                    {history.events.max_result_window_exceeded ? " · límite visual aplicado" : ""}
                  </p>
                </div>
                <div className="flex gap-2 min-w-0">
                  <input
                    className="px-3 py-2.5 rounded-lg border border-cyan-100 dark:border-slate-700 bg-white dark:bg-slate-950 focus:outline-none focus:ring-2 focus:ring-[#0083B0] min-w-0"
                    value={eventQ}
                    onChange={(e) => setEventQ(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && selectedPatientId) loadHistory(selectedPatientId, 1, eventQ);
                    }}
                    placeholder="Buscar en eventos"
                  />
                  <button
                    className="px-4 py-2.5 rounded-lg bg-[#0083B0] hover:bg-[#006a90] text-white font-bold transition disabled:opacity-60"
                    disabled={!selectedPatientId || loadingHistory}
                    onClick={() => selectedPatientId && loadHistory(selectedPatientId, 1, eventQ)}
                    type="button"
                  >
                    Filtrar
                  </button>
                </div>
              </div>

              {history.events.result_message && (
                <div className="mt-3 p-3 rounded-lg bg-amber-50 text-amber-700 border border-amber-200 text-sm">{history.events.result_message}</div>
              )}

              <div className="mt-4 rounded-2xl border border-cyan-100 dark:border-slate-800 overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm align-top">
                    <thead className="bg-[#0083B0] text-white text-left">
                      <tr>
                        <th className="p-3">Fecha</th>
                        <th className="p-3">Tipo</th>
                        <th className="p-3">Concepto</th>
                        <th className="p-3">Valor</th>
                        <th className="p-3">Detalle</th>
                        <th className="p-3">Profesional / centro</th>
                      </tr>
                    </thead>
                    <tbody>
                      {history.events.rows.length === 0 && (
                        <tr>
                          <td className="p-4 text-slate-500" colSpan={6}>No hay eventos para los filtros aplicados.</td>
                        </tr>
                      )}
                      {history.events.rows.map((event, index) => (
                        <tr key={`${event.tipo_evento}-${event.id_evento}-${index}`} className="border-t border-cyan-100 dark:border-slate-800">
                          <td className="p-3 whitespace-nowrap text-slate-600 dark:text-slate-300">{formatDate(event.fecha_evento)}</td>
                          <td className="p-3">
                            <span className="inline-flex rounded-full bg-[#C6EB32]/45 text-[#005f80] px-2.5 py-1 text-xs font-bold">
                              {getText(event, "tipo_evento")}
                            </span>
                          </td>
                          <td className="p-3 min-w-72">
                            <div className="font-bold text-slate-900 dark:text-white">{getText(event, "concepto_estandar")}</div>
                            <div className="text-xs text-slate-500 dark:text-slate-400">Fuente: {getText(event, "codigo_fuente")} · {getText(event, "concepto_fuente")}</div>
                          </td>
                          <td className="p-3 min-w-40">
                            <div>{getText(event, "valor_numerico")}</div>
                            <div className="text-xs text-slate-500 dark:text-slate-400">{getText(event, "valor_texto")} {getText(event, "unidad")}</div>
                          </td>
                          <td className="p-3 min-w-80 text-slate-700 dark:text-slate-300">{getText(event, "detalle_evento")}</td>
                          <td className="p-3 min-w-64">
                            <div className="font-semibold text-slate-900 dark:text-white">{getText(event, "nombre_profesional")}</div>
                            <div className="text-xs text-slate-500 dark:text-slate-400">{getText(event, "centro_atencion")}</div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="mt-4 flex items-center justify-end gap-2">
                <button
                  className="px-3 py-2 rounded-lg bg-cyan-50 hover:bg-cyan-100 dark:bg-slate-800 dark:hover:bg-slate-700 disabled:opacity-40 font-semibold"
                  disabled={eventsPage <= 1 || loadingHistory}
                  onClick={() => selectedPatientId && loadHistory(selectedPatientId, eventsPage - 1, eventQ)}
                  type="button"
                >
                  Anterior
                </button>
                <span className="px-2 py-1 text-sm text-slate-500 dark:text-slate-400">Página {history.events.page} de {history.events.total_pages ?? 1}</span>
                <button
                  className="px-3 py-2 rounded-lg bg-cyan-50 hover:bg-cyan-100 dark:bg-slate-800 dark:hover:bg-slate-700 disabled:opacity-40 font-semibold"
                  disabled={eventsPage >= (history.events.total_pages ?? 1) || loadingHistory}
                  onClick={() => selectedPatientId && loadHistory(selectedPatientId, eventsPage + 1, eventQ)}
                  type="button"
                >
                  Siguiente
                </button>
              </div>
            </div>
          )}
        </section>
      </section>
    </>
  );
}
