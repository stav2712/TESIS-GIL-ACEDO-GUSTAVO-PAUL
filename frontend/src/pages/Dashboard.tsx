import { useEffect, useMemo, useRef, useState } from "react";
import { clearToken, getAuthUser } from "../auth";
import {
  type Conversation,
  type ReportData,
  type QueryJob,
  type QueryResponse,
  type ReportMeta,
  deleteConversation,
  downloadExport,
  getConversation,
  getQueryJob,
  getReportData,
  listActiveQueryJobs,
  listConversations,
  renameConversation,
  selectConversationReport,
  sendFeedback,
  sendReportEmail,
  startQueryJob,
} from "../api";
import { getTheme, toggleTheme } from "../theme";

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

function dayDiff(iso: string) {
  const a = new Date(iso);
  const b = new Date();
  a.setHours(0, 0, 0, 0);
  b.setHours(0, 0, 0, 0);
  return Math.round((b.getTime() - a.getTime()) / 86400000);
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
    <div className="mb-4 flex items-start gap-3">
      <div className="bg-amber-300 rounded-full w-8 h-8 flex items-center justify-center font-bold text-amber-800 shrink-0">A</div>
      <div className="chat-inline-loader bg-white dark:bg-slate-900 border border-lime-200 dark:border-slate-800 shadow-sm rounded-2xl px-4 py-3 w-full max-w-xl">
        <div className="flex items-center justify-between gap-4 mb-3">
          <div>
            <div className="text-sm font-semibold text-slate-800 dark:text-slate-100">{label}</div>
            <div className="text-xs text-slate-500 dark:text-slate-400">Preparando resultados...</div>
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
    </div>
  );
}

