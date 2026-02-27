import { useEffect, useMemo, useState } from "react";
import { clearToken } from "../auth";
import {
  type Conversation,
  type ReportMeta,
  type ReportData,
  deleteConversation,
  downloadExport,
  getConversation,
  getReportData,
  listConversations,
  renameConversation,
  runQuery,
  selectConversationReport,
  sendFeedback,
} from "../api";
import { getTheme, toggleTheme } from "../theme";

function dayDiff(iso: string) {
  const a = new Date(iso);
  const b = new Date();
  a.setHours(0, 0, 0, 0);
  b.setHours(0, 0, 0, 0);
  return Math.round((b.getTime() - a.getTime()) / 86400000);
}

export default function Dashboard() {
  const [leftOpen, setLeftOpen] = useState(false);
  const [rightOpen, setRightOpen] = useState(false);

  const [convs, setConvs] = useState<Conversation[]>([]);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);

  const [reports, setReports] = useState<ReportMeta[]>([]);
  const [activeReportId, setActiveReportId] = useState<string | null>(null);
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null);

  // historial: datos por reporte
  const [tablesById, setTablesById] = useState<Record<string, ReportData | null>>({});
  const [pagesById, setPagesById] = useState<Record<string, number>>({});

  const [nl, setNl] = useState("");
  const [pageSize, setPageSize] = useState(10);

  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [menuFor, setMenuFor] = useState<string | null>(null);

  const overlayVisible = leftOpen || rightOpen;
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
    refreshConversations().catch(() => {});
  }, []);

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

  async function openConversation(conversationId: string) {
    setErr(null);
    setLoading(true);
    try {
      const detail = await getConversation(conversationId);

      setActiveConvId(detail.conversation.conversation_id);
      setReports(detail.reports);

      const sel = detail.conversation.selected_report_id;
      setSelectedReportId(sel);

      const last = detail.reports.length ? detail.reports[detail.reports.length - 1].report_id : null;
      const toShow = sel || last;
      setActiveReportId(toShow);

      // cargar TODOS los reportes (página 1) para mostrar historial completo
      const nextTables: Record<string, ReportData | null> = {};
      const nextPages: Record<string, number> = {};

      await Promise.all(
        detail.reports.map(async (r) => {
          try {
            const data = await getReportData(r.report_id, 1, pageSize);
            nextTables[r.report_id] = data;
            nextPages[r.report_id] = 1;
          } catch {
            nextTables[r.report_id] = null;
            nextPages[r.report_id] = 1;
          }
        })
      );

      setTablesById(nextTables);
      setPagesById(nextPages);

      closeMenus();
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Error");
    } finally {
      setLoading(false);
    }
  }

  async function ensureReportLoaded(reportId: string) {
    if (tablesById[reportId]) return;
    setLoading(true);
    try {
      const data = await getReportData(reportId, 1, pageSize);
      setTablesById((prev) => ({ ...prev, [reportId]: data }));
      setPagesById((prev) => ({ ...prev, [reportId]: 1 }));
    } finally {
      setLoading(false);
    }
  }

  async function doQuery() {
    const text = nl.trim();
    if (!text) return;

    setErr(null);
    setLoading(true);
    try {
      const res = await runQuery(text, activeConvId, 1, pageSize);

      // si venías sin chat abierto, backend creó uno nuevo:
      if (!activeConvId) setActiveConvId(res.conversation_id);

      await refreshConversations();

      // recarga conversación actual para traer lista completa de reportes
      const detail = await getConversation(res.conversation_id);
      setReports(detail.reports);
      setSelectedReportId(detail.conversation.selected_report_id);

      // guardar el NUEVO reporte sin borrar los anteriores
      setActiveReportId(res.report_id);
      setTablesById((prev) => ({
        ...prev,
        [res.report_id]: {
          columns: res.columns,
          rows: res.rows,
          page: res.page,
          page_size: res.page_size,
          row_count: res.row_count,
        },
      }));
      setPagesById((prev) => ({ ...prev, [res.report_id]: 1 }));

      setNl("");
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Error al generar reporte");
    } finally {
      setLoading(false);
    }
  }

  // ✅ Nuevo reporte ya NO crea conversación (evita chats vacíos infinitos)
  // Solo “prepara” un chat nuevo local, y la conversación real se crea al enviar la primera consulta.
  const isDraftNewChat = !activeConvId && reports.length === 0;

  function newChat() {
    if (isDraftNewChat) {
      closeMenus();
      return;
    }
    setErr(null);
    setActiveConvId(null);
    setReports([]);
    setActiveReportId(null);
    setSelectedReportId(null);
    setTablesById({});
    setPagesById({});
    setNl("");
    closeMenus();
  }

  async function doRename(conversationId: string) {
    const current = convs.find((c) => c.conversation_id === conversationId);
    const title = prompt("Nuevo nombre del chat:", current?.title ?? "");
    if (!title) return;
    await renameConversation(conversationId, title);
    await refreshConversations();
    setMenuFor(null);
  }

  async function doDelete(conversationId: string) {
    if (!confirm("¿Eliminar este chat? (solo para tu usuario)")) return;
    await deleteConversation(conversationId);
    await refreshConversations();
    setMenuFor(null);

    if (activeConvId === conversationId) {
      setActiveConvId(null);
      setReports([]);
      setActiveReportId(null);
      setSelectedReportId(null);
      setTablesById({});
      setPagesById({});
    }
  }

  async function selectReport(reportId: string) {
    if (!activeConvId) return;
    await selectConversationReport(activeConvId, reportId);
    setSelectedReportId(reportId);
    await refreshConversations();
  }

  async function feedback(reportId: string, value: "up" | "down") {
    await sendFeedback(reportId, value);
    setReports((prev) =>
      prev.map((r) =>
        r.report_id === reportId
          ? { ...r, feedback: value === "up" ? "positive" : "negative" }
          : r
      )
    );
  }

  async function changePage(reportId: string, next: number) {
    setLoading(true);
    try {
      const data = await getReportData(reportId, next, pageSize);
      setTablesById((prev) => ({ ...prev, [reportId]: data }));
      setPagesById((prev) => ({ ...prev, [reportId]: next }));
    } finally {
      setLoading(false);
    }
  }

  // si cambias el tamaño de página, recarga todos los reportes visibles a página 1
  useEffect(() => {
    if (!activeConvId || reports.length === 0) return;
    setLoading(true);
    (async () => {
      try {
        const nextTables: Record<string, ReportData | null> = {};
        const nextPages: Record<string, number> = {};

        await Promise.all(
          reports.map(async (r) => {
            try {
              const data = await getReportData(r.report_id, 1, pageSize);
              nextTables[r.report_id] = data;
              nextPages[r.report_id] = 1;
            } catch {
              nextTables[r.report_id] = tablesById[r.report_id] ?? null;
              nextPages[r.report_id] = 1;
            }
          })
        );

        setTablesById(nextTables);
        setPagesById(nextPages);
      } finally {
        setLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pageSize]);

  const exportReportId = selectedReportId || activeReportId;
  const exportReportText =
    (exportReportId && reports.find((r) => r.report_id === exportReportId)?.nl) || null;

  const theme = getTheme();

  return (
    <div className="bg-gray-100 dark:bg-slate-950 overflow-hidden h-screen">
      <div
        className={`fixed inset-0 bg-black/50 z-30 transition-opacity lg:hidden ${overlayVisible ? "" : "hidden"}`}
        onClick={closeMenus}
      />

      <div className="ui-scale flex relative h-screen min-h-0">
        {/* LEFT */}
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
                      <li className="mb-3 relative min-w-0" key={c.conversation_id}>
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
                            className="text-lime-300 hover:text-lime-200"
                            title="Opciones"
                            type="button"
                          >
                            <span className="material-icons">more_vert</span>
                          </button>
                        </div>

                        {menuFor === c.conversation_id && (
                          <div className="absolute right-0 mt-2 w-40 bg-white text-gray-900 rounded-md shadow-lg z-50 overflow-hidden">
                            <button
                              className="w-full text-left px-3 py-2 hover:bg-gray-100"
                              onClick={() => doRename(c.conversation_id)}
                              type="button"
                            >
                              Renombrar
                            </button>
                            <button
                              className="w-full text-left px-3 py-2 hover:bg-gray-100 text-red-700"
                              onClick={() => doDelete(c.conversation_id)}
                              type="button"
                            >
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

        {/* MAIN */}
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

              <div className="w-10 h-10 rounded-full bg-gray-200 dark:bg-slate-700 flex items-center justify-center">
                <span className="material-icons text-gray-600 dark:text-slate-200">person</span>
              </div>
            </div>
          </header>

          <div className="flex-1 p-4 lg:p-6 pb-10 flex overflow-hidden min-h-0">
            {/* CENTER */}
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
                      const fb = r.feedback ?? null;

                      return (
                        <div key={r.report_id} className="space-y-3">
                          <button
                            onClick={async (e) => {
                              // ✅ quita el focus feo
                              (e.currentTarget as HTMLButtonElement).blur();
                              setActiveReportId(r.report_id);
                              await ensureReportLoaded(r.report_id);
                            }}
                            className={[
                              "w-full text-left bg-lime-200 dark:bg-slate-800 p-4 rounded-lg flex items-center justify-between",
                              "focus:outline-none focus-visible:outline-none",
                            ].join(" ")}
                            title={r.nl}
                            type="button"
                          >
                            <p className="text-lime-800 dark:text-slate-100 line-clamp-2">{r.nl}</p>
                            <div className="ml-4 flex items-center gap-2">
                              {isSelected && <span className="text-xs font-bold text-lime-900 dark:text-slate-200">SELECCIONADO</span>}
                              <span className="text-xs text-lime-900/80 dark:text-slate-300">{r.latency_ms}ms</span>
                            </div>
                          </button>

                          <div className="bg-white dark:bg-slate-900 dark:text-slate-50 shadow-md rounded-lg overflow-hidden">
                            <div className="flex items-center p-4">
                              <div className="bg-amber-300 rounded-full w-8 h-8 flex items-center justify-center font-bold text-amber-800 mr-4">
                                A
                              </div>
                              <div className="text-sm text-gray-600 dark:text-slate-300">
                                {t ? "Reporte cargado" : "Cargando reporte..."}
                              </div>
                            </div>

                            <div className="overflow-x-auto w-full">
                              <table className="w-full text-sm text-left text-gray-500 dark:text-slate-200 whitespace-nowrap lg:whitespace-normal">
                                <thead className="text-xs text-gray-700 dark:text-slate-200 uppercase bg-gray-50 dark:bg-slate-800">
                                  <tr>
                                    {(t?.columns || ["Sin datos"]).map((c) => (
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
                                  {t?.rows?.map((row, idx) => (
                                    <tr key={idx} className="bg-white dark:bg-slate-900 border-b dark:border-slate-800">
                                      {t.columns.map((c) => (
                                        <td key={c} className="px-6 py-4">
                                          {String((row as any)[c] ?? "")}
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
                                  value={pageSize}
                                  onChange={(e) => setPageSize(Number(e.target.value))}
                                >
                                  <option value={5}>5</option>
                                  <option value={10}>10</option>
                                  <option value={20}>20</option>
                                  <option value={50}>50</option>
                                </select>
                              </div>

                              <div className="flex items-center space-x-1">
                                <button
                                  className="p-2 text-gray-500 hover:text-gray-800 dark:text-slate-300 dark:hover:text-white disabled:opacity-50"
                                  disabled={!t || page <= 1 || loading}
                                  onClick={() => changePage(r.report_id, page - 1)}
                                  type="button"
                                >
                                  <span className="material-icons">chevron_left</span>
                                </button>

                                <div className="px-3 py-1 rounded-md bg-blue-500 text-white">{page}</div>

                                <button
                                  className="p-2 text-gray-500 hover:text-gray-800 dark:text-slate-300 dark:hover:text-white disabled:opacity-50"
                                  disabled={!t || t.row_count < t.page_size || loading}
                                  onClick={() => changePage(r.report_id, page + 1)}
                                  type="button"
                                >
                                  <span className="material-icons">chevron_right</span>
                                </button>
                              </div>
                            </div>

                            <div className="bg-lime-200 dark:bg-slate-800 px-4 py-3 flex items-center justify-between">
                              <button
                                onClick={() => selectReport(r.report_id)}
                                disabled={!activeConvId}
                                className="bg-lime-700 hover:bg-lime-800 dark:bg-slate-700 dark:hover:bg-slate-600 disabled:opacity-60 text-white px-4 py-2 rounded-md transition-colors"
                                type="button"
                              >
                                SELECCIONAR
                              </button>

                              <div className="flex items-center space-x-2">
                                <button
                                  onClick={() => feedback(r.report_id, "up")}
                                  className={[
                                    "transition-colors",
                                    fb === "positive"
                                      ? "text-lime-950 dark:text-slate-100"
                                      : "text-lime-700 hover:text-lime-900 dark:text-slate-300 dark:hover:text-white",
                                  ].join(" ")}
                                  aria-label="Me gusta"
                                  type="button"
                                >
                                  <span className="material-icons">thumb_up</span>
                                </button>

                                <button
                                  onClick={() => feedback(r.report_id, "down")}
                                  className={[
                                    "transition-colors",
                                    fb === "negative"
                                      ? "text-lime-950 dark:text-slate-100"
                                      : "text-lime-700 hover:text-lime-900 dark:text-slate-300 dark:hover:text-white",
                                  ].join(" ")}
                                  aria-label="No me gusta"
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
                ) : (
                  <div className="bg-white dark:bg-slate-900 dark:text-slate-50 shadow-md rounded-lg overflow-hidden">
                    <div className="flex items-center p-4">
                      <div className="bg-amber-300 rounded-full w-8 h-8 flex items-center justify-center font-bold text-amber-800 mr-4">
                        A
                      </div>
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
                )}
              </div>

              {/* input */}
              <div className="bg-lime-200 dark:bg-slate-800 p-4 mt-4 rounded-lg flex items-center justify-between shadow-sm">
                <input
                  className="bg-transparent outline-none flex-1 text-lime-900 dark:text-slate-100 placeholder:text-lime-800/70 dark:placeholder:text-slate-400"
                  placeholder="Consulta"
                  value={nl}
                  onChange={(e) => setNl(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") doQuery();
                  }}
                />
                <button
                  className="bg-lime-700 hover:bg-lime-800 dark:bg-slate-700 dark:hover:bg-slate-600 transition-colors p-2 rounded-full ml-4 flex items-center justify-center disabled:opacity-70"
                  onClick={doQuery}
                  disabled={loading}
                  type="button"
                >
                  <span className="material-icons text-white">send</span>
                </button>
              </div>
            </div>

            {/* RIGHT */}
            <aside
              className={[
                "w-80 bg-lime-300 dark:bg-slate-900 p-6 flex flex-col fixed inset-y-0 right-0 z-40 transform transition-transform duration-300",
                "lg:relative lg:translate-x-0 lg:rounded-lg overflow-y-auto shrink-0 scrollbar-subtle",
                rightOpen ? "translate-x-0" : "translate-x-full",
              ].join(" ")}
            >
              <div className="flex justify-between items-center mb-6">
                <h2 className="text-xl font-bold text-lime-800 dark:text-slate-100">Exportación del reporte generado</h2>
                <button
                  className="lg:hidden text-lime-800 dark:text-slate-200 hover:text-lime-900 dark:hover:text-white"
                  onClick={closeMenus}
                  type="button"
                >
                  <span className="material-icons">close</span>
                </button>
              </div>

              {/* ✅ texto del reporte seleccionado */}
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

                <div className="flex justify-between items-center py-2 hover:bg-lime-400/30 dark:hover:bg-slate-800 px-2 rounded cursor-pointer transition-colors opacity-60">
                  <span className="text-lime-800 dark:text-slate-200">Enviar por correo</span>
                  <button className="text-lime-800 dark:text-slate-200" type="button">
                    <span className="material-icons">send</span>
                  </button>
                </div>
              </div>
            </aside>
          </div>
        </main>
      </div>
    </div>
  );
}