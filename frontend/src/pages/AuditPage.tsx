import { useEffect, useState } from "react";
import { listAuditReports, type AuditList } from "../api";

type AuditStatus = "completed" | "failed" | "abandoned" | string;

type AuditRowExtra = {
  status?: AuditStatus | null;
  error?: string | null;
};

function statusLabel(status: AuditStatus | null | undefined) {
  if (status === "failed") return "Falló";
  if (status === "abandoned") return "Cancelado";
  return "Correcto";
}

function statusClass(status: AuditStatus | null | undefined) {
  if (status === "failed") return "bg-red-100 text-red-700 border-red-200 dark:bg-red-950/30 dark:text-red-200 dark:border-red-900";
  if (status === "abandoned") return "bg-amber-100 text-amber-800 border-amber-200 dark:bg-amber-950/30 dark:text-amber-200 dark:border-amber-900";
  return "bg-lime-100 text-lime-800 border-lime-200 dark:bg-lime-950/30 dark:text-lime-200 dark:border-lime-900";
}

export default function AuditPage() {
  const [data, setData] = useState<AuditList | null>(null);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [userId, setUserId] = useState("");
  const [err, setErr] = useState<string | null>(null);

  async function load(nextPage = page) {
    setErr(null);
    try {
      const res = await listAuditReports({
        page: nextPage,
        page_size: 20,
        q: q.trim() || null,
        user_id: userId.trim() ? Number(userId) : null,
      });
      setData(res);
      setPage(res.page);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "No se pudo cargar auditoría");
    }
  }

  useEffect(() => {
    load(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <>
       <section className="rounded-3xl bg-white dark:bg-slate-900 border border-cyan-100 dark:border-slate-800 p-6 shadow-xl shadow-cyan-950/10">
         <p className="text-sm uppercase tracking-[0.25em] text-[#0083B0] dark:text-lime-300 font-bold">Auditoría</p>
         <h2 className="text-3xl font-bold text-slate-900 dark:text-white">Preguntas realizadas</h2>
         <p className="text-slate-500 dark:text-slate-400 mt-1">
           Permite ver quién realizó preguntas, qué preguntó, si se generó correctamente y, si falló, el motivo registrado.
         </p>
       </section>

      <section className="mt-6 rounded-2xl bg-[#C6EB32] dark:bg-slate-900 border border-lime-200 dark:border-slate-800 p-4 shadow-xl shadow-cyan-950/10">
        <div className="flex flex-wrap gap-3 items-center">
          <div className="relative flex-1 min-w-64">
            <span className="material-icons absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">search</span>
            <input
              className="w-full pl-10 pr-3 py-2.5 rounded-lg border border-cyan-100 dark:border-slate-700 bg-white dark:bg-slate-950 focus:outline-none focus:ring-2 focus:ring-[#0083B0]"
              placeholder="Buscar pregunta, usuario, perfil o error"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>
          <input
             className="px-3 py-2.5 rounded-lg border border-cyan-100 dark:border-slate-700 bg-white dark:bg-slate-950 w-36 focus:outline-none focus:ring-2 focus:ring-[#0083B0]"
             placeholder="ID usuario"
             value={userId}
             onChange={(e) => setUserId(e.target.value.replace(/\D/g, ""))}
          />
          <button className="px-5 py-2.5 rounded-lg bg-[#0083B0] hover:bg-[#006a90] text-white font-bold transition" onClick={() => load(1)} type="button">
             Filtrar
          </button>
        </div>
      </section>

      {err && <div className="mt-4 p-3 rounded-lg bg-red-100 text-red-700 border border-red-200">{err}</div>}

      <section className="mt-6 rounded-2xl bg-white dark:bg-slate-900 border border-cyan-100 dark:border-slate-800 overflow-hidden shadow-xl shadow-cyan-950/10">
         <div className="p-4 border-b border-cyan-100 dark:border-slate-800 flex items-center justify-between gap-3 flex-wrap">
           <div className="flex items-center gap-2">
             <span className="material-icons text-[#0083B0] dark:text-lime-300">manage_search</span>
             <p className="font-bold">{data?.total_count ?? 0} registros</p>
           </div>
           <div className="flex gap-2 items-center">
             <button
               className="px-3 py-2 rounded-lg bg-cyan-50 hover:bg-cyan-100 dark:bg-slate-800 dark:hover:bg-slate-700 disabled:opacity-40 font-semibold"
               disabled={!data || page <= 1}
               onClick={() => load(page - 1)}
               type="button"
             >
               Anterior
             </button>
             <span className="px-2 py-1 text-sm text-slate-500 dark:text-slate-400">
               Página {data?.page ?? 1} de {data?.total_pages ?? 1}
             </span>
             <button
               className="px-3 py-2 rounded-lg bg-cyan-50 hover:bg-cyan-100 dark:bg-slate-800 dark:hover:bg-slate-700 disabled:opacity-40 font-semibold"
               disabled={!data || page >= data.total_pages}
               onClick={() => load(page + 1)}
               type="button"
             >
               Siguiente
             </button>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm align-top">
            <thead className="bg-[#0083B0] text-white text-left">
              <tr>
                 <th className="p-3">Fecha</th>
                 <th className="p-3">Usuario</th>
                 <th className="p-3">Estado</th>
                 <th className="p-3">Pregunta</th>
                 <th className="p-3">SQL / error</th>
                 <th className="p-3">Latencia</th>
              </tr>
            </thead>
            <tbody>
              {data?.rows.map((r) => {
                const extra = r as typeof r & AuditRowExtra;
                const status = extra.status || "completed";
                const failed = status === "failed" || status === "abandoned";
                return (
                 <tr key={r.report_id} className="border-t border-cyan-100 dark:border-slate-800">
                   <td className="p-3 whitespace-nowrap text-slate-600 dark:text-slate-300">{new Date(r.timestamp).toLocaleString()}</td>
                   <td className="p-3">
                     <div className="font-bold text-slate-900 dark:text-white">{r.full_name || r.username || `ID ${r.user_id}`}</div>
                     <div className="text-xs text-slate-500 dark:text-slate-400">
                        {r.full_name && r.username && r.full_name.trim().toLowerCase() !== r.username.trim().toLowerCase()
                          ? `@${r.username} · `
                          : ""}
                        Perfil: {r.profile || "sin perfil"}
                     </div>
                   </td>
                   <td className="p-3 whitespace-nowrap">
                     <span className={["inline-flex rounded-full border px-2.5 py-1 text-xs font-bold", statusClass(status)].join(" ")}>
                       {statusLabel(status)}
                     </span>
                   </td>
                   <td className="p-3 min-w-80 text-slate-700 dark:text-slate-300">{r.nl}</td>
                   <td className="p-3 min-w-96">
                     {failed ? (
                        <pre className="whitespace-pre-wrap text-xs bg-red-50 dark:bg-red-950/20 text-red-800 dark:text-red-200 rounded-lg p-3 max-h-40 overflow-auto border border-red-100 dark:border-red-900">
                          {extra.error || "La generación falló sin detalle adicional."}
                        </pre>
                     ) : r.sql ? (
                        <pre className="whitespace-pre-wrap text-xs bg-cyan-50 dark:bg-slate-950 rounded-lg p-3 max-h-40 overflow-auto border border-cyan-100 dark:border-slate-800">
                          {r.sql}
                        </pre>
                     ) : (
                        <span className="text-slate-500">Oculto por permisos</span>
                     )}
                   </td>
                   <td className="p-3 whitespace-nowrap font-semibold text-[#0083B0] dark:text-lime-300">{r.latency_ms} ms</td>
                 </tr>
                );
              })}

              {(!data || data.rows.length === 0) && (
                <tr>
                  <td colSpan={6} className="p-6 text-center text-slate-500">
                    Sin resultados.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
