import { useEffect, useMemo, useRef, useState, type ChangeEvent, type KeyboardEvent } from "react";
import { Link } from "react-router-dom";
import { getAuthUser, hasPermission } from "../auth";
import {
  type QueryJob,
  type QueryResponse,
  type ReportData,
  type ReportMeta,
  downloadExport,
  getConversation,
  getQueryJob,
  getReportData,
  listActiveQueryJobs,
  selectConversationReport,
  sendFeedback,
  sendReportEmail,
  startQueryJob,
} from "../api";

const DEFAULT_PAGE_SIZE = 10;
const PAGE_SIZE_OPTIONS = [5, 10, 20, 50] as const;
const EMAIL_FORMATS = [
  { value: "csv", label: "CSV" },
  { value: "xlsx", label: "Excel" },
  { value: "pdf", label: "PDF" },
] as const;

type ExportFormat = "csv" | "xlsx" | "pdf";
type PageItem = number | "left-ellipsis" | "right-ellipsis";

type PendingJobSnapshot = {
  job_id: string;
  conversation_id: string;
  nl: string;
  started_at: string;
};

type DashboardSnapshot = {
  active_conv_id: string | null;
  active_report_id: string | null;
  selected_report_id: string | null;
};

const DASHBOARD_STATE_KEY = "empresa_reports_dashboard_state_v2";
const PENDING_JOB_KEY = "empresa_reports_pending_query_job_v2";

function readJson<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    localStorage.removeItem(key);
    return null;
  }
}

function saveDashboardSnapshot(snapshot: DashboardSnapshot) {
  if (!snapshot.active_conv_id && !snapshot.active_report_id && !snapshot.selected_report_id) {
    localStorage.removeItem(DASHBOARD_STATE_KEY);
    return;
  }
  localStorage.setItem(DASHBOARD_STATE_KEY, JSON.stringify(snapshot));
}

function readDashboardSnapshot(): DashboardSnapshot | null {
  return readJson<DashboardSnapshot>(DASHBOARD_STATE_KEY);
}

function savePendingJob(job: PendingJobSnapshot) {
  localStorage.setItem(PENDING_JOB_KEY, JSON.stringify(job));
}

function readPendingJob(): PendingJobSnapshot | null {
  return readJson<PendingJobSnapshot>(PENDING_JOB_KEY);
}

function clearPendingJob() {
  localStorage.removeItem(PENDING_JOB_KEY);
}

function responseToReportData(res: QueryResponse): ReportData {
  return {
    columns: res.columns,
    rows: res.rows,
    page: res.page,
    page_size: res.page_size,
    row_count: res.row_count,
    total_count: res.total_count ?? null,
    display_total_count: res.display_total_count ?? null,
    total_pages: res.total_pages ?? null,
    max_result_window: res.max_result_window ?? null,
    max_result_window_exceeded: res.max_result_window_exceeded ?? false,
    result_message: res.result_message ?? null,
    suppressed_columns: res.suppressed_columns ?? [],
  };
}

function getPaginationItems(currentPage: number, totalPages?: number | null): PageItem[] {
  if (!totalPages || totalPages <= 1) return [currentPage];
  if (totalPages <= 7) return Array.from({ length: totalPages }, (_, i) => i + 1);

  const items: PageItem[] = [1];
  const start = Math.max(2, currentPage - 1);
  const end = Math.min(totalPages - 1, currentPage + 1);

  if (start > 2) items.push("left-ellipsis");
  for (let page = start; page <= end; page += 1) items.push(page);
  if (end < totalPages - 1) items.push("right-ellipsis");
  items.push(totalPages);
  return items;
}

function ChatLoader({ label = "Procesando reporte" }: { label?: string }) {
  return (
    <div className="rounded-2xl border border-lime-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm p-5">
      <div className="flex items-center justify-between gap-4 mb-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-2xl bg-[#C6EB32] text-[#005f80] flex items-center justify-center">
            <span className="material-icons">hourglass_top</span>
          </div>
          <div>
            <div className="text-sm font-bold text-slate-800 dark:text-slate-100">{label}</div>
            <div className="text-xs text-slate-500 dark:text-slate-400">Preparando resultados...</div>
          </div>
        </div>
        <div className="flex items-center gap-1 text-lime-700 dark:text-slate-300">
          <span className="chat-loader-dot" />
          <span className="chat-loader-dot" />
          <span className="chat-loader-dot" />
        </div>
      </div>
      <div className="space-y-2">
        <div className="chat-loader-line w-full" />
        <div className="chat-loader-line w-4/5" />
        <div className="chat-loader-line w-2/3" />
      </div>
    </div>
  );
}

function formatCell(value: unknown) {
  if (value === null || value === undefined) return "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function formatDate(value: string | null | undefined) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("es-PE");
}

function reportRowCount(data: ReportData | null) {
  if (!data) return "-";
  return (data.total_count ?? data.display_total_count ?? data.row_count).toLocaleString("es-PE");
}

