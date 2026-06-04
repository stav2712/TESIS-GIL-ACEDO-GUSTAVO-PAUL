import { useEffect, useMemo, useState, type ChangeEvent } from "react";
import { Link } from "react-router-dom";
import {
  type Conversation,
  type ReportData,
  type ReportMeta,
  downloadExport,
  getConversation,
  getReportData,
  listConversations,
  selectConversationReport,
} from "../api";
import { hasPermission } from "../auth";

const DEFAULT_PAGE_SIZE = 10;
const PAGE_SIZE_OPTIONS = [5, 10, 20, 50] as const;

type PageItem = number | "left-ellipsis" | "right-ellipsis";

function dayDiff(iso: string) {
  const a = new Date(iso);
  const b = new Date();
  a.setHours(0, 0, 0, 0);
  b.setHours(0, 0, 0, 0);
  return Math.round((b.getTime() - a.getTime()) / 86400000);
}

function groupLabel(key: "hoy" | "semana" | "mes" | "anteriores") {
  if (key === "hoy") return "Hoy y ayer";
  if (key === "semana") return "Última semana";
  if (key === "mes") return "Último mes";
  return "Anteriores";
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

function rowCount(data: ReportData | null) {
  if (!data) return "-";
  return (data.total_count ?? data.display_total_count ?? data.row_count).toLocaleString("es-PE");
}

export default function ReportHistoryPage() {
  const canExport = hasPermission("can_export");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selectedConversation, setSelectedConversation] = useState<Conversation | null>(null);
  const [reports, setReports] = useState<ReportMeta[]>([]);
  const [activeReportId, setActiveReportId] = useState<string | null>(null);
  const [reportData, setReportData] = useState<ReportData | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [q, setQ] = useState("");
  const [loadingList, setLoadingList] = useState(false);
  const [loadingReport, setLoadingReport] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [expandedGroups, setExpandedGroups] = useState<Record<"hoy" | "semana" | "mes" | "anteriores", boolean>>({
    hoy: true,
    semana: false,
    mes: false,
    anteriores: false,
  });

  const activeReport = activeReportId ? reports.find((r) => r.report_id === activeReportId) ?? null : null;

  const filteredConversations = useMemo(() => {
    const query = q.trim().toLowerCase();
    if (!query) return conversations;
    return conversations.filter((conv) => {
      const text = [conv.title, conv.last_preview ?? "", conv.created_at, conv.updated_at].join(" ").toLowerCase();
      return text.includes(query);
    });
  }, [conversations, q]);

  const grouped = useMemo(() => {
    const groups: Record<"hoy" | "semana" | "mes" | "anteriores", Conversation[]> = {
      hoy: [],
      semana: [],
      mes: [],
      anteriores: [],
    };

    for (const c of filteredConversations) {
      const d = dayDiff(c.updated_at);
      if (d <= 1) groups.hoy.push(c);
      else if (d <= 7) groups.semana.push(c);
      else if (d <= 30) groups.mes.push(c);
      else groups.anteriores.push(c);
    }

    return groups;
  }, [filteredConversations]);

  async function loadConversations(selectFirst = false) {
    setLoadingList(true);
    setErr(null);
    try {
      const list = await listConversations();
      setConversations(list);
      if (selectFirst && list.length > 0 && !selectedConversation) {
        await openConversation(list[0].conversation_id);
      }
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "No se pudo cargar el historial");
    } finally {
      setLoadingList(false);
    }
  }

  async function loadReport(reportId: string, nextPage = 1, nextPageSize = pageSize) {
    setLoadingReport(true);
    setErr(null);
    try {
      const data = await getReportData(reportId, nextPage, nextPageSize);
      setReportData(data);
      setActiveReportId(reportId);
      setPage(data.page ?? nextPage);
      setPageSize(data.page_size ?? nextPageSize);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "No se pudo cargar el reporte");
    } finally {
      setLoadingReport(false);
    }
  }

  async function openConversation(conversationId: string) {
    setLoadingReport(true);
    setErr(null);
    try {
      const detail = await getConversation(conversationId);
      setSelectedConversation(detail.conversation);
      setReports(detail.reports);

      const last = detail.reports.length ? detail.reports[detail.reports.length - 1].report_id : null;
      const reportId = detail.conversation.selected_report_id || last;
      setActiveReportId(reportId);
      setReportData(null);
      setPage(1);
      setPageSize(DEFAULT_PAGE_SIZE);

      if (reportId) {
        const data = await getReportData(reportId, 1, DEFAULT_PAGE_SIZE);
        setReportData(data);
        setPage(data.page ?? 1);
        setPageSize(data.page_size ?? DEFAULT_PAGE_SIZE);
      }
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "No se pudo abrir el reporte");
    } finally {
      setLoadingReport(false);
    }
  }

  async function selectReport(reportId: string) {
    if (!selectedConversation) return;
    await selectConversationReport(selectedConversation.conversation_id, reportId).catch(() => undefined);
    await loadReport(reportId, 1, pageSize);
    setSelectedConversation((prev) => (prev ? { ...prev, selected_report_id: reportId } : prev));
  }

  async function changePage(nextPage: number) {
    if (!activeReportId) return;
    await loadReport(activeReportId, nextPage, pageSize);
  }

  async function changePageSize(nextPageSize: number) {
    if (!activeReportId) return;
    await loadReport(activeReportId, 1, nextPageSize);
  }

  async function doDownload(format: "csv" | "xlsx" | "pdf") {
    if (!activeReportId) return;
    try {
      await downloadExport(activeReportId, format);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "No se pudo exportar el reporte");
    }
  }

  useEffect(() => {
    loadConversations(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="h-full min-h-0 flex flex-col">
      <section className="rounded-3xl bg-[#C6EB32] dark:bg-slate-900 border border-lime-200 dark:border-slate-700 p-6 shadow-xl shadow-cyan-950/20 overflow-hidden relative">
        <div className="absolute -right-16 -top-16 w-48 h-48 rounded-full bg-white/25 dark:bg-white/5" />
        <div className="relative flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm uppercase tracking-[0.3em] text-[#006a90] dark:text-lime-300 font-bold">Historial de reportes</p>
            <h2 className="text-3xl lg:text-4xl font-bold mt-2 text-[#005f80] dark:text-white">Reportes generados</h2>
            <p className="text-[#005f80]/90 dark:text-slate-300 mt-3 max-w-3xl font-medium">
              Revisa reportes anteriores en un módulo separado de la pantalla de consultas. Puedes abrirlos, paginarlos y exportarlos según tus permisos.
            </p>
          </div>
          <Link
            to="/consultas"
            className="inline-flex items-center gap-2 px-5 py-3 rounded-lg bg-[#0083B0] hover:bg-[#006a90] text-white font-bold transition"
          >
            <span className="material-icons">add</span>
            Nuevo reporte
          </Link>
        </div>
      </section>

      {err && <div className="mt-4 p-3 rounded-lg bg-red-100 text-red-700 border border-red-200">{err}</div>}

      <section className="grid grid-cols-1 xl:grid-cols-[22rem_minmax(0,1fr)] gap-6 mt-6 min-h-0 flex-1">
        <aside className="rounded-2xl bg-white dark:bg-slate-900 border border-cyan-100 dark:border-slate-800 p-4 shadow-xl shadow-cyan-950/10 min-h-0 flex flex-col">
          <div className="relative mb-4">
            <span className="material-icons absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">search</span>
            <input
              className="w-full pl-10 pr-3 py-2.5 rounded-xl border border-cyan-100 dark:border-slate-700 bg-white dark:bg-slate-950 focus:outline-none focus:ring-2 focus:ring-[#0083B0]"
              placeholder="Buscar por título o vista previa"
              value={q}
              onChange={(e: ChangeEvent<HTMLInputElement>) => setQ(e.target.value)}
            />
          </div>

          <div className="flex items-center justify-between gap-3 mb-3">
            <p className="text-sm font-bold text-slate-700 dark:text-slate-200">{filteredConversations.length} conversaciones</p>
            <button className="text-xs font-bold text-[#0083B0] dark:text-lime-300 hover:underline" type="button" onClick={() => loadConversations(false)}>
              Actualizar
            </button>
          </div>

          <div className="overflow-y-auto min-h-0 pr-1 scrollbar-subtle space-y-5">
            {(["hoy", "semana", "mes", "anteriores"] as const).map((group) => {
              const items = grouped[group];
              if (!items.length) return null;

              const expanded = expandedGroups[group];

              return (
                <div key={group}>
                  <button
                    type="button"
                    aria-expanded={expanded}
                    onClick={() => setExpandedGroups((prev) => ({ ...prev, [group]: !prev[group] }))}
                    className="w-full flex items-center justify-between gap-3 text-left text-xs uppercase tracking-[0.18em] text-[#0083B0] dark:text-lime-300 font-bold mb-2 rounded-lg hover:bg-cyan-50 dark:hover:bg-slate-800 px-1.5 py-1 transition"
                  >
                    <span>{groupLabel(group)}</span>
                    <span className="inline-flex items-center gap-1 text-[10px] tracking-normal normal-case text-slate-500 dark:text-slate-400">
                      {items.length}
                      <span className="material-icons text-base transition-transform" aria-hidden="true">
                        {expanded ? "expand_less" : "expand_more"}
                      </span>
                    </span>
                  </button>
                  {expanded && (
                    <div className="space-y-2">
                      {items.map((conv) => {
                        const active = selectedConversation?.conversation_id === conv.conversation_id;
                        return (
                          <button
                            key={conv.conversation_id}
                            type="button"
                            onClick={() => openConversation(conv.conversation_id)}
                            className={[
                              "w-full text-left rounded-xl border px-3 py-3 transition",
                              active
                                ? "bg-[#0083B0] border-[#0083B0] text-white shadow-md"
                                : "bg-white dark:bg-slate-950 border-cyan-100 dark:border-slate-800 hover:bg-cyan-50 dark:hover:bg-slate-800",
                            ].join(" ")}
                          >
                            <div className="font-bold line-clamp-2">{conv.title}</div>
                            <div className={active ? "text-xs text-cyan-50 mt-1" : "text-xs text-slate-500 dark:text-slate-400 mt-1"}>
                              {formatDate(conv.updated_at)}
                            </div>
                            {conv.last_preview && <div className={active ? "text-xs text-cyan-50/90 mt-2 line-clamp-2" : "text-xs text-slate-500 dark:text-slate-400 mt-2 line-clamp-2"}>{conv.last_preview}</div>}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}

            {!loadingList && filteredConversations.length === 0 && (
              <div className="rounded-xl bg-cyan-50 dark:bg-slate-950 border border-cyan-100 dark:border-slate-800 p-4 text-sm text-slate-500 dark:text-slate-400">
                No hay reportes en el historial.
              </div>
            )}

            {loadingList && <div className="text-sm text-slate-500 dark:text-slate-400">Cargando historial...</div>}
          </div>
        </aside>

        <main className="min-w-0 min-h-0 flex flex-col gap-4">
          {selectedConversation && reports.length > 0 && (
            <section className="rounded-2xl bg-white dark:bg-slate-900 border border-cyan-100 dark:border-slate-800 p-4 shadow-xl shadow-cyan-950/10">
              <div className="flex items-center justify-between gap-3 flex-wrap mb-3">
                <div>
                  <p className="text-xs uppercase tracking-[0.2em] text-[#0083B0] dark:text-lime-300 font-bold">Reportes de la conversación</p>
                  <h3 className="font-bold text-lg text-slate-900 dark:text-white">{selectedConversation.title}</h3>
                </div>
                <span className="px-3 py-1 rounded-full bg-[#C6EB32]/40 text-[#005f80] text-xs font-bold">{reports.length} reportes</span>
              </div>
              <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-subtle">
                {reports.map((report, index) => {
                  const active = report.report_id === activeReportId;
                  const selected = report.report_id === selectedConversation.selected_report_id;
                  return (
                    <button
                      key={report.report_id}
                      type="button"
                      onClick={() => selectReport(report.report_id)}
                      className={[
                        "min-w-[16rem] max-w-xs rounded-xl border px-3 py-3 text-left transition",
                        active
                          ? "bg-[#0083B0] text-white border-[#0083B0]"
                          : "bg-white dark:bg-slate-950 border-cyan-100 dark:border-slate-800 hover:bg-cyan-50 dark:hover:bg-slate-800",
                      ].join(" ")}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-bold uppercase tracking-wide">Reporte {index + 1}</span>
                        {selected && <span className={active ? "text-[10px] bg-white/20 rounded-full px-2 py-0.5" : "text-[10px] bg-[#C6EB32]/40 text-[#005f80] rounded-full px-2 py-0.5"}>Seleccionado</span>}
                      </div>
                      <div className="font-bold line-clamp-2 mt-1">{report.nl}</div>
                      <div className={active ? "text-xs text-cyan-50 mt-1" : "text-xs text-slate-500 dark:text-slate-400 mt-1"}>{formatDate(report.timestamp)}</div>
                    </button>
                  );
                })}
              </div>
            </section>
          )}

          {activeReport ? (
            <article className="rounded-3xl bg-white dark:bg-slate-900 border border-cyan-100 dark:border-slate-800 shadow-xl shadow-cyan-950/10 overflow-hidden min-h-0">
              <div className="bg-[#0083B0] text-white p-6 relative overflow-hidden">
                <div className="absolute -right-14 -top-14 w-40 h-40 rounded-full bg-white/10" />
                <div className="relative flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
                  <div className="min-w-0">
                    <p className="text-xs uppercase tracking-[0.25em] text-cyan-50 font-bold">Reporte histórico</p>
                    <h2 className="text-2xl lg:text-3xl font-bold mt-2 leading-tight">{activeReport.nl}</h2>
                    <p className="text-sm text-cyan-50 mt-3">Generado: {formatDate(activeReport.timestamp)}</p>
                  </div>
                  <div className="grid grid-cols-3 gap-2 shrink-0">
                    <div className="rounded-2xl bg-white/15 px-4 py-3">
                      <div className="text-[11px] uppercase tracking-wide text-cyan-50">Filas</div>
                      <div className="font-bold text-xl">{rowCount(reportData)}</div>
                    </div>
                    <div className="rounded-2xl bg-white/15 px-4 py-3">
                      <div className="text-[11px] uppercase tracking-wide text-cyan-50">Columnas</div>
                      <div className="font-bold text-xl">{reportData?.columns.length ?? "-"}</div>
                    </div>
                    <div className="rounded-2xl bg-white/15 px-4 py-3">
                      <div className="text-[11px] uppercase tracking-wide text-cyan-50">Latencia</div>
                      <div className="font-bold text-xl">{activeReport.latency_ms} ms</div>
                    </div>
                  </div>
                </div>
              </div>

              <div className="p-5 lg:p-6 space-y-5">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex flex-wrap gap-2">
                    {canExport && (["csv", "xlsx", "pdf"] as const).map((fmt) => (
                      <button
                        key={fmt}
                        type="button"
                        onClick={() => doDownload(fmt)}
                        className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-[#C6EB32] hover:bg-lime-300 text-[#005f80] font-bold transition"
                      >
                        <span className="material-icons text-[18px]">file_download</span>
                        {fmt === "csv" ? "CSV" : fmt === "xlsx" ? "Excel" : "PDF"}
                      </button>
                    ))}
                  </div>
                  <Link to="/consultas" className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-cyan-100 dark:border-slate-700 font-bold text-[#005f80] dark:text-lime-300 hover:bg-cyan-50 dark:hover:bg-slate-800">
                    <span className="material-icons text-[18px]">query_stats</span>
                    Nueva consulta
                  </Link>
                </div>

                {reportData?.result_message && (
                  <div className="rounded-xl bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 text-amber-800 dark:text-amber-200 px-4 py-3 text-sm">
                    {reportData.result_message}
                  </div>
                )}

                {!!reportData?.suppressed_columns?.length && (
                  <div className="rounded-xl bg-cyan-50 dark:bg-slate-800 border border-cyan-100 dark:border-slate-700 text-cyan-800 dark:text-slate-200 px-4 py-3 text-xs">
                    Columnas ocultas por tu perfil: {reportData.suppressed_columns.join(", ")}
                  </div>
                )}

                {activeReport.sql && (
                  <details className="rounded-2xl border border-cyan-100 dark:border-slate-800 bg-cyan-50/40 dark:bg-slate-950 overflow-hidden">
                    <summary className="cursor-pointer px-4 py-3 font-bold text-[#005f80] dark:text-lime-300 flex items-center gap-2">
                      <span className="material-icons text-[18px]">code</span>
                      SQL generado
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
                        Vista del reporte
                      </h3>
                      <p className="text-xs text-slate-500 dark:text-slate-400">Página {page}{reportData?.total_pages ? ` de ${reportData.total_pages}` : ""}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-slate-600 dark:text-slate-300">Mostrar</span>
                      <select
                        className="border rounded-lg px-2 py-1.5 outline-none dark:bg-slate-800 dark:border-slate-700"
                        value={pageSize}
                        onChange={(e: ChangeEvent<HTMLSelectElement>) => changePageSize(Number(e.target.value))}
                        disabled={loadingReport || !activeReportId}
                      >
                        {PAGE_SIZE_OPTIONS.map((n) => (
                          <option key={n} value={n}>{n}</option>
                        ))}
                      </select>
                    </div>
                  </div>

                  <div className="overflow-x-auto w-full">
                    <table className="w-full text-sm text-left text-slate-600 dark:text-slate-200 whitespace-nowrap">
                      <thead className="text-xs uppercase bg-[#C6EB32] text-[#005f80]">
                        <tr>
                          {reportData?.columns.length ? reportData.columns.map((col) => (
                            <th key={col} className="px-4 py-3 font-bold">{col}</th>
                          )) : <th className="px-4 py-3">Sin columnas</th>}
                        </tr>
                      </thead>
                      <tbody>
                        {reportData?.rows.length ? reportData.rows.map((row, rowIndex) => (
                          <tr key={`${activeReport.report_id}-${page}-${rowIndex}`} className="border-t border-cyan-100 dark:border-slate-800 odd:bg-white even:bg-slate-50 dark:odd:bg-slate-900 dark:even:bg-slate-950">
                            {reportData.columns.map((col) => (
                              <td key={col} className="px-4 py-3 align-top max-w-[28rem] truncate" title={formatCell(row[col])}>
                                {formatCell(row[col])}
                              </td>
                            ))}
                          </tr>
                        )) : (
                          <tr>
                            <td className="px-4 py-6 text-center text-slate-500" colSpan={Math.max(reportData?.columns.length ?? 1, 1)}>
                              {loadingReport ? "Cargando reporte..." : "La consulta no devolvió filas."}
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>

                  <div className="bg-slate-50 dark:bg-slate-950 px-4 py-3 border-t border-cyan-100 dark:border-slate-800 flex flex-wrap items-center justify-between gap-4">
                    <div className="text-xs text-slate-500 dark:text-slate-400">Mostrando {reportData?.row_count ?? 0} filas en esta página.</div>
                    <div className="flex items-center gap-1">
                      <button className="p-2 rounded-lg text-slate-500 hover:text-lime-700 hover:bg-lime-100 dark:text-slate-400 dark:hover:text-white dark:hover:bg-slate-800 disabled:opacity-40" disabled={!reportData || page <= 1 || loadingReport} onClick={() => changePage(page - 1)} type="button" title="Página anterior">
                        <span className="material-icons">chevron_left</span>
                      </button>
                      {getPaginationItems(page, reportData?.total_pages).map((item) =>
                        typeof item === "number" ? (
                          <button
                            key={item}
                            type="button"
                            onClick={() => changePage(item)}
                            disabled={!reportData || loadingReport || item === page}
                            aria-current={item === page ? "page" : undefined}
                            className={[
                              "min-w-9 h-9 px-3 rounded-lg text-sm font-semibold transition-colors",
                              item === page ? "bg-lime-700 text-white dark:bg-slate-700" : "bg-white text-lime-800 hover:bg-lime-100 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800",
                              "disabled:opacity-100",
                            ].join(" ")}
                          >
                            {item}
                          </button>
                        ) : <span key={item} className="min-w-9 h-9 px-2 flex items-center justify-center text-lime-800 dark:text-slate-300 font-bold">...</span>
                      )}
                      <button className="p-2 rounded-lg text-lime-700 hover:text-lime-900 hover:bg-lime-100 dark:text-slate-300 dark:hover:text-white dark:hover:bg-slate-800 disabled:opacity-40" disabled={!reportData || loadingReport || (reportData.total_pages ? page >= reportData.total_pages : reportData.row_count < reportData.page_size)} onClick={() => changePage(page + 1)} type="button" title="Página siguiente">
                        <span className="material-icons">chevron_right</span>
                      </button>
                    </div>
                  </div>
                </section>
              </div>
            </article>
          ) : selectedConversation ? (
            <section className="rounded-3xl bg-white dark:bg-slate-900 border border-cyan-100 dark:border-slate-800 p-8 shadow-xl shadow-cyan-950/10 text-center">
              <div className="mx-auto w-16 h-16 rounded-3xl bg-[#C6EB32] text-[#005f80] flex items-center justify-center mb-4">
                <span className="material-icons text-4xl">description</span>
              </div>
              <h2 className="text-2xl font-bold text-slate-900 dark:text-white">Sin reportes generados</h2>
              <p className="mt-2 text-slate-500 dark:text-slate-400">Esta conversación está seleccionada, pero no tiene ningún reporte generado para mostrar.</p>
              <Link
                to="/consultas"
                className="mt-5 inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-[#0083B0] hover:bg-[#006a90] text-white font-bold transition"
              >
                <span className="material-icons text-[18px]">query_stats</span>
                Crear nuevo reporte
              </Link>
            </section>
          ) : (
            <section className="rounded-3xl bg-white dark:bg-slate-900 border border-cyan-100 dark:border-slate-800 p-8 shadow-xl shadow-cyan-950/10 text-center">
              <div className="mx-auto w-16 h-16 rounded-3xl bg-[#C6EB32] text-[#005f80] flex items-center justify-center mb-4">
                <span className="material-icons text-4xl">history</span>
              </div>
              <h2 className="text-2xl font-bold text-slate-900 dark:text-white">Selecciona un reporte</h2>
              <p className="mt-2 text-slate-500 dark:text-slate-400">Elige una conversación del historial para revisar su reporte generado.</p>
            </section>
          )}
        </main>
      </section>
    </div>
  );
}
