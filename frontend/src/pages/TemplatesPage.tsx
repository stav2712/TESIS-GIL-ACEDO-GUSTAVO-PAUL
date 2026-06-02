import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import {
  createPlatformTemplate,
  deletePlatformTemplate,
  forkPlatformTemplate,
  listPlatformTemplates,
  recordPlatformTemplateUse,
  startQueryJob,
  updatePlatformTemplate,
  type PlatformTemplate,
  type TemplateStatus,
  type TemplateVisibility,
} from "../api";
import { getAuthUser } from "../auth";

const PENDING_JOB_KEY = "empresa_reports_pending_query_job_v2";
const DEFAULT_PAGE_SIZE = 10;

type Draft = {
  template_id?: string;
  title: string;
  description: string;
  nl: string;
  tagsText: string;
  visibility: TemplateVisibility;
  status: TemplateStatus;
};

const emptyDraft: Draft = {
  title: "",
  description: "",
  nl: "",
  tagsText: "",
  visibility: "private",
  status: "published",
};

function tagsFromText(value: string) {
  return value
    .split(",")
    .map((tag) => tag.trim().toLowerCase())
    .filter(Boolean)
    .slice(0, 10);
}

function draftFromTemplate(template: PlatformTemplate): Draft {
  return {
    template_id: template.template_id,
    title: template.title,
    description: template.description ?? "",
    nl: template.nl,
    tagsText: template.tags.join(", "),
    visibility: template.visibility,
    status: template.status,
  };
}

function templateOwner(template: PlatformTemplate) {
  return template.owner_full_name || template.owner_username || `Usuario ${template.owner_user_id}`;
}

function Badge({ children }: { children: string }) {
  return (
    <span className="inline-flex items-center rounded-full bg-cyan-50 dark:bg-slate-800 px-2.5 py-1 text-xs font-bold text-[#006a90] dark:text-lime-300 border border-cyan-100 dark:border-slate-700">
      {children}
    </span>
  );
}

export default function TemplatesPage() {
  const navigate = useNavigate();
  const user = getAuthUser();
  const [templates, setTemplates] = useState<PlatformTemplate[]>([]);
  const [q, setQ] = useState("");
  const [mine, setMine] = useState(false);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [editing, setEditing] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [runningId, setRunningId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const allTags = useMemo(() => {
    const tags = new Set<string>();
    templates.forEach((template) => template.tags.forEach((tag) => tags.add(tag)));
    return Array.from(tags).sort();
  }, [templates]);

  async function load() {
    setLoading(true);
    setErr(null);
    try {
      const data = await listPlatformTemplates({ q, mine });
      setTemplates(data.rows);
    } catch (error) {
      setErr(error instanceof Error ? error.message : "No se pudo cargar el catálogo");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function startCreate() {
    setDraft(emptyDraft);
    setEditing(true);
    setMessage(null);
    setErr(null);
  }

  function startEdit(template: PlatformTemplate) {
    setDraft(draftFromTemplate(template));
    setEditing(true);
    setMessage(null);
    setErr(null);
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setErr(null);
    setMessage(null);

    const payload = {
      title: draft.title.trim(),
      description: draft.description.trim() || null,
      nl: draft.nl.trim(),
      tags: tagsFromText(draft.tagsText),
      visibility: draft.visibility,
      status: draft.status,
    };

    try {
      if (draft.template_id) {
        await updatePlatformTemplate(draft.template_id, payload);
        setMessage("Plantilla actualizada.");
      } else {
        await createPlatformTemplate(payload);
        setMessage("Plantilla creada.");
      }
      setEditing(false);
      setDraft(emptyDraft);
      await load();
    } catch (error) {
      setErr(error instanceof Error ? error.message : "No se pudo guardar la plantilla");
    } finally {
      setSaving(false);
    }
  }

  async function remove(template: PlatformTemplate) {
    const ok = window.confirm(`¿Eliminar la plantilla "${template.title}"?`);
    if (!ok) return;

    setErr(null);
    setMessage(null);
    try {
      await deletePlatformTemplate(template.template_id);
      setMessage("Plantilla eliminada.");
      await load();
    } catch (error) {
      setErr(error instanceof Error ? error.message : "No se pudo eliminar la plantilla");
    }
  }

  async function fork(template: PlatformTemplate) {
    setErr(null);
    setMessage(null);
    try {
      await forkPlatformTemplate(template.template_id);
      setMessage("Se creó una copia privada.");
      await load();
    } catch (error) {
      setErr(error instanceof Error ? error.message : "No se pudo copiar la plantilla");
    }
  }

  async function runTemplate(template: PlatformTemplate) {
    setRunningId(template.template_id);
    setErr(null);
    setMessage(null);

    try {
      const pageSize = Math.min(user?.max_page_size ?? DEFAULT_PAGE_SIZE, 50);
      const job = await startQueryJob(template.nl, null, 1, pageSize);
      localStorage.setItem(
        PENDING_JOB_KEY,
        JSON.stringify({
          job_id: job.job_id,
          conversation_id: job.conversation_id,
          nl: template.nl,
          started_at: new Date().toISOString(),
        })
      );
      recordPlatformTemplateUse(template.template_id).catch(() => undefined);
      navigate("/consultas");
    } catch (error) {
      setErr(error instanceof Error ? error.message : "No se pudo ejecutar la plantilla");
    } finally {
      setRunningId(null);
    }
  }

  async function copyPrompt(template: PlatformTemplate) {
    try {
      await navigator.clipboard.writeText(template.nl);
      setMessage("Consulta copiada al portapapeles.");
    } catch {
      setErr("No se pudo copiar automáticamente. Selecciona el texto manualmente.");
    }
  }

  return (
    <>
      <section className="rounded-3xl bg-[#C6EB32] dark:bg-slate-900 border border-lime-200 dark:border-slate-700 p-6 lg:p-8 shadow-xl shadow-cyan-950/20 overflow-hidden relative">
        <div className="absolute -right-16 -top-16 w-48 h-48 rounded-full bg-white/25 dark:bg-white/5" />
        <div className="relative flex flex-col lg:flex-row gap-5 lg:items-center lg:justify-between">
          <div>
            <p className="text-sm uppercase tracking-[0.3em] text-[#006a90] dark:text-lime-300 font-bold">Catálogo</p>
            <h2 className="text-3xl lg:text-4xl font-bold mt-2 text-[#005f80] dark:text-white">Plantillas de consulta</h2>
            <p className="text-[#005f80]/90 dark:text-slate-300 mt-3 max-w-3xl font-medium">
              Guarda consultas frecuentes, compártelas con el equipo y ejecútalas sin volver a escribir la pregunta.
            </p>
          </div>
          <button
            onClick={startCreate}
            className="inline-flex items-center justify-center gap-2 px-5 py-3 rounded-lg bg-[#0083B0] hover:bg-[#006a90] text-white font-bold transition"
            type="button"
          >
            <span className="material-icons">add</span>
            Nueva plantilla
          </button>
        </div>
      </section>

      <section className="mt-6 rounded-2xl bg-white dark:bg-slate-900 border border-cyan-100 dark:border-slate-800 p-4 shadow-xl shadow-cyan-950/10">
        <div className="flex flex-col lg:flex-row gap-3 lg:items-center">
          <div className="relative flex-1">
            <span className="material-icons absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">search</span>
            <input
              className="w-full pl-10 pr-3 py-2.5 rounded-lg border border-cyan-100 dark:border-slate-700 bg-white dark:bg-slate-950 focus:outline-none focus:ring-2 focus:ring-[#0083B0]"
              placeholder="Buscar por título, etiqueta o consulta"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") load();
              }}
            />
          </div>
          <label className="inline-flex items-center gap-2 text-sm font-bold text-slate-600 dark:text-slate-300">
            <input
              type="checkbox"
              checked={mine}
              onChange={(e) => setMine(e.target.checked)}
              className="h-4 w-4 rounded border-cyan-200"
            />
            Solo mis plantillas
          </label>
          <button
            className="px-5 py-2.5 rounded-lg bg-[#0083B0] hover:bg-[#006a90] text-white font-bold transition"
            onClick={() => load()}
            type="button"
          >
            Filtrar
          </button>
        </div>
        {allTags.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {allTags.slice(0, 14).map((tag) => (
              <button
                key={tag}
                onClick={() => {
                  setQ(tag);
                  setTimeout(() => load(), 0);
                }}
                className="rounded-full bg-cyan-50 hover:bg-cyan-100 dark:bg-slate-800 dark:hover:bg-slate-700 px-3 py-1 text-xs font-bold text-[#006a90] dark:text-lime-300"
                type="button"
              >
                #{tag}
              </button>
            ))}
          </div>
        )}
      </section>

      {err && <div className="mt-4 p-3 rounded-lg bg-red-100 text-red-700 border border-red-200">{err}</div>}
      {message && <div className="mt-4 p-3 rounded-lg bg-lime-100 text-lime-800 border border-lime-200">{message}</div>}

      {editing && (
        <section className="mt-6 rounded-2xl bg-white dark:bg-slate-900 border border-cyan-100 dark:border-slate-800 p-6 shadow-xl shadow-cyan-950/10">
          <div className="flex items-center justify-between gap-3 mb-4">
            <h3 className="text-xl font-bold text-slate-900 dark:text-white">
              {draft.template_id ? "Editar plantilla" : "Nueva plantilla"}
            </h3>
            <button
              onClick={() => {
                setEditing(false);
                setDraft(emptyDraft);
              }}
              className="w-9 h-9 rounded-full bg-cyan-50 dark:bg-slate-800 hover:bg-cyan-100 dark:hover:bg-slate-700 flex items-center justify-center"
              type="button"
            >
              <span className="material-icons text-[20px]">close</span>
            </button>
          </div>

          <form className="grid grid-cols-1 lg:grid-cols-2 gap-4" onSubmit={save}>
            <label className="block">
              <span className="text-sm font-bold text-slate-600 dark:text-slate-300">Título</span>
              <input
                className="mt-1 w-full px-3 py-2.5 rounded-lg border border-cyan-100 dark:border-slate-700 bg-white dark:bg-slate-950 focus:outline-none focus:ring-2 focus:ring-[#0083B0]"
                value={draft.title}
                onChange={(e) => setDraft((current) => ({ ...current, title: e.target.value }))}
                maxLength={90}
                required
              />
            </label>

            <label className="block">
              <span className="text-sm font-bold text-slate-600 dark:text-slate-300">Etiquetas separadas por coma</span>
              <input
                className="mt-1 w-full px-3 py-2.5 rounded-lg border border-cyan-100 dark:border-slate-700 bg-white dark:bg-slate-950 focus:outline-none focus:ring-2 focus:ring-[#0083B0]"
                value={draft.tagsText}
                onChange={(e) => setDraft((current) => ({ ...current, tagsText: e.target.value }))}
                placeholder="ej. pacientes, medicamentos, mensual"
              />
            </label>

            <label className="block lg:col-span-2">
              <span className="text-sm font-bold text-slate-600 dark:text-slate-300">Descripción</span>
              <input
                className="mt-1 w-full px-3 py-2.5 rounded-lg border border-cyan-100 dark:border-slate-700 bg-white dark:bg-slate-950 focus:outline-none focus:ring-2 focus:ring-[#0083B0]"
                value={draft.description}
                onChange={(e) => setDraft((current) => ({ ...current, description: e.target.value }))}
                maxLength={300}
              />
            </label>

            <label className="block lg:col-span-2">
              <span className="text-sm font-bold text-slate-600 dark:text-slate-300">Consulta en lenguaje natural</span>
              <textarea
                className="mt-1 w-full min-h-32 px-3 py-2.5 rounded-lg border border-cyan-100 dark:border-slate-700 bg-white dark:bg-slate-950 focus:outline-none focus:ring-2 focus:ring-[#0083B0]"
                value={draft.nl}
                onChange={(e) => setDraft((current) => ({ ...current, nl: e.target.value }))}
                maxLength={2000}
                required
              />
            </label>

            <label className="block">
              <span className="text-sm font-bold text-slate-600 dark:text-slate-300">Visibilidad</span>
              <select
                className="mt-1 w-full px-3 py-2.5 rounded-lg border border-cyan-100 dark:border-slate-700 bg-white dark:bg-slate-950 focus:outline-none focus:ring-2 focus:ring-[#0083B0]"
                value={draft.visibility}
                onChange={(e) => setDraft((current) => ({ ...current, visibility: e.target.value as TemplateVisibility }))}
              >
                <option value="private">Privada</option>
                <option value="shared">Compartida</option>
              </select>
            </label>

            <label className="block">
              <span className="text-sm font-bold text-slate-600 dark:text-slate-300">Estado</span>
              <select
                className="mt-1 w-full px-3 py-2.5 rounded-lg border border-cyan-100 dark:border-slate-700 bg-white dark:bg-slate-950 focus:outline-none focus:ring-2 focus:ring-[#0083B0]"
                value={draft.status}
                onChange={(e) => setDraft((current) => ({ ...current, status: e.target.value as TemplateStatus }))}
              >
                <option value="published">Publicada</option>
                <option value="draft">Borrador</option>
              </select>
            </label>

            <div className="lg:col-span-2 flex justify-end gap-3">
              <button
                type="button"
                onClick={() => {
                  setEditing(false);
                  setDraft(emptyDraft);
                }}
                className="px-5 py-2.5 rounded-lg bg-cyan-50 hover:bg-cyan-100 dark:bg-slate-800 dark:hover:bg-slate-700 font-bold transition"
              >
                Cancelar
              </button>
              <button
                type="submit"
                disabled={saving || !draft.title.trim() || !draft.nl.trim()}
                className="px-5 py-2.5 rounded-lg bg-[#0083B0] hover:bg-[#006a90] disabled:opacity-60 text-white font-bold transition"
              >
                {saving ? "Guardando..." : "Guardar"}
              </button>
            </div>
          </form>
        </section>
      )}

      <section className="mt-6 grid grid-cols-1 lg:grid-cols-2 gap-4">
        {loading ? (
          <div className="lg:col-span-2 rounded-2xl bg-white dark:bg-slate-900 border border-cyan-100 dark:border-slate-800 p-8 text-center text-slate-500 dark:text-slate-400">
            Cargando plantillas...
          </div>
        ) : templates.length === 0 ? (
          <div className="lg:col-span-2 rounded-2xl bg-white dark:bg-slate-900 border border-cyan-100 dark:border-slate-800 p-8 text-center text-slate-500 dark:text-slate-400">
            No hay plantillas para mostrar.
          </div>
        ) : (
          templates.map((template) => (
            <article key={template.template_id} className="rounded-2xl bg-white dark:bg-slate-900 border border-cyan-100 dark:border-slate-800 p-5 shadow-lg shadow-cyan-950/10">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="font-bold text-lg text-slate-900 dark:text-white break-words">{template.title}</h3>
                    <Badge>{template.visibility === "shared" ? "Compartida" : "Privada"}</Badge>
                    {template.status === "draft" && <Badge>Borrador</Badge>}
                  </div>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                    {templateOwner(template)} · Usos: {template.use_count} · Copias: {template.fork_count}
                  </p>
                </div>
                <span className="material-icons text-[#0083B0] dark:text-lime-300">article</span>
              </div>

              {template.description && <p className="mt-3 text-sm text-slate-600 dark:text-slate-300">{template.description}</p>}

              <div className="mt-4 rounded-xl bg-cyan-50 dark:bg-slate-950 border border-cyan-100 dark:border-slate-800 p-3">
                <p className="text-xs uppercase tracking-[0.2em] font-bold text-[#006a90] dark:text-lime-300 mb-2">Consulta</p>
                <p className="text-sm text-slate-700 dark:text-slate-300 whitespace-pre-wrap break-words line-clamp-4">{template.nl}</p>
              </div>

              {template.tags.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {template.tags.map((tag) => (
                    <span key={tag} className="rounded-full bg-lime-100 dark:bg-slate-800 px-2.5 py-1 text-xs font-bold text-lime-800 dark:text-lime-300">
                      #{tag}
                    </span>
                  ))}
                </div>
              )}

              <div className="mt-5 flex flex-wrap gap-2">
                <button
                  className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-[#0083B0] hover:bg-[#006a90] text-white font-bold transition disabled:opacity-60"
                  onClick={() => runTemplate(template)}
                  disabled={runningId === template.template_id}
                  type="button"
                >
                  <span className="material-icons text-[18px]">play_arrow</span>
                  {runningId === template.template_id ? "Ejecutando..." : "Ejecutar"}
                </button>
                <button
                  className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-cyan-50 hover:bg-cyan-100 dark:bg-slate-800 dark:hover:bg-slate-700 font-bold transition"
                  onClick={() => copyPrompt(template)}
                  type="button"
                >
                  <span className="material-icons text-[18px]">content_copy</span>
                  Copiar
                </button>
                <button
                  className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-cyan-50 hover:bg-cyan-100 dark:bg-slate-800 dark:hover:bg-slate-700 font-bold transition"
                  onClick={() => fork(template)}
                  type="button"
                >
                  <span className="material-icons text-[18px]">call_split</span>
                  Copiar como mía
                </button>
                {template.can_edit && (
                  <button
                    className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-cyan-50 hover:bg-cyan-100 dark:bg-slate-800 dark:hover:bg-slate-700 font-bold transition"
                    onClick={() => startEdit(template)}
                    type="button"
                  >
                    <span className="material-icons text-[18px]">edit</span>
                    Editar
                  </button>
                )}
                {template.can_delete && (
                  <button
                    className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-red-50 hover:bg-red-100 dark:bg-red-950 dark:hover:bg-red-900 text-red-700 dark:text-red-200 font-bold transition"
                    onClick={() => remove(template)}
                    type="button"
                  >
                    <span className="material-icons text-[18px]">delete</span>
                    Eliminar
                  </button>
                )}
              </div>
            </article>
          ))
        )}
      </section>
    </>
  );
}