export default function Dashboard() {
  const authUser = getAuthUser();
  const [rightOpen, setRightOpen] = useState(false);
  const [reports, setReports] = useState<ReportMeta[]>([]);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [activeReportId, setActiveReportId] = useState<string | null>(null);
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null);
  const [tablesById, setTablesById] = useState<Record<string, ReportData | null>>({});
  const [pagesById, setPagesById] = useState<Record<string, number>>({});
  const [pageSizesById, setPageSizesById] = useState<Record<string, number>>({});
  const [nl, setNl] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingLabel, setLoadingLabel] = useState("Procesando reporte");
  const [err, setErr] = useState<string | null>(null);
  const [emailOpen, setEmailOpen] = useState(false);
  const [emailFormats, setEmailFormats] = useState<ExportFormat[]>(["xlsx"]);
  const [emailLoading, setEmailLoading] = useState(false);
  const [emailErr, setEmailErr] = useState<string | null>(null);
  const [emailMsg, setEmailMsg] = useState<string | null>(null);
  const [pendingJob, setPendingJob] = useState<PendingJobSnapshot | null>(() => readPendingJob());
  const viewRequestRef = useRef(0);
  const pollTimeoutRef = useRef<ReturnType<typeof window.setTimeout> | null>(null);

  const canExport = hasPermission("can_export");
  const exportReportId = selectedReportId || activeReportId;
  const activeReport = activeReportId ? reports.find((r) => r.report_id === activeReportId) ?? null : null;
  const exportReport = exportReportId ? reports.find((r) => r.report_id === exportReportId) ?? activeReport : null;
  const exportReportText = exportReport?.nl ?? null;
  const activeTable = activeReportId ? tablesById[activeReportId] ?? null : null;
  const activePage = activeReportId ? pagesById[activeReportId] ?? 1 : 1;
  const activePageSize = activeReportId ? pageSizesById[activeReportId] ?? DEFAULT_PAGE_SIZE : DEFAULT_PAGE_SIZE;
  const fb = activeReport?.feedback ?? null;

  const currentColumns = useMemo(() => activeTable?.columns ?? [], [activeTable?.columns]);

  const closeMenus = () => {
    setRightOpen(false);
  };

  const getReportPageSize = (reportId: string) => pageSizesById[reportId] ?? DEFAULT_PAGE_SIZE;

  useEffect(() => {
    saveDashboardSnapshot({
      active_conv_id: activeConvId,
      active_report_id: activeReportId,
      selected_report_id: selectedReportId,
    });
  }, [activeConvId, activeReportId, selectedReportId]);

  useEffect(() => {
    let cancelled = false;

    async function boot() {
      const snapshot = readDashboardSnapshot();
      const storedPending = readPendingJob();

      if (storedPending) {
        setPendingJob(storedPending);
        setActiveConvId(storedPending.conversation_id);
        setLoadingLabel("Generando reporte");
        setLoading(true);
        return;
      }

      try {
        const activeJobs = await listActiveQueryJobs();
        if (cancelled) return;
        if (activeJobs.length > 0) {
          const job = activeJobs[0];
          const pending = {
            job_id: job.job_id,
            conversation_id: job.conversation_id,
            nl: job.nl,
            started_at: job.created_at,
          };
          savePendingJob(pending);
          setPendingJob(pending);
          setActiveConvId(job.conversation_id);
          setLoadingLabel("Generando reporte");
          setLoading(true);
          return;
        }
      } catch {
        // La recuperación de trabajos no debe bloquear el módulo de consultas.
      }

      if (snapshot?.active_conv_id && !cancelled) {
        await openConversation(snapshot.active_conv_id, {
          preferReportId: snapshot.active_report_id || snapshot.selected_report_id,
        });
      }
    }

    boot();

    return () => {
      cancelled = true;
      if (pollTimeoutRef.current) window.clearTimeout(pollTimeoutRef.current);
    };
  }, []);

  async function openConversation(conversationId: string, options: { preferReportId?: string | null } = {}) {
    const requestId = ++viewRequestRef.current;
    setErr(null);
    setLoadingLabel("Cargando reporte");
    setLoading(true);

    try {
      const detail = await getConversation(conversationId);
      if (requestId !== viewRequestRef.current) return;

      setActiveConvId(detail.conversation.conversation_id);
      setReports(detail.reports);
      setSelectedReportId(detail.conversation.selected_report_id);

      const last = detail.reports.length ? detail.reports[detail.reports.length - 1].report_id : null;
      const preferred = options.preferReportId && detail.reports.some((r) => r.report_id === options.preferReportId)
        ? options.preferReportId
        : null;
      const toShow = preferred || detail.conversation.selected_report_id || last;
      setActiveReportId(toShow);

      if (!toShow) {
        setTablesById({});
        setPagesById({});
        setPageSizesById({});
        return;
      }

      const size = getReportPageSize(toShow);
      const data = await getReportData(toShow, 1, size);
      if (requestId !== viewRequestRef.current) return;

      setTablesById({ [toShow]: data });
      setPagesById({ [toShow]: 1 });
      setPageSizesById({ [toShow]: size });
      closeMenus();
    } catch (ex) {
      if (requestId === viewRequestRef.current) {
        setErr(ex instanceof Error ? ex.message : "Error al cargar reporte");
      }
    } finally {
      if (requestId === viewRequestRef.current) setLoading(false);
    }
  }

  async function finishCompletedJob(job: QueryJob) {
    clearPendingJob();
    setPendingJob(null);

    const result = job.result;
    if (!result) {
      await openConversation(job.conversation_id, { preferReportId: job.report_id });
      return;
    }

    await selectConversationReport(result.conversation_id, result.report_id).catch(() => undefined);
    const detail = await getConversation(result.conversation_id);

    setActiveConvId(detail.conversation.conversation_id);
    setReports(detail.reports);
    setSelectedReportId(detail.conversation.selected_report_id || result.report_id);
    setActiveReportId(result.report_id);

    const firstPageData = responseToReportData(result);
    setTablesById({ [result.report_id]: firstPageData });
    setPagesById({ [result.report_id]: firstPageData.page ?? 1 });
    setPageSizesById({ [result.report_id]: result.page_size || DEFAULT_PAGE_SIZE });
    setNl("");
    setLoading(false);
    setLoadingLabel("Procesando reporte");
  }

  async function handleJobUpdate(job: QueryJob) {
    if (job.status === "completed") {
      await finishCompletedJob(job);
      return;
    }

    if (job.status === "failed" || job.status === "abandoned") {
      clearPendingJob();
      setPendingJob(null);
      setLoading(false);
      setErr(job.error || "No se pudo generar el reporte");
      return;
    }

    setLoadingLabel(job.status === "queued" ? "Reporte en cola" : "Generando reporte");
    setLoading(true);
  }

  useEffect(() => {
    if (!pendingJob) return;
    const currentPendingJob = pendingJob;
    let cancelled = false;

    async function checkJob() {
      try {
        const job = await getQueryJob(currentPendingJob.job_id);
        if (cancelled) return;
        await handleJobUpdate(job);
      } catch (ex) {
        if (cancelled) return;
        const message = ex instanceof Error ? ex.message : "No se pudo recuperar el estado del reporte";
        if (message.includes("Trabajo no existe")) {
          clearPendingJob();
          setPendingJob(null);
          setLoading(false);
        } else {
          setErr(message);
        }
      } finally {
        if (!cancelled && readPendingJob()?.job_id === currentPendingJob.job_id) {
          pollTimeoutRef.current = window.setTimeout(checkJob, document.hidden ? 6000 : 2000);
        }
      }
    }

    function onVisibilityChange() {
      if (!document.hidden) {
        if (pollTimeoutRef.current) window.clearTimeout(pollTimeoutRef.current);
        checkJob();
      }
    }

    setLoadingLabel("Generando reporte");
    setLoading(true);
    checkJob();
    document.addEventListener("visibilitychange", onVisibilityChange);

    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", onVisibilityChange);
      if (pollTimeoutRef.current) window.clearTimeout(pollTimeoutRef.current);
    };
  }, [pendingJob]);

  async function doQuery() {
    const text = nl.trim();
    if (!text || loading) return;

    setErr(null);
    setLoadingLabel("Generando reporte");
    setLoading(true);

    try {
      const size = activeReportId ? getReportPageSize(activeReportId) : DEFAULT_PAGE_SIZE;
      const job = await startQueryJob(text, activeConvId, 1, size);
      const pending = {
        job_id: job.job_id,
        conversation_id: job.conversation_id,
        nl: text,
        started_at: new Date().toISOString(),
      };

      savePendingJob(pending);
      setPendingJob(pending);
      setActiveConvId(job.conversation_id);
      setNl("");
    } catch (ex) {
      clearPendingJob();
      setPendingJob(null);
      setErr(ex instanceof Error ? ex.message : "Error al iniciar el reporte");
      setLoading(false);
    }
  }

  function newReport() {
    if (pendingJob) {
      setErr("Hay un reporte generándose. Cuando termine podrás iniciar uno nuevo sin perder el resultado.");
      closeMenus();
      return;
    }

    viewRequestRef.current += 1;
    setErr(null);
    setActiveConvId(null);
    setReports([]);
    setActiveReportId(null);
    setSelectedReportId(null);
    setTablesById({});
    setPagesById({});
    setPageSizesById({});
    setNl("");
    closeMenus();
  }

  async function feedback(reportId: string, value: "up" | "down") {
    try {
      await sendFeedback(reportId, value);
      setReports((prev) =>
        prev.map((r) =>
          r.report_id === reportId ? { ...r, feedback: value === "up" ? "positive" : "negative" } : r
        )
      );
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Error al guardar feedback");
    }
  }

  async function changePage(reportId: string, next: number) {
    setLoadingLabel("Cargando página");
    setLoading(true);

    try {
      const size = getReportPageSize(reportId);
      const data = await getReportData(reportId, next, size);
      setTablesById((prev) => ({ ...prev, [reportId]: data }));
      setPagesById((prev) => ({ ...prev, [reportId]: next }));
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Error al cambiar de página");
    } finally {
      setLoading(false);
    }
  }

  async function changePageSize(reportId: string, size: number) {
    setPageSizesById((prev) => ({ ...prev, [reportId]: size }));
    setLoadingLabel("Actualizando filas");
    setLoading(true);

    try {
      const data = await getReportData(reportId, 1, size);
      setTablesById((prev) => ({ ...prev, [reportId]: data }));
      setPagesById((prev) => ({ ...prev, [reportId]: 1 }));
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Error al cambiar cantidad de filas");
    } finally {
      setLoading(false);
    }
  }

  async function doDownload(format: ExportFormat) {
    if (!exportReportId) return;
    try {
      await downloadExport(exportReportId, format);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "No se pudo exportar el reporte");
    }
  }

  function openEmailModal() {
    setEmailErr(null);
    setEmailMsg(null);
    if (!canExport || !exportReportId) return;
    setEmailOpen(true);
  }

  function toggleEmailFormat(fmt: ExportFormat) {
    setEmailFormats((prev) => (prev.includes(fmt) ? prev.filter((x) => x !== fmt) : [...prev, fmt]));
  }

  async function doSendEmail() {
    if (!canExport || !exportReportId || emailLoading) return;
    setEmailErr(null);
    setEmailMsg(null);

    if (!emailFormats.length) {
      setEmailErr("Selecciona al menos un formato.");
      return;
    }

    setEmailLoading(true);
    try {
      const res = await sendReportEmail(exportReportId, emailFormats);
      setEmailMsg(`Correo enviado a ${res.to}.`);
    } catch (ex) {
      setEmailErr(ex instanceof Error ? ex.message : "No se pudo enviar el correo");
    } finally {
      setEmailLoading(false);
    }
  }

  return (
    <div className="h-full min-h-0 bg-gray-100 dark:bg-slate-950 overflow-hidden">
      <div className={`fixed inset-0 bg-black/50 z-30 transition-opacity lg:hidden ${rightOpen ? "" : "hidden"}`} onClick={closeMenus} />

      {canExport && emailOpen && (
        <div className="fixed inset-0 z-[60] bg-slate-950/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="w-full max-w-lg rounded-3xl bg-white dark:bg-slate-900 border border-lime-200 dark:border-slate-800 shadow-2xl overflow-hidden">
            <div className="px-6 py-5 bg-[#0083B0] text-white flex items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <span className="material-icons">outgoing_mail</span>
                <div>
                  <h3 className="font-bold text-xl">Enviar reporte por correo</h3>
                  <p className="text-cyan-50 text-sm">Se enviará al correo vinculado a tu usuario.</p>
                </div>
              </div>
              <button className="w-10 h-10 rounded-full hover:bg-white/15 transition flex items-center justify-center" type="button" onClick={() => setEmailOpen(false)}>
                <span className="material-icons">close</span>
              </button>
            </div>

            <div className="p-6 space-y-4">
              <div>
                <div className="text-xs font-bold uppercase tracking-[0.2em] text-[#0083B0] dark:text-lime-300 mb-1">Destino</div>
                <div className="rounded-xl border border-cyan-100 dark:border-slate-800 bg-cyan-50/60 dark:bg-slate-950 px-3 py-2 text-sm text-slate-700 dark:text-slate-200">
                  {authUser?.email ? authUser.email : "Tu usuario no tiene correo configurado"}
                </div>
              </div>

              <div>
                <div className="text-xs font-bold uppercase tracking-[0.2em] text-[#0083B0] dark:text-lime-300 mb-1">Reporte</div>
                <div className="rounded-xl border border-cyan-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 px-3 py-2 text-sm text-slate-700 dark:text-slate-200 line-clamp-3">
                  {exportReportText || "Ninguno seleccionado"}
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between gap-2 mb-2">
                  <div className="text-xs font-bold uppercase tracking-[0.2em] text-[#0083B0] dark:text-lime-300">Formatos</div>
                  <button
                    type="button"
                    className="text-xs font-bold text-[#0083B0] dark:text-lime-300 hover:underline"
                    onClick={() => setEmailFormats(emailFormats.length === 3 ? [] : ["csv", "xlsx", "pdf"])}
                  >
                    {emailFormats.length === 3 ? "Quitar todos" : "Marcar todos"}
                  </button>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                  {EMAIL_FORMATS.map((fmt) => {
                    const active = emailFormats.includes(fmt.value);
                    return (
                      <button
                        key={fmt.value}
                        type="button"
                        onClick={() => toggleEmailFormat(fmt.value)}
                        className={[
                          "rounded-xl border px-4 py-3 flex items-center justify-center gap-2 font-bold transition",
                          active
                            ? "bg-[#C6EB32] border-lime-300 text-[#005f80]"
                            : "bg-white dark:bg-slate-950 border-cyan-100 dark:border-slate-800 text-slate-600 dark:text-slate-300 hover:bg-cyan-50 dark:hover:bg-slate-800",
                        ].join(" ")}
                      >
                        <span className="material-icons text-[20px]">{active ? "check_circle" : "radio_button_unchecked"}</span>
                        {fmt.label}
                      </button>
                    );
                  })}
                </div>
              </div>

              {emailErr && <div className="rounded-xl bg-red-100 border border-red-200 text-red-700 p-3 text-sm">{emailErr}</div>}
              {emailMsg && <div className="rounded-xl bg-lime-100 border border-lime-200 text-lime-800 p-3 text-sm">{emailMsg}</div>}

              <p className="text-xs text-slate-500 dark:text-slate-400">
                Se respetan los mismos permisos de exportación y columnas ocultas del perfil.
              </p>
            </div>

            <div className="px-6 py-4 bg-slate-50 dark:bg-slate-950 flex justify-end gap-2">
              <button className="px-4 py-2.5 rounded-lg bg-white dark:bg-slate-800 border border-cyan-100 dark:border-slate-700 font-bold" type="button" onClick={() => setEmailOpen(false)}>
                Cerrar
              </button>
              <button
                className="px-5 py-2.5 rounded-lg bg-[#C6EB32] hover:bg-lime-300 text-[#005f80] font-bold transition disabled:opacity-60"
                type="button"
                disabled={emailLoading || !exportReportId || !emailFormats.length}
                onClick={doSendEmail}
              >
                {emailLoading ? "Enviando..." : "Enviar correo"}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="flex h-full min-h-0">
        <main className="flex-1 flex flex-col h-full min-w-0 min-h-0">
          <header className="shrink-0 bg-white dark:bg-slate-900 dark:text-slate-50 shadow-sm border-b border-cyan-100 dark:border-slate-800 px-4 lg:px-6 py-4 flex flex-wrap justify-between items-center gap-3 z-10">
            <div>
              <p className="text-xs uppercase tracking-[0.25em] text-[#0083B0] dark:text-lime-300 font-bold">Módulo de consultas</p>
              <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Generar reporte</h1>
              <p className="text-sm text-slate-500 dark:text-slate-400">El historial se consulta en su módulo independiente.</p>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={newReport}
                disabled={loading && !!pendingJob}
                className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-[#0083B0] hover:bg-[#006a90] text-white font-bold transition disabled:opacity-60"
                type="button"
              >
                <span className="material-icons text-[18px]">add</span>
                Nuevo reporte
              </button>
              <Link
                to="/historial-reportes"
                className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-white dark:bg-slate-800 border border-cyan-100 dark:border-slate-700 text-[#005f80] dark:text-lime-300 font-bold transition hover:bg-cyan-50 dark:hover:bg-slate-700"
              >
                <span className="material-icons text-[18px]">history</span>
                Historial
              </Link>
              {canExport && (
                <button
                  className="lg:hidden inline-flex items-center justify-center w-10 h-10 rounded-lg bg-lime-100 text-lime-800 dark:bg-slate-800 dark:text-slate-200"
                  onClick={() => setRightOpen(true)}
                  title="Exportar"
                  type="button"
                >
                  <span className="material-icons">file_download</span>
                </button>
              )}
            </div>
          </header>

          <div className="flex-1 p-4 lg:p-6 pb-10 flex overflow-hidden min-h-0">
            <div className="flex-1 flex flex-col lg:mr-6 min-h-0 min-w-0">
              <div className="flex-1 overflow-y-auto min-h-0 scrollbar-subtle pr-0 lg:pr-1">
                {err && (
                  <div className="mb-4 rounded-xl bg-red-100 border border-red-200 text-red-700 p-3 text-sm">{err}</div>
                )}

                {activeReport ? (
                  <article className="rounded-3xl bg-white dark:bg-slate-900 border border-cyan-100 dark:border-slate-800 shadow-xl shadow-cyan-950/10 overflow-hidden">
                    <div className="bg-[#0083B0] text-white p-6 lg:p-8 relative overflow-hidden">
                      <div className="absolute -right-14 -top-14 w-40 h-40 rounded-full bg-white/10" />
                      <div className="absolute right-10 bottom-4 w-20 h-20 rounded-full bg-[#C6EB32]/20" />
                      <div className="relative flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
                        <div className="min-w-0">
                          <p className="text-xs uppercase tracking-[0.25em] text-cyan-50 font-bold">Reporte generado</p>
                          <h2 className="text-2xl lg:text-3xl font-bold mt-2 leading-tight">{activeReport.nl}</h2>
                          <p className="text-sm text-cyan-50 mt-3">Generado: {formatDate(activeReport.timestamp)}</p>
                        </div>
                        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 shrink-0">
                          <div className="rounded-2xl bg-white/15 px-4 py-3">
                            <div className="text-[11px] uppercase tracking-wide text-cyan-50">Filas</div>
                            <div className="font-bold text-xl">{reportRowCount(activeTable)}</div>
                          </div>
                          <div className="rounded-2xl bg-white/15 px-4 py-3">
                            <div className="text-[11px] uppercase tracking-wide text-cyan-50">Columnas</div>
                            <div className="font-bold text-xl">{currentColumns.length}</div>
                          </div>
                          <div className="rounded-2xl bg-white/15 px-4 py-3 col-span-2 sm:col-span-1">
                            <div className="text-[11px] uppercase tracking-wide text-cyan-50">Latencia</div>
                            <div className="font-bold text-xl">{activeReport.latency_ms} ms</div>
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="p-5 lg:p-6 space-y-5">
                      {activeTable?.result_message && (
                        <div className="rounded-xl bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 text-amber-800 dark:text-amber-200 px-4 py-3 text-sm">
                          {activeTable.result_message}
                        </div>
                      )}

                      {!!activeTable?.suppressed_columns?.length && (
                        <div className="rounded-xl bg-cyan-50 dark:bg-slate-800 border border-cyan-100 dark:border-slate-700 text-cyan-800 dark:text-slate-200 px-4 py-3 text-xs">
                          Columnas ocultas por tu perfil: {activeTable.suppressed_columns.join(", ")}
                        </div>
                      )}

                      {activeReport.sql && (
                        <details className="rounded-2xl border border-cyan-100 dark:border-slate-800 bg-cyan-50/40 dark:bg-slate-950 overflow-hidden">
                          <summary className="cursor-pointer px-4 py-3 font-bold text-[#005f80] dark:text-lime-300 flex items-center gap-2">
                            <span className="material-icons text-[18px]">code</span>
                            Ver SQL generado
                          </summary>
                          <pre className="mx-4 mb-4 whitespace-pre-wrap text-xs bg-white dark:bg-slate-900 rounded-xl p-4 overflow-auto border border-cyan-100 dark:border-slate-800 max-h-60">
                            {activeReport.sql}
                          </pre>
                        </details>
                      )}

                      <section className="rounded-2xl border border-cyan-100 dark:border-slate-800 overflow-hidden">
                        <div className="px-4 py-3 bg-slate-50 dark:bg-slate-950 border-b border-cyan-100 dark:border-slate-800 flex flex-wrap items-center justify-between gap-3">
                          <div>
                            <h3 className="font-bold text-slate-900 dark:text-white flex items-center gap-2">
                              <span className="material-icons text-[#0083B0] dark:text-lime-300">table_chart</span>
                              Datos del reporte
                            </h3>
                            <p className="text-xs text-slate-500 dark:text-slate-400">
                              Página {activePage}{activeTable?.total_pages ? ` de ${activeTable.total_pages}` : ""}
                            </p>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="text-sm text-slate-600 dark:text-slate-300">Mostrar</span>
                            <select
                              className="border rounded-lg px-2 py-1.5 outline-none dark:bg-slate-800 dark:border-slate-700"
                              value={activePageSize}
                              onChange={(e: ChangeEvent<HTMLSelectElement>) => activeReportId && changePageSize(activeReportId, Number(e.target.value))}
                              disabled={loading || !activeReportId}
                              title="Filas por página"
                            >
                              {PAGE_SIZE_OPTIONS.map((n) => (
                                <option key={n} value={n}>
                                  {n}
                                </option>
                              ))}
                            </select>
                          </div>
                        </div>

                        <div className="overflow-x-auto w-full">
                          <table className="w-full text-sm text-left text-slate-600 dark:text-slate-200 whitespace-nowrap">
                            <thead className="text-xs uppercase bg-[#C6EB32] text-[#005f80]">
                              <tr>
                                {currentColumns.length ? currentColumns.map((col) => (
                                  <th key={col} className="px-4 py-3 font-bold">{col}</th>
                                )) : <th className="px-4 py-3">Sin columnas</th>}
                              </tr>
                            </thead>
                            <tbody>
                              {activeTable?.rows.length ? activeTable.rows.map((row, rowIndex) => (
                                <tr key={`${activeReport.report_id}-${activePage}-${rowIndex}`} className="border-t border-cyan-100 dark:border-slate-800 odd:bg-white even:bg-slate-50 dark:odd:bg-slate-900 dark:even:bg-slate-950">
                                  {currentColumns.map((col) => (
                                    <td key={col} className="px-4 py-3 align-top max-w-[28rem] truncate" title={formatCell(row[col])}>
                                      {formatCell(row[col])}
                                    </td>
                                  ))}
                                </tr>
                              )) : (
                                <tr>
                                  <td className="px-4 py-6 text-center text-slate-500" colSpan={Math.max(currentColumns.length, 1)}>
                                    {activeTable ? "La consulta no devolvió filas." : "Cargando datos del reporte..."}
                                  </td>
                                </tr>
                              )}
                            </tbody>
                          </table>
                        </div>

                        <div className="bg-slate-50 dark:bg-slate-950 px-4 py-3 border-t border-cyan-100 dark:border-slate-800 flex flex-wrap items-center justify-between gap-4">
                          <div className="text-xs text-slate-500 dark:text-slate-400">
                            Mostrando {activeTable?.row_count ?? 0} filas en esta página.
                          </div>
                          <div className="flex items-center gap-1">
                            <button
                              className="p-2 rounded-lg text-slate-500 hover:text-lime-700 hover:bg-lime-100 dark:text-slate-400 dark:hover:text-white dark:hover:bg-slate-800 disabled:opacity-40"
                              disabled={!activeTable || activePage <= 1 || loading || !activeReportId}
                              onClick={() => activeReportId && changePage(activeReportId, activePage - 1)}
                              type="button"
                              title="Página anterior"
                            >
                              <span className="material-icons">chevron_left</span>
                            </button>
                            {getPaginationItems(activePage, activeTable?.total_pages).map((item) =>
                              typeof item === "number" ? (
                                <button
                                  key={item}
                                  type="button"
                                  onClick={() => activeReportId && changePage(activeReportId, item)}
                                  disabled={!activeTable || loading || item === activePage || !activeReportId}
                                  aria-current={item === activePage ? "page" : undefined}
                                  className={[
                                    "min-w-9 h-9 px-3 rounded-lg text-sm font-semibold transition-colors",
                                    item === activePage
                                      ? "bg-lime-700 text-white dark:bg-slate-700"
                                      : "bg-white text-lime-800 hover:bg-lime-100 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800",
                                    "disabled:opacity-100",
                                  ].join(" ")}
                                >
                                  {item}
                                </button>
                              ) : (
                                <span key={item} className="min-w-9 h-9 px-2 flex items-center justify-center text-lime-800 dark:text-slate-300 font-bold">...</span>
                              )
                            )}
                            <button
                              className="p-2 rounded-lg text-lime-700 hover:text-lime-900 hover:bg-lime-100 dark:text-slate-300 dark:hover:text-white dark:hover:bg-slate-800 disabled:opacity-40"
                              disabled={!activeTable || loading || !activeReportId || (activeTable.total_pages ? activePage >= activeTable.total_pages : activeTable.row_count < activeTable.page_size)}
                              onClick={() => activeReportId && changePage(activeReportId, activePage + 1)}
                              type="button"
                              title="Página siguiente"
                            >
                              <span className="material-icons">chevron_right</span>
                            </button>
                          </div>
                        </div>
                      </section>

                      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-lime-50 dark:bg-slate-950 border border-lime-100 dark:border-slate-800 px-4 py-3">
                        <div className="text-sm text-slate-600 dark:text-slate-300">
                          Marca si este reporte fue útil para mejorar el seguimiento de calidad.
                        </div>
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => feedback(activeReport.report_id, "up")}
                            className={[
                              "rounded-full p-2 transition-colors border",
                              fb === "positive"
                                ? "bg-lime-700 text-white border-lime-700 shadow-sm"
                                : "text-lime-700 border-lime-300 hover:bg-lime-100 dark:text-slate-300 dark:border-slate-700 dark:hover:bg-slate-700",
                            ].join(" ")}
                            aria-label="Me gusta"
                            title="Útil"
                            type="button"
                          >
                            <span className="material-icons">thumb_up</span>
                          </button>
                          <button
                            onClick={() => feedback(activeReport.report_id, "down")}
                            className={[
                              "rounded-full p-2 transition-colors border",
                              fb === "negative"
                                ? "bg-red-600 text-white border-red-600 shadow-sm"
                                : "text-slate-500 border-slate-300 hover:bg-slate-100 dark:text-slate-300 dark:border-slate-700 dark:hover:bg-slate-700",
                            ].join(" ")}
                            aria-label="No me gusta"
                            title="No útil"
                            type="button"
                          >
                            <span className="material-icons">thumb_down</span>
                          </button>
                        </div>
                      </div>
                    </div>
                  </article>
                ) : !loading ? (
                  <section className="rounded-3xl bg-white dark:bg-slate-900 border border-cyan-100 dark:border-slate-800 p-8 shadow-xl shadow-cyan-950/10 text-center">
                    <div className="mx-auto w-16 h-16 rounded-3xl bg-[#C6EB32] text-[#005f80] flex items-center justify-center mb-4">
                      <span className="material-icons text-4xl">assignment</span>
                    </div>
                    <h2 className="text-2xl font-bold text-slate-900 dark:text-white">Nuevo reporte clínico</h2>
                    <p className="mt-2 text-slate-500 dark:text-slate-400 max-w-xl mx-auto">
                      Escribe una consulta en lenguaje natural. El resultado se presentará como reporte organizado; los reportes anteriores están disponibles en el módulo Historial.
                    </p>
                  </section>
                ) : null}

                {loading && <ChatLoader label={loadingLabel} />}
              </div>

              <div className="bg-lime-200 dark:bg-slate-800 p-4 mt-4 rounded-2xl flex items-center justify-between shadow-sm border border-lime-300 dark:border-slate-700">
                <input
                  className="text-lg bg-transparent outline-none flex-1 text-lime-950 dark:text-slate-100 placeholder:text-lime-800/70 dark:placeholder:text-slate-400 disabled:opacity-60"
                  placeholder={loading ? "Procesando consulta..." : "Escribe una consulta para generar un reporte"}
                  value={nl}
                  disabled={loading}
                  onChange={(e: ChangeEvent<HTMLInputElement>) => setNl(e.target.value)}
                  onKeyDown={(e: KeyboardEvent<HTMLInputElement>) => {
                    if (e.key === "Enter" && !loading && nl.trim()) doQuery();
                  }}
                />
                <button
                  className="bg-lime-700 hover:bg-lime-800 dark:bg-slate-700 dark:hover:bg-slate-600 transition-colors p-2 rounded-full ml-4 flex items-center justify-center disabled:opacity-70"
                  onClick={doQuery}
                  disabled={loading || !nl.trim()}
                  type="button"
                >
                  <span className="material-icons text-white">{loading ? "hourglass_top" : "send"}</span>
                </button>
              </div>
            </div>

            {canExport && (
              <aside
                className={[
                  "w-80 bg-lime-300 dark:bg-slate-900 p-6 flex flex-col fixed inset-y-0 right-0 z-40 transform transition-transform duration-300",
                  "lg:relative lg:translate-x-0 lg:rounded-2xl overflow-y-auto shrink-0 scrollbar-subtle border border-lime-200 dark:border-slate-800",
                  rightOpen ? "translate-x-0" : "translate-x-full",
                ].join(" ")}
              >
                <div className="flex justify-between items-center mb-6">
                  <h2 className="text-xl font-bold text-lime-800 dark:text-slate-100">Acciones del reporte</h2>
                  <button className="lg:hidden text-lime-800 dark:text-slate-200 hover:text-lime-900 dark:hover:text-white" onClick={closeMenus} type="button">
                    <span className="material-icons">close</span>
                  </button>
                </div>

                <div className="mb-4">
                  <div className="text-xs font-semibold text-lime-800 dark:text-slate-300 mb-1">Reporte actual</div>
                  <div className="text-sm text-lime-900 dark:text-slate-100 bg-lime-200/60 dark:bg-slate-800/70 rounded-xl p-3 line-clamp-5">
                    {exportReportText ? exportReportText : "Ninguno seleccionado"}
                  </div>
                </div>

                <div className="space-y-4">
                  <div className="font-semibold text-lime-800 dark:text-slate-200">Exportar</div>
                  {EMAIL_FORMATS.map((fmt) => (
                    <button
                      key={fmt.value}
                      className="w-full flex justify-between items-center py-2 border-b border-lime-400 dark:border-slate-700 hover:bg-lime-400/30 dark:hover:bg-slate-800 px-2 rounded transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
                      onClick={() => doDownload(fmt.value)}
                      title={exportReportId ? `Exportar ${fmt.label}` : "Selecciona un reporte"}
                      disabled={!exportReportId}
                      type="button"
                    >
                      <span className="text-lime-800 dark:text-slate-200">{fmt.label}</span>
                      <span className="text-lime-800 dark:text-slate-200 material-icons">file_download</span>
                    </button>
                  ))}
                  <button
                    className="w-full flex justify-between items-center py-2 px-2 rounded transition-colors border-b border-lime-400 dark:border-slate-700 hover:bg-lime-400/30 dark:hover:bg-slate-800 disabled:opacity-60 disabled:cursor-not-allowed"
                    title={exportReportId ? "Enviar reporte por correo" : "Selecciona un reporte"}
                    disabled={!exportReportId}
                    onClick={openEmailModal}
                    type="button"
                  >
                    <span className="text-lime-800 dark:text-slate-200">Enviar por correo</span>
                    <span className="text-lime-800 dark:text-slate-200 material-icons">send</span>
                  </button>
                  <Link
                    to="/historial-reportes"
                    className="w-full flex justify-between items-center py-2 px-2 rounded transition-colors border-b border-lime-400 dark:border-slate-700 hover:bg-lime-400/30 dark:hover:bg-slate-800"
                  >
                    <span className="text-lime-800 dark:text-slate-200">Ver historial completo</span>
                    <span className="text-lime-800 dark:text-slate-200 material-icons">history</span>
                  </Link>
                </div>
              </aside>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