function formatCell(value: unknown) {
  if (value === null || value === undefined) return "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export default function Dashboard() {
  const authUser = getAuthUser();
  const [leftOpen, setLeftOpen] = useState(false);
  const [rightOpen, setRightOpen] = useState(false);

  const [convs, setConvs] = useState<Conversation[]>([]);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [reports, setReports] = useState<ReportMeta[]>([]);
  const [activeReportId, setActiveReportId] = useState<string | null>(null);
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null);

  const [tablesById, setTablesById] = useState<Record<string, ReportData | null>>({});
  const [pagesById, setPagesById] = useState<Record<string, number>>({});
  const [pageSizesById, setPageSizesById] = useState<Record<string, number>>({});

  const [nl, setNl] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingLabel, setLoadingLabel] = useState("Procesando reporte");
  const [err, setErr] = useState<string | null>(null);
  const [menuFor, setMenuFor] = useState<string | null>(null);

  const [emailOpen, setEmailOpen] = useState(false);
  const [emailFormats, setEmailFormats] = useState<ExportFormat[]>(["xlsx"]);
  const [emailLoading, setEmailLoading] = useState(false);
  const [emailErr, setEmailErr] = useState<string | null>(null);
  const [emailMsg, setEmailMsg] = useState<string | null>(null);

  const [pendingJob, setPendingJob] = useState<PendingJobSnapshot | null>(() => readPendingJob());
  const viewRequestRef = useRef(0);
  const pollTimeoutRef = useRef<ReturnType<typeof window.setTimeout> | null>(null);

  const overlayVisible = leftOpen || rightOpen;
  const exportReportId = selectedReportId || activeReportId;
  const exportReport = exportReportId ? reports.find((r) => r.report_id === exportReportId) ?? null : null;
  const exportReportText = exportReport?.nl ?? null;
  const theme = getTheme();

  const getReportPageSize = (reportId: string) => pageSizesById[reportId] ?? DEFAULT_PAGE_SIZE;

  const closeMenus = () => {
    setLeftOpen(false);
    setRightOpen(false);
    setMenuFor(null);
  };

  async function refreshConversations() {
    const list = await listConversations();
    setConvs(list);
  }

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

      try {
        await refreshConversations();
      } catch {
        // La pantalla puede cargar aunque el historial falle temporalmente.
      }

      if (cancelled) return;

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
        // Si falla la recuperación de trabajos, aún intentamos restaurar el último chat.
      }

      if (snapshot?.active_conv_id && !cancelled) {
        await openConversation(snapshot.active_conv_id, { preferReportId: snapshot.active_report_id || snapshot.selected_report_id });
      }
    }

    boot();

    return () => {
      cancelled = true;
      if (pollTimeoutRef.current) window.clearTimeout(pollTimeoutRef.current);
    };
  }, []);

  useEffect(() => {
    if (!menuFor) return;

    function handlePointerDown(event: PointerEvent) {
      const target = event.target as HTMLElement | null;
      if (target?.closest("[data-chat-menu-root]")) return;
      setMenuFor(null);
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setMenuFor(null);
    }

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [menuFor]);

  const grouped = useMemo(() => {
    const ayer: Conversation[] = [];
    const semana: Conversation[] = [];
    const mes: Conversation[] = [];

    for (const c of convs) {
      const d = dayDiff(c.updated_at);
      if (d <= 1) ayer.push(c);
      else if (d <= 7) semana.push(c);
      else mes.push(c);
    }

    return { ayer, semana, mes };
  }, [convs]);

  async function openConversation(conversationId: string, options: { preferReportId?: string | null } = {}) {
    const requestId = ++viewRequestRef.current;
    setErr(null);
    setLoadingLabel("Cargando conversación");
    setLoading(true);

    try {
      const detail = await getConversation(conversationId);
      if (requestId !== viewRequestRef.current) return;

      setActiveConvId(detail.conversation.conversation_id);
      setReports(detail.reports);

      const sel = detail.conversation.selected_report_id;
      setSelectedReportId(sel);

      const last = detail.reports.length ? detail.reports[detail.reports.length - 1].report_id : null;
      const preferred = options.preferReportId && detail.reports.some((r) => r.report_id === options.preferReportId) ? options.preferReportId : null;
      const toShow = preferred || sel || last;
      setActiveReportId(toShow);

      const nextTables: Record<string, ReportData | null> = {};
      const nextPages: Record<string, number> = {};
      const nextPageSizes: Record<string, number> = {};

      await Promise.all(
        detail.reports.map(async (r) => {
          const size = getReportPageSize(r.report_id);
          nextPageSizes[r.report_id] = size;
          try {
            const data = await getReportData(r.report_id, 1, size);
            nextTables[r.report_id] = data;
            nextPages[r.report_id] = 1;
          } catch {
            nextTables[r.report_id] = null;
            nextPages[r.report_id] = 1;
          }
        })
      );

      if (requestId !== viewRequestRef.current) return;
      setTablesById(nextTables);
      setPagesById(nextPages);
      setPageSizesById(nextPageSizes);
      closeMenus();
    } catch (ex) {
      if (requestId === viewRequestRef.current) {
        setErr(ex instanceof Error ? ex.message : "Error");
      }
    } finally {
      if (requestId === viewRequestRef.current) {
        setLoading(false);
      }
    }
  }

  async function ensureReportLoaded(reportId: string) {
    if (tablesById[reportId]) return;

    setLoadingLabel("Cargando reporte");
    setLoading(true);

    try {
      const size = getReportPageSize(reportId);
      const data = await getReportData(reportId, 1, size);
      setTablesById((prev) => ({ ...prev, [reportId]: data }));
      setPagesById((prev) => ({ ...prev, [reportId]: 1 }));
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Error al cargar reporte");
    } finally {
      setLoading(false);
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

    await selectConversationReport(result.conversation_id, result.report_id).catch(() => {});
    await refreshConversations();

    const detail = await getConversation(result.conversation_id);
    setActiveConvId(detail.conversation.conversation_id);
    setReports(detail.reports);
    setSelectedReportId(detail.conversation.selected_report_id || result.report_id);
    setActiveReportId(result.report_id);

    const firstPageData = responseToReportData(result);
    setTablesById((prev) => ({ ...prev, [result.report_id]: firstPageData }));
    setPagesById((prev) => ({ ...prev, [result.report_id]: firstPageData.page ?? 1 }));
    setPageSizesById((prev) => ({ ...prev, [result.report_id]: result.page_size || DEFAULT_PAGE_SIZE }));
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
      await refreshConversations().catch(() => {});
      return;
    }

    setLoadingLabel(job.status === "queued" ? "Reporte en cola" : "Generando reporte");
    setLoading(true);
  }

  useEffect(() => {
    if (!pendingJob) return;

    let cancelled = false;

    async function checkJob() {
      try {
        const job = await getQueryJob(pendingJob.job_id);
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
        if (!cancelled && readPendingJob()?.job_id === pendingJob.job_id) {
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
      await refreshConversations().catch(() => {});
    } catch (ex) {
      clearPendingJob();
      setPendingJob(null);
      setErr(ex instanceof Error ? ex.message : "Error al iniciar el reporte");
      setLoading(false);
    }
  }

  const isDraftNewChat = !activeConvId && reports.length === 0;

  function newChat() {
    if (pendingJob) {
      setErr("Hay un reporte generándose. Cuando termine podrás iniciar un chat nuevo sin perder el resultado.");
      closeMenus();
      return;
    }

    if (isDraftNewChat) {
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

  async function doRename(conversationId: string) {
    const current = convs.find((c) => c.conversation_id === conversationId);
    const title = prompt("Nuevo nombre del chat:", current?.title ?? "");
    if (!title?.trim()) return;

    try {
      await renameConversation(conversationId, title.trim());
      await refreshConversations();
      setMenuFor(null);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Error al renombrar chat");
    }
  }

  async function doDelete(conversationId: string) {
    if (!confirm("¿Eliminar este chat? (solo para tu usuario)")) return;

    try {
      await deleteConversation(conversationId);
      await refreshConversations();
      setMenuFor(null);

      if (activeConvId === conversationId) {
        viewRequestRef.current += 1;
        if (pendingJob?.conversation_id === conversationId) {
          clearPendingJob();
          setPendingJob(null);
          setLoading(false);
        }
        setActiveConvId(null);
        setReports([]);
        setActiveReportId(null);
        setSelectedReportId(null);
        setTablesById({});
        setPagesById({});
        setPageSizesById({});
      }
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Error al eliminar chat");
    }
  }

  async function selectReport(reportId: string) {
    if (!activeConvId) return;

    try {
      await selectConversationReport(activeConvId, reportId);
      setSelectedReportId(reportId);
      setActiveReportId(reportId);
      await refreshConversations();
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Error al seleccionar reporte");
    }
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

  function openEmailModal() {
    setEmailErr(null);
    setEmailMsg(null);
    if (!exportReportId) return;
    setEmailOpen(true);
  }

  function toggleEmailFormat(fmt: ExportFormat) {
    setEmailFormats((prev) => (prev.includes(fmt) ? prev.filter((x) => x !== fmt) : [...prev, fmt]));
  }

  async function doSendEmail() {
    if (!exportReportId || emailLoading) return;
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
    <div className="bg-gray-100 dark:bg-slate-950 overflow-hidden h-screen">
      <div className={`fixed inset-0 bg-black/50 z-30 transition-opacity lg:hidden ${overlayVisible ? "" : "hidden"}`} onClick={closeMenus} />

      {emailOpen && (
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
                Se respetan los mismos permisos de exportación y columnas ocultas del perfil. Si una columna está oculta, tampoco se adjunta por correo.
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

      <div className="ui-scale flex relative h-screen min-h-0">
        <aside
          className={[
            "w-64 text-white p-4 flex flex-col h-full fixed inset-y-0 left-0 z-40 transform transition-transform duration-300",
            "lg:relative lg:translate-x-0",
            leftOpen ? "translate-x-0" : "-translate-x-full",
            "bg-[#007aa3] dark:bg-slate-900",
          ].join(" ")}
        >
          <div className="flex justify-between items-center mb-8">
            <h1 className="text-2xl font-bold">empresa REPORTS</h1>
            <button className="lg:hidden text-white hover:text-cyan-200" onClick={closeMenus} type="button">
              <span className="material-icons">close</span>
            </button>
          </div>

          <button
            onClick={newChat}
            disabled={isDraftNewChat}
            className="font-bold py-2 px-4 rounded-lg flex items-center mb-6 w-full bg-[#006a90] hover:bg-[#005c7d] dark:bg-slate-800 dark:hover:bg-slate-700 disabled:opacity-60 disabled:cursor-not-allowed"
            type="button"
          >
            <span className="material-icons mr-2">add</span>
            Nuevo reporte
          </button>

          <nav className="flex-grow overflow-y-auto overflow-x-hidden scrollbar-subtle">
            {(["ayer", "semana", "mes"] as const).map((k) => {
              const label = k === "ayer" ? "Ayer" : k === "semana" ? "Última semana" : "Último mes";
              const items = grouped[k];

              return (
                <div key={k}>
                  <h2 className="text-sm font-semibold text-cyan-100 uppercase mb-4 mt-6">{label}</h2>
                  <ul>
                    {items.map((c) => (
                      <li className="mb-3 relative min-w-0" key={c.conversation_id} data-chat-menu-root>
                        <div className="flex items-center justify-between gap-2 min-w-0">
                          <button
                            onClick={() => openConversation(c.conversation_id)}
                            className={[
                              "flex-1 min-w-0 overflow-hidden text-left flex items-center text-cyan-50 hover:text-white",
                              activeConvId === c.conversation_id ? "font-semibold" : "",
                            ].join(" ")}
                            title={c.title}
                            type="button"
                          >
                            <span className="material-icons mr-3">bar_chart</span>
                            <span className="truncate min-w-0">{c.title}</span>
                          </button>
                          <button
                            onClick={() => setMenuFor((prev) => (prev === c.conversation_id ? null : c.conversation_id))}
                            className="text-cyan-100 hover:text-white rounded-full p-1 hover:bg-white/10"
                            title="Opciones"
                            type="button"
                          >
                            <span className="material-icons">more_vert</span>
                          </button>
                        </div>

                        {menuFor === c.conversation_id && (
                          <div className="absolute right-2 mt-2 w-44 bg-white dark:bg-slate-800 text-gray-900 dark:text-slate-100 rounded-xl shadow-xl soft-popover z-50 overflow-hidden border border-gray-100 dark:border-slate-700">
                            <button className="w-full text-left px-3 py-2.5 hover:bg-gray-100 dark:hover:bg-slate-700 flex items-center gap-2" onClick={() => doRename(c.conversation_id)} type="button">
                              <span className="material-icons text-[18px]">edit</span>
                              Renombrar
                            </button>
                            <button className="w-full text-left px-3 py-2.5 hover:bg-red-50 dark:hover:bg-red-950/30 text-red-700 dark:text-red-300 flex items-center gap-2" onClick={() => doDelete(c.conversation_id)} type="button">
                              <span className="material-icons text-[18px]">delete</span>
                              Eliminar
                            </button>
                          </div>
                        )}
                      </li>
                    ))}
                    {items.length === 0 && <li className="text-cyan-100 text-sm opacity-80">Sin chats</li>}
                  </ul>
                </div>
              );
            })}
          </nav>
        </aside>

        <main className="flex-1 flex flex-col h-full min-w-0 min-h-0">
          <header className="bg-white dark:bg-slate-900 dark:text-slate-50 shadow-sm p-4 flex justify-between lg:justify-end items-center z-10">
            <button
              className="lg:hidden text-gray-600 hover:text-gray-900 dark:text-slate-200 dark:hover:text-white"
              onClick={() => {
                setLeftOpen(true);
                setRightOpen(false);
              }}
              type="button"
            >
              <span className="material-icons text-3xl">menu</span>
            </button>

            <div className="flex items-center space-x-4">
              <button
                className="lg:hidden text-gray-600 hover:text-lime-700 dark:text-slate-200 dark:hover:text-lime-300"
                onClick={() => {
                  setRightOpen(true);
                  setLeftOpen(false);
                }}
                title="Exportar"
                type="button"
              >
                <span className="material-icons text-3xl">file_download</span>
              </button>

              <button onClick={() => toggleTheme()} className="text-gray-600 dark:text-slate-200" title={`Tema: ${theme}`} type="button">
                <span className="material-icons">brightness_6</span>
              </button>

              <button
                onClick={() => {
                  clearToken();
                  window.location.href = "/login";
                }}
                className="text-gray-600 dark:text-slate-200"
                title="Cerrar sesión"
                type="button"
              >
                <span className="material-icons">logout</span>
              </button>

              <div className="w-10 h-10 rounded-full bg-gray-200 dark:bg-slate-700 flex items-center justify-center" title={authUser?.username}>
                <span className="material-icons text-gray-600 dark:text-slate-200">person</span>
              </div>
            </div>
          </header>

          <div className="flex-1 p-4 lg:p-6 pb-10 flex overflow-hidden min-h-0">
            <div className="flex-1 flex flex-col lg:mr-6 min-h-0 min-w-0">
              <div className="flex-1 overflow-y-auto min-h-0 scrollbar-subtle">
                {err && (
                  <div className="mb-4">
                    <div className="text-sm text-red-700 bg-red-100 rounded-md p-2">{err}</div>
                  </div>
                )}

                {reports.length > 0 ? (
                  <div className="space-y-6 mb-4">
                    {reports.map((r) => {
                      const isActive = r.report_id === activeReportId;
                      const isSelected = r.report_id === selectedReportId;
                      const t = tablesById[r.report_id] ?? null;
                      const page = pagesById[r.report_id] ?? 1;
                      const reportPageSize = getReportPageSize(r.report_id);
                      const fb = r.feedback ?? null;

                      return (
                        <div
                          key={r.report_id}
                          className={[
                            "report-card space-y-3 rounded-2xl border overflow-hidden bg-white dark:bg-slate-900",
                            isSelected
                              ? "border-lime-500 ring-2 ring-lime-500/30"
                              : isActive
                                ? "border-slate-300 dark:border-slate-600"
                                : "border-gray-200 dark:border-slate-800",
                          ].join(" ")}
                        >
                          <button
                            onClick={async (e) => {
                              (e.currentTarget as HTMLButtonElement).blur();
                              setActiveReportId(r.report_id);
                              await ensureReportLoaded(r.report_id);
                            }}
                            className={[
                              "w-full text-left p-4 rounded-t-2xl flex items-center justify-between transition-colors",
                              isSelected
                                ? "bg-lime-100 dark:bg-lime-950/30"
                                : "bg-lime-200 dark:bg-slate-800 hover:bg-lime-100 dark:hover:bg-slate-700",
                              "focus:outline-none focus-visible:outline-none",
                            ].join(" ")}
                            title={r.nl}
                            type="button"
                          >
                            <p className="text-lime-900 dark:text-slate-100 line-clamp-2">{r.nl}</p>
                            <div className="ml-4 flex items-center gap-2 shrink-0">
                              {isSelected && <span className="text-[11px] font-bold rounded-full bg-lime-700 text-white px-2 py-0.5">SELECCIONADO</span>}
                              <span className="text-xs text-lime-900/80 dark:text-slate-300">{r.latency_ms}ms</span>
                            </div>
                          </button>

                          <div className="bg-white dark:bg-slate-900 dark:text-slate-50 shadow-md overflow-hidden">
                            <div className="flex items-center p-4">
                              <div className="bg-amber-300 rounded-full w-8 h-8 flex items-center justify-center font-bold text-amber-800 mr-4">A</div>
                              <div className="text-sm text-gray-600 dark:text-slate-300">
                                {t ? `Reporte cargado${t.total_count != null ? ` · ${t.total_count} filas` : ""}` : "Cargando reporte..."}
                              </div>
                            </div>

                            {t?.result_message && (
                              <div className="mx-4 mb-3 rounded-lg bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 text-amber-800 dark:text-amber-200 px-3 py-2 text-sm">
                                {t.result_message}
                              </div>
                            )}

                            {!!t?.suppressed_columns?.length && (
                              <div className="mx-4 mb-3 rounded-lg bg-cyan-50 dark:bg-slate-800 border border-cyan-100 dark:border-slate-700 text-cyan-800 dark:text-slate-200 px-3 py-2 text-xs">
                                Columnas ocultas por tu perfil: {t.suppressed_columns.join(", ")}
                              </div>
                            )}

                            <div className="overflow-x-auto w-full">
                              <table className="w-full text-sm text-left text-gray-500 dark:text-slate-200 whitespace-nowrap lg:whitespace-normal">
                                <thead className="text-xs text-gray-700 dark:text-slate-200 uppercase bg-gray-50 dark:bg-slate-800">
                                  <tr>
                                    {(t?.columns?.length ? t.columns : ["Sin datos"]).map((c) => (
                                      <th key={c} className="px-6 py-3">
                                        {c}
                                      </th>
                                    ))}
                                  </tr>
                                </thead>
                                <tbody>
                                  {!t && (
                                    <tr className="bg-white dark:bg-slate-900 border-b dark:border-slate-800">
                                      <td className="px-6 py-4">Sin resultados</td>
                                    </tr>
                                  )}
                                  {t && t.rows.length === 0 && (
                                    <tr className="bg-white dark:bg-slate-900 border-b dark:border-slate-800">
                                      <td className="px-6 py-4" colSpan={Math.max(t.columns.length, 1)}>
                                        La consulta no devolvió filas.
                                      </td>
                                    </tr>
                                  )}
                                  {t?.rows?.map((row, idx) => (
                                    <tr key={idx} className="bg-white dark:bg-slate-900 border-b dark:border-slate-800">
                                      {t.columns.map((c) => (
                                        <td key={c} className="px-6 py-4">
                                          {formatCell(row[c])}
                                        </td>
                                      ))}
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>

                            <div className="flex flex-col sm:flex-row justify-between items-center p-4 border-t dark:border-slate-800 gap-4">
                              <div className="flex items-center">
                                <span className="text-sm text-gray-700 dark:text-slate-200 mr-2">Mostrar</span>
                                <select
                                  className="border rounded-md p-1 outline-none dark:bg-slate-800 dark:border-slate-700"
                                  value={reportPageSize}
                                  onChange={(e) => changePageSize(r.report_id, Number(e.target.value))}
                                  disabled={loading}
                                  title="Filas por página de este reporte"
                                >
                                  {PAGE_SIZE_OPTIONS.map((n) => (
                                    <option key={n} value={n}>
                                      {n}
                                    </option>
                                  ))}
                                </select>
                              </div>

                              <div className="flex items-center gap-1">
                                <button
                                  className="p-2 rounded-lg text-gray-400 hover:text-lime-700 hover:bg-lime-100 dark:text-slate-400 dark:hover:text-white dark:hover:bg-slate-800 disabled:opacity-40"
                                  disabled={!t || page <= 1 || loading}
                                  onClick={() => changePage(r.report_id, page - 1)}
                                  type="button"
                                  title="Página anterior"
                                >
                                  <span className="material-icons">chevron_left</span>
                                </button>

                                {getPaginationItems(page, t?.total_pages).map((item) =>
                                  typeof item === "number" ? (
                                    <button
                                      key={item}
                                      type="button"
                                      onClick={() => changePage(r.report_id, item)}
                                      disabled={!t || loading || item === page}
                                      aria-current={item === page ? "page" : undefined}
                                      className={[
                                        "min-w-9 h-9 px-3 rounded-lg text-sm font-semibold transition-colors",
                                        item === page
                                          ? "bg-lime-700 text-white dark:bg-slate-700"
                                          : "bg-white text-lime-800 hover:bg-lime-100 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800",
                                        "disabled:opacity-100",
                                      ].join(" ")}
                                    >
                                      {item}
                                    </button>
                                  ) : (
                                    <span key={item} className="min-w-9 h-9 px-2 flex items-center justify-center text-lime-800 dark:text-slate-300 font-bold">
                                      ...
                                    </span>
                                  )
                                )}

                                <button
                                  className="p-2 rounded-lg text-lime-700 hover:text-lime-900 hover:bg-lime-100 dark:text-slate-300 dark:hover:text-white dark:hover:bg-slate-800 disabled:opacity-40"
                                  disabled={!t || loading || (t.total_pages ? page >= t.total_pages : t.row_count < t.page_size)}
                                  onClick={() => changePage(r.report_id, page + 1)}
                                  type="button"
                                  title="Página siguiente"
                                >
                                  <span className="material-icons">chevron_right</span>
                                </button>
                              </div>
                            </div>

                            <div className="bg-lime-200 dark:bg-slate-800 px-4 py-3 flex items-center justify-between">
                              <button
                                onClick={() => selectReport(r.report_id)}
                                disabled={!activeConvId || isSelected}
                                className={[
                                  "px-4 py-2 rounded-md transition-colors font-bold text-sm",
                                  isSelected
                                    ? "bg-lime-300 text-lime-950 dark:bg-slate-700 dark:text-slate-100"
                                    : "bg-lime-700 hover:bg-lime-800 dark:bg-slate-700 dark:hover:bg-slate-600 text-white",
                                  "disabled:opacity-80",
                                ].join(" ")}
                                type="button"
                              >
                                {isSelected ? "REPORTE SELECCIONADO" : "SELECCIONAR"}
                              </button>

                              <div className="flex items-center space-x-2">
                                <button
                                  onClick={() => feedback(r.report_id, "up")}
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
                                  onClick={() => feedback(r.report_id, "down")}
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
                        </div>
                      );
                    })}
                  </div>
                ) : !loading ? (
                  <div className="bg-white dark:bg-slate-900 dark:text-slate-50 shadow-md rounded-lg overflow-hidden">
                    <div className="flex items-center p-4">
                      <div className="bg-amber-300 rounded-full w-8 h-8 flex items-center justify-center font-bold text-amber-800 mr-4">A</div>
                      <div className="text-sm text-gray-600 dark:text-slate-300">Abre un chat o crea uno nuevo.</div>
                    </div>
                    <div className="overflow-x-auto w-full">
                      <table className="w-full text-sm text-left text-gray-500 dark:text-slate-200 whitespace-nowrap lg:whitespace-normal">
                        <thead className="text-xs text-gray-700 dark:text-slate-200 uppercase bg-gray-50 dark:bg-slate-800">
                          <tr>
                            <th className="px-6 py-3">Sin datos</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr className="bg-white dark:bg-slate-900 border-b dark:border-slate-800">
                            <td className="px-6 py-4">Sin resultados</td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </div>
                ) : null}

                {loading && <ChatLoader label={loadingLabel} />}
              </div>

              <div className="bg-lime-200 dark:bg-slate-800 p-4 mt-4 rounded-lg flex items-center justify-between shadow-sm">
                <input
                  className="bg-transparent outline-none flex-1 text-lime-900 dark:text-slate-100 placeholder:text-lime-800/70 dark:placeholder:text-slate-400 disabled:opacity-60"
                  placeholder={loading ? "Procesando consulta..." : "Consulta"}
                  value={nl}
                  disabled={loading}
                  onChange={(e) => setNl(e.target.value)}
                  onKeyDown={(e) => {
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

            <aside
              className={[
                "w-80 bg-lime-300 dark:bg-slate-900 p-6 flex flex-col fixed inset-y-0 right-0 z-40 transform transition-transform duration-300",
                "lg:relative lg:translate-x-0 lg:rounded-lg overflow-y-auto shrink-0 scrollbar-subtle",
                rightOpen ? "translate-x-0" : "translate-x-full",
              ].join(" ")}
            >
              <div className="flex justify-between items-center mb-6">
                <h2 className="text-xl font-bold text-lime-800 dark:text-slate-100">Exportación del reporte generado</h2>
                <button className="lg:hidden text-lime-800 dark:text-slate-200 hover:text-lime-900 dark:hover:text-white" onClick={closeMenus} type="button">
                  <span className="material-icons">close</span>
                </button>
              </div>

              <div className="mb-4">
                <div className="text-xs font-semibold text-lime-800 dark:text-slate-300 mb-1">Reporte actual</div>
                <div className="text-sm text-lime-900 dark:text-slate-100 bg-lime-200/60 dark:bg-slate-800/70 rounded-md p-2">
                  {exportReportText ? exportReportText : "Ninguno seleccionado"}
                </div>
              </div>

              <div className="space-y-4">
                <div className="font-semibold text-lime-800 dark:text-slate-200">Exportar</div>

                {(["csv", "xlsx", "pdf"] as const).map((fmt) => (
                  <div
                    key={fmt}
                    className="flex justify-between items-center py-2 border-b border-lime-400 dark:border-slate-700 hover:bg-lime-400/30 dark:hover:bg-slate-800 px-2 rounded cursor-pointer transition-colors"
                    onClick={async () => {
                      if (!exportReportId) return;
                      await downloadExport(exportReportId, fmt);
                    }}
                    title={exportReportId ? `Exportar ${fmt}` : "Selecciona un reporte"}
                  >
                    <span className="text-lime-800 dark:text-slate-200">{fmt === "csv" ? "CSV" : fmt === "xlsx" ? "Excel" : "PDF"}</span>
                    <button className="text-lime-800 dark:text-slate-200" type="button">
                      <span className="material-icons">file_download</span>
                    </button>
                  </div>
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
              </div>
            </aside>
          </div>
        </main>
      </div>
    </div>
  );
}
