import { useMemo, useState } from "react";
import { clearToken } from "../auth";
import { downloadExport, runQuery, sendFeedback } from "../api";
import type { QueryResponse } from "../api";
import { getTheme, toggleTheme } from "../theme";

type HistoryItem = { nl: string; at: number; reportId?: string };

const HISTORY_KEY = "empresa_reports_history";

function loadHistory(): HistoryItem[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    const arr = raw ? (JSON.parse(raw) as HistoryItem[]) : [];
    return Array.isArray(arr) ? arr : [];
  } catch {
    return [];
  }
}
function saveHistory(items: HistoryItem[]) {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(items.slice(0, 50)));
}

function dayDiff(a: number, b: number) {
  const A = new Date(a); const B = new Date(b);
  A.setHours(0,0,0,0); B.setHours(0,0,0,0);
  return Math.round((B.getTime() - A.getTime()) / 86400000);
}

export default function Dashboard() {
  const [leftOpen, setLeftOpen] = useState(false);
  const [rightOpen, setRightOpen] = useState(false);

  const [nl, setNl] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [data, setData] = useState<QueryResponse | null>(null);
  const [pageSize, setPageSize] = useState(10);

  const [history, setHistory] = useState<HistoryItem[]>(() => loadHistory());

  const grouped = useMemo(() => {
    const now = Date.now();
    const ayer: HistoryItem[] = [];
    const semana: HistoryItem[] = [];
    const mes: HistoryItem[] = [];
    for (const it of history) {
      const d = dayDiff(it.at, now);
      if (d <= 1) ayer.push(it);
      else if (d <= 7) semana.push(it);
      else mes.push(it);
    }
    return { ayer, semana, mes };
  }, [history]);

  const overlayVisible = leftOpen || rightOpen;

  const closeMenus = () => {
    setLeftOpen(false);
    setRightOpen(false);
  };

  const onNewReport = () => {
    setData(null);
    setNl("");
    setErr(null);
  };

  const doQuery = async (text: string, page: number) => {
    setErr(null);
    setLoading(true);
    try {
      const res = await runQuery(text, page, pageSize);
      setData(res);

      const item: HistoryItem = { nl: text, at: Date.now(), reportId: res.report_id };
      const next = [item, ...history];
      setHistory(next);
      saveHistory(next);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Error al generar reporte");
    } finally {
      setLoading(false);
    }
  };

  const onSend = () => {
    const text = nl.trim();
    if (!text) return;
    doQuery(text, 1);
  };

  const onHistoryClick = (text: string) => {
    setNl(text);
    doQuery(text, 1);
    closeMenus();
  };

  const theme = getTheme(); // para “pasar” el estado actual

  return (
    <div className="bg-gray-100 dark:bg-slate-950 overflow-hidden">
      {/* Overlay móvil */}
      <div
        className={`fixed inset-0 bg-black/50 z-30 transition-opacity lg:hidden ${overlayVisible ? "" : "hidden"}`}
        onClick={closeMenus}
      />

      <div className="ui-scale flex relative">
        {/* Left sidebar */}
        <aside
          className={[
            "w-64 text-white p-4 flex flex-col h-full fixed inset-y-0 left-0 z-40 transform transition-transform duration-300",
            "lg:relative lg:translate-x-0",
            leftOpen ? "translate-x-0" : "-translate-x-full",
            // SOLO colores mejorados (sin cambiar estructura)
            "bg-[#007aa3] dark:bg-slate-900",
          ].join(" ")}
        >
          <div className="flex justify-between items-center mb-8">
            <h1 className="text-2xl font-bold">empresa REPORTS</h1>
            <button className="lg:hidden text-white hover:text-cyan-200" onClick={closeMenus}>
              <span className="material-icons">close</span>
            </button>
          </div>

          <button
            onClick={onNewReport}
            className="font-bold py-2 px-4 rounded-lg flex items-center mb-6 w-full bg-[#006a90] hover:bg-[#005c7d] dark:bg-slate-800 dark:hover:bg-slate-700"
          >
            <span className="material-icons mr-2">add</span>
            Nuevo reporte
          </button>

          <nav className="flex-grow overflow-y-auto">
            <h2 className="text-sm font-semibold text-cyan-100 uppercase mb-4">Ayer</h2>
            <ul>
              {grouped.ayer.map((it, idx) => (
                <li className="mb-3" key={`a-${idx}`}>
                  <button
                    onClick={() => onHistoryClick(it.nl)}
                    className="w-full text-left flex items-center text-cyan-50 hover:text-white"
                    title={it.nl}
                  >
                    <span className="material-icons mr-3">bar_chart</span>
                    <span className="truncate">{it.nl}</span>
                  </button>
                </li>
              ))}
              {grouped.ayer.length === 0 && (
                <li className="text-cyan-100 text-sm opacity-80">Sin reportes</li>
              )}
            </ul>

            <h2 className="text-sm font-semibold text-cyan-100 uppercase mt-8 mb-4">Última semana</h2>
            <ul>
              {grouped.semana.map((it, idx) => (
                <li className="mb-3" key={`s-${idx}`}>
                  <button
                    onClick={() => onHistoryClick(it.nl)}
                    className="w-full text-left flex items-center text-cyan-50 hover:text-white"
                    title={it.nl}
                  >
                    <span className="material-icons mr-3">chat_bubble_outline</span>
                    <span className="truncate">{it.nl}</span>
                  </button>
                </li>
              ))}
              {grouped.semana.length === 0 && (
                <li className="text-cyan-100 text-sm opacity-80">Sin reportes</li>
              )}
            </ul>

            <h2 className="text-sm font-semibold text-cyan-100 uppercase mt-8 mb-4">Último mes</h2>
            <ul>
              {grouped.mes.map((it, idx) => (
                <li className="mb-3" key={`m-${idx}`}>
                  <button
                    onClick={() => onHistoryClick(it.nl)}
                    className="w-full text-left flex items-center text-cyan-50 hover:text-white"
                    title={it.nl}
                  >
                    <span className="material-icons mr-3">science</span>
                    <span className="truncate">{it.nl}</span>
                  </button>
                </li>
              ))}
              {grouped.mes.length === 0 && (
                <li className="text-cyan-100 text-sm opacity-80">Sin reportes</li>
              )}
            </ul>
          </nav>
        </aside>

        {/* Main */}
        <main className="flex-1 flex flex-col h-full min-w-0">
          <header className="bg-white dark:bg-slate-900 dark:text-slate-50 shadow-sm p-4 flex justify-between lg:justify-end items-center z-10">
            <button
              className="lg:hidden text-gray-600 hover:text-gray-900 dark:text-slate-200 dark:hover:text-white focus:outline-none"
              onClick={() => {
                setLeftOpen(true);
                setRightOpen(false);
              }}
            >
              <span className="material-icons text-3xl">menu</span>
            </button>

            <div className="flex items-center space-x-4">
              <button
                className="lg:hidden text-gray-600 hover:text-lime-700 dark:text-slate-200 dark:hover:text-lime-300 focus:outline-none"
                onClick={() => {
                  setRightOpen(true);
                  setLeftOpen(false);
                }}
                title="Exportar"
              >
                <span className="material-icons text-3xl">file_download</span>
              </button>

              <button
                onClick={() => toggleTheme()}
                className="text-gray-600 hover:text-gray-900 dark:text-slate-200 dark:hover:text-white"
                title={`Tema: ${theme}`}
              >
                <span className="material-icons">brightness_6</span>
              </button>

              <button
                onClick={() => {
                  clearToken();
                  window.location.href = "/login";
                }}
                className="text-gray-600 hover:text-gray-900 dark:text-slate-200 dark:hover:text-white"
                title="Cerrar sesión"
              >
                <span className="material-icons">logout</span>
              </button>

              <div className="w-10 h-10 rounded-full bg-gray-200 dark:bg-slate-700 flex items-center justify-center">
                <span className="material-icons text-gray-600 dark:text-slate-200">person</span>
              </div>
            </div>
          </header>

          <div className="flex-1 p-4 lg:p-6 pb-10 flex overflow-hidden">
            {/* Center column */}
            <div className="flex-1 flex flex-col lg:mr-6 min-h-0 min-w-0">
              <div className="flex-1 overflow-y-auto min-h-0">
                {/* Bubble consulta */}
                {data && (
                  <div className="bg-lime-200 dark:bg-lime-300 p-4 rounded-lg flex items-center justify-between mb-4">
                    <p className="text-lime-800">
                      {nl || "Consulta ejecutada"}
                    </p>
                    <div className="flex items-center ml-4">
                      <div className="w-8 h-8 rounded-full bg-lime-700 flex items-center justify-center text-white font-bold">
                        U
                      </div>
                    </div>
                  </div>
                )}

                {/* Tabla */}
                <div className="bg-white dark:bg-slate-900 dark:text-slate-50 shadow-md rounded-lg overflow-hidden">
                  <div className="flex items-center p-4">
                    <div className="bg-amber-300 rounded-full w-8 h-8 flex items-center justify-center font-bold text-amber-800 mr-4">
                      A
                    </div>
                    <div className="text-sm text-gray-600 dark:text-slate-300">
                      {data ? (
                        <>
                          <span className="font-medium">latencia:</span> {data.latency_ms} ms{" "}
                          <span className="mx-2">•</span>
                          <span className="font-medium">SQL:</span>{" "}
                          <span className="break-all">{data.sql}</span>
                        </>
                      ) : (
                        "Genera un reporte escribiendo tu consulta abajo."
                      )}
                    </div>
                  </div>

                  {err && (
                    <div className="px-4 pb-4">
                      <div className="text-sm text-red-700 bg-red-100 rounded-md p-2">{err}</div>
                    </div>
                  )}

                  <div className="overflow-x-auto w-full">
                    <table className="w-full text-sm text-left text-gray-500 dark:text-slate-200 whitespace-nowrap lg:whitespace-normal">
                      <thead className="text-xs text-gray-700 dark:text-slate-200 uppercase bg-gray-50 dark:bg-slate-800">
                        <tr>
                          {(data?.columns || ["N°", "ID", "Campo", "Valor"]).map((c) => (
                            <th key={c} className="px-6 py-3" scope="col">
                              {c}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {!data && (
                          <tr className="bg-white dark:bg-slate-900 border-b dark:border-slate-800">
                            <td className="px-6 py-4" colSpan={4}>
                              Sin resultados todavía.
                            </td>
                          </tr>
                        )}

                        {data?.rows?.map((r, idx) => (
                          <tr
                            key={idx}
                            className="bg-white dark:bg-slate-900 border-b dark:border-slate-800"
                          >
                            {data.columns.map((c) => (
                              <td key={c} className="px-6 py-4">
                                {String((r as any)[c] ?? "")}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {/* Paginación */}
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
                        disabled={!data || data.page <= 1 || loading}
                        onClick={() => data && doQuery(nl, data.page - 1)}
                      >
                        <span className="material-icons">chevron_left</span>
                      </button>

                      <div className="px-3 py-1 rounded-md bg-blue-500 text-white">
                        {data?.page ?? 1}
                      </div>

                      <button
                        className="p-2 text-gray-500 hover:text-gray-800 dark:text-slate-300 dark:hover:text-white disabled:opacity-50"
                        disabled={!data || (data.row_count < data.page_size) || loading}
                        onClick={() => data && doQuery(nl, data.page + 1)}
                      >
                        <span className="material-icons">chevron_right</span>
                      </button>
                    </div>
                  </div>

                  {/* Barra inferior (feedback) */}
                  <div className="bg-lime-200 dark:bg-lime-300 px-4 py-3 flex items-center justify-between">
                    <button className="bg-lime-700 hover:bg-lime-800 text-white px-4 py-2 rounded-md transition-colors">
                      SELECCIONAR
                    </button>
                    <div className="flex items-center space-x-2">
                      <button
                        className="text-lime-700 hover:text-lime-900 transition-colors disabled:opacity-50"
                        disabled={!data}
                        onClick={async () => data && sendFeedback(data.report_id, "up")}
                        aria-label="Me gusta"
                      >
                        <span className="material-icons">thumb_up</span>
                      </button>
                      <button
                        className="text-lime-700 hover:text-lime-900 transition-colors disabled:opacity-50"
                        disabled={!data}
                        onClick={async () => data && sendFeedback(data.report_id, "down")}
                        aria-label="No me gusta"
                      >
                        <span className="material-icons">thumb_down</span>
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              {/* Input consulta */}
              <div className="bg-lime-200 dark:bg-lime-300 p-4 mt-4 rounded-lg flex items-center justify-between shadow-sm">
                <input
                  className="bg-transparent outline-none flex-1 text-lime-900 placeholder:text-lime-800/70"
                  placeholder="Consulta"
                  value={nl}
                  onChange={(e) => setNl(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") onSend();
                  }}
                />
                <button
                  className="bg-lime-700 hover:bg-lime-800 transition-colors p-2 rounded-full ml-4 flex items-center justify-center disabled:opacity-70"
                  onClick={onSend}
                  disabled={loading}
                >
                  <span className="material-icons text-white">send</span>
                </button>
              </div>
            </div>

            {/* Right sidebar */}
            <aside
              className={[
                "w-80 p-6 flex flex-col fixed inset-y-0 right-0 z-40 transform transition-transform duration-300",
                "lg:relative lg:translate-x-0 lg:rounded-lg overflow-y-auto shrink-0",
                rightOpen ? "translate-x-0" : "translate-x-full",
                "bg-lime-300 dark:bg-slate-900",
              ].join(" ")}
            >
              <div className="flex justify-between items-center mb-6">
                <h2 className="text-xl font-bold text-lime-800 dark:text-lime-200">
                  Exportación del reporte generado
                </h2>
                <button
                  className="lg:hidden text-lime-800 hover:text-lime-900 dark:text-lime-200 dark:hover:text-lime-100"
                  onClick={closeMenus}
                >
                  <span className="material-icons">close</span>
                </button>
              </div>

              <div className="space-y-4">
                <div className="font-semibold text-lime-800 dark:text-lime-200">Exportar</div>

                {(["csv", "xlsx", "pdf"] as const).map((fmt) => (
                  <div
                    key={fmt}
                    className="flex justify-between items-center py-2 border-b border-lime-400 dark:border-slate-800 hover:bg-lime-400/30 dark:hover:bg-slate-800 px-2 rounded cursor-pointer transition-colors"
                    onClick={async () => {
                      if (!data) return;
                      await downloadExport(data.report_id, fmt);
                    }}
                    title={data ? `Descargar ${fmt}` : "Genera un reporte primero"}
                  >
                    <span className="text-lime-800 dark:text-lime-200">
                      {fmt === "csv" ? "CSV" : fmt === "xlsx" ? "Excel" : "PDF"}
                    </span>
                    <button className="text-lime-800 dark:text-lime-200">
                      <span className="material-icons">file_download</span>
                    </button>
                  </div>
                ))}

                <div className="flex justify-between items-center py-2 hover:bg-lime-400/30 dark:hover:bg-slate-800 px-2 rounded cursor-pointer transition-colors opacity-60">
                  <span className="text-lime-800 dark:text-lime-200">Enviar por correo</span>
                  <button className="text-lime-800 dark:text-lime-200">
                    <span className="material-icons">send</span>
                  </button>
                </div>

                <div className="text-xs text-lime-800/80 dark:text-slate-400 mt-2">
                  (Envío por correo lo conectamos después cuando implementemos ese endpoint.)
                </div>
              </div>
            </aside>
          </div>
        </main>
      </div>
    </div>
  );
}