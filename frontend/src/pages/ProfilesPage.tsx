import { useEffect, useMemo, useState, type ChangeEvent } from "react";
import { createProfile, getSystemConfig, listProfiles, updateProfile, type Profile, type SystemConfig } from "../api";

const PERMISSIONS = [
  ["can_query", "Consultar"],
  ["can_export", "Exportar"],
  ["can_view_sql", "Ver SQL generado"],
  ["can_manage_users", "Gestionar usuarios"],
  ["can_manage_profiles", "Gestionar perfiles"],
  ["can_view_audit", "Ver auditoría"],
  ["can_view_system_config", "Ver configuración"],
] as const;

type ProfileDraft = {
  name: string;
  description: string;
  permissions: Record<string, boolean>;
  allowed_tables_text: string;
  max_page_size: number;
};

function emptyPermissions() {
  return Object.fromEntries(PERMISSIONS.map(([k]) => [k, false]));
}

function toDraft(profile?: Profile): ProfileDraft {
  return {
    name: profile?.name ?? "",
    description: profile?.description ?? "",
    permissions: profile?.permissions ?? emptyPermissions(),
    allowed_tables_text: profile?.allowed_tables?.join(",") ?? "",
    max_page_size: profile?.max_page_size ?? 50,
  };
}

function tablesFromText(text: string): string[] {
  return text
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);
}

export default function ProfilesPage() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [config, setConfig] = useState<SystemConfig | null>(null);
  const [selectedId, setSelectedId] = useState<number | "new">("new");
  const [draft, setDraft] = useState<ProfileDraft>(toDraft());
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const selectedProfile = useMemo(
    () => (selectedId === "new" ? undefined : profiles.find((p) => p.id === selectedId)),
    [profiles, selectedId]
  );

  async function load() {
    const [p, c] = await Promise.all([listProfiles(), getSystemConfig()]);
    setProfiles(p);
    setConfig(c);
  }

  useEffect(() => {
    load().catch((ex) => setErr(ex instanceof Error ? ex.message : "No se pudo cargar perfiles"));
  }, []);

  function selectProfile(next: number | "new") {
    setSelectedId(next);
    setErr(null);
    setMsg(null);

    if (next === "new") {
      setDraft(toDraft());
      return;
    }

    const profile = profiles.find((p) => p.id === next);
    setDraft(toDraft(profile));
  }

  function changePermission(key: string, checked: boolean) {
    setDraft((d) => ({
      ...d,
      permissions: {
        ...d.permissions,
        [key]: checked,
      },
    }));
  }

  function useAllTables() {
    setDraft((d) => ({ ...d, allowed_tables_text: config?.allowed_tables.join(",") ?? d.allowed_tables_text }));
  }

  function onPageSizeChange(e: ChangeEvent<HTMLInputElement>) {
    const value = Number(e.target.value);
    setDraft((d) => ({ ...d, max_page_size: Number.isFinite(value) ? value : 50 }));
  }

  async function save() {
    setErr(null);
    setMsg(null);

    const payload = {
      description: draft.description.trim(),
      permissions: draft.permissions,
      allowed_tables: tablesFromText(draft.allowed_tables_text),
      max_page_size: draft.max_page_size,
    };

    try {
      if (selectedId === "new") {
        if (!draft.name.trim()) {
          setErr("El nombre del perfil es obligatorio.");
          return;
        }
        const created = await createProfile({ name: draft.name.trim(), ...payload });
        setSelectedId(created.id);
        setDraft(toDraft(created));
        setMsg("Perfil creado correctamente.");
      } else {
        const updated = await updateProfile(selectedId, payload);
        setDraft(toDraft(updated));
        setMsg("Perfil actualizado. Los usuarios afectados deben volver a iniciar sesión.");
      }
      await load();
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "No se pudo guardar perfil");
    }
  }

  return (
    <>
      <section className="rounded-3xl bg-white dark:bg-slate-900 border border-cyan-100 dark:border-slate-800 p-6 shadow-xl shadow-cyan-950/10">
        <p className="text-sm uppercase tracking-[0.25em] text-[#0083B0] dark:text-lime-300 font-bold">Seguridad</p>
        <h2 className="text-3xl font-bold text-slate-900 dark:text-white">Perfiles y permisos</h2>
        <p className="text-slate-500 dark:text-slate-400 mt-1">
          Controla qué puede hacer cada perfil, si puede ver el SQL generado y qué vistas clínicas puede consultar. El máximo visualizable es global para toda la plataforma.
        </p>
      </section>

      {err && <div className="mt-4 p-3 rounded-lg bg-red-100 text-red-700 border border-red-200">{err}</div>}
      {msg && <div className="mt-4 p-3 rounded-lg bg-[#C6EB32]/30 text-[#005f80] border border-[#C6EB32]">{msg}</div>}

      <section className="grid grid-cols-1 lg:grid-cols-3 gap-6 mt-6">
        <aside className="rounded-2xl bg-white dark:bg-slate-900 border border-cyan-100 dark:border-slate-800 p-4 shadow-xl shadow-cyan-950/10 h-fit">
          <button
            className={[
              "w-full text-left px-4 py-3 rounded-xl font-bold transition flex items-center gap-2",
              selectedId === "new" ? "bg-[#C6EB32] text-[#005f80]" : "hover:bg-cyan-50 dark:hover:bg-slate-800",
            ].join(" ")}
            onClick={() => selectProfile("new")}
            type="button"
          >
            <span className="material-icons">add_circle</span>
            Nuevo perfil
          </button>

          <div className="mt-3 space-y-2">
            {profiles.map((profile) => (
              <button
                key={profile.id}
                className={[
                  "w-full text-left px-4 py-3 rounded-xl transition",
                  selectedId === profile.id ? "bg-[#0083B0] text-white" : "hover:bg-cyan-50 dark:hover:bg-slate-800",
                ].join(" ")}
                onClick={() => selectProfile(profile.id)}
                type="button"
              >
                <div className="font-bold">{profile.name}</div>
                <div className={selectedId === profile.id ? "text-xs text-cyan-50" : "text-xs text-slate-500 dark:text-slate-400"}>
                  {profile.is_system ? "Perfil del sistema" : "Perfil personalizado"}
                </div>
              </button>
            ))}
          </div>
        </aside>

        <section className="lg:col-span-2 rounded-2xl bg-white dark:bg-slate-900 border border-cyan-100 dark:border-slate-800 p-5 shadow-xl shadow-cyan-950/10">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div className="flex items-center gap-2">
              <span className="material-icons text-[#0083B0] dark:text-lime-300">admin_panel_settings</span>
              <h3 className="font-bold text-xl">{selectedId === "new" ? "Crear perfil" : `Editar ${selectedProfile?.name ?? "perfil"}`}</h3>
            </div>
            {selectedProfile?.is_system && (
              <span className="px-3 py-1 rounded-full bg-[#C6EB32]/40 text-[#005f80] text-xs font-bold">Sistema</span>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-5">
            <label className="block">
              <span className="text-sm font-bold text-slate-600 dark:text-slate-300">Nombre del perfil</span>
              <input
                className="mt-1 w-full px-3 py-2.5 rounded-lg border border-cyan-100 dark:border-slate-700 bg-white dark:bg-slate-950 disabled:bg-slate-100 disabled:text-slate-500"
                value={draft.name}
                onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))}
                disabled={selectedId !== "new"}
                placeholder="Ej. médico, auditor, analista"
              />
            </label>

            <label className="block">
              <span className="text-sm font-bold text-slate-600 dark:text-slate-300">Descripción</span>
              <input
                className="mt-1 w-full px-3 py-2.5 rounded-lg border border-cyan-100 dark:border-slate-700 bg-white dark:bg-slate-950"
                value={draft.description}
                onChange={(e) => setDraft((d) => ({ ...d, description: e.target.value }))}
                placeholder="Descripción funcional del perfil"
              />
            </label>

{/*             <div className="rounded-xl border border-cyan-100 dark:border-slate-800 bg-cyan-50/70 dark:bg-slate-950 px-4 py-3">
              <span className="text-sm font-bold text-slate-600 dark:text-slate-300">Máximo visualizable</span>
              <p className="text-2xl font-extrabold text-[#0083B0] dark:text-lime-300 mt-1">
                {config?.query_display_max_rows ?? 5000}
              </p>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                Valor global definido en configuración del sistema. No se modifica por perfil para mantener una regla uniforme.
              </p>
            </div>

            <label className="block">
              <span className="text-sm font-bold text-slate-600 dark:text-slate-300">Máximo por página</span>
              <input
                className="mt-1 w-full px-3 py-2.5 rounded-lg border border-cyan-100 dark:border-slate-700 bg-white dark:bg-slate-950"
                type="number"
                min={1}
                max={50}
                value={draft.max_page_size}
                onChange={onPageSizeChange}
              />
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                Recomendado: 50. El backend no permitirá superar 50 desde perfiles.
              </p>
            </label> */}
          </div>

          <div className="mt-6">
            <h4 className="font-bold text-slate-900 dark:text-white">Permisos funcionales</h4>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">El permiso “Ver SQL generado” permite mostrar el SQL en auditoría y también incluirlo en la metadata de exportaciones Excel/PDF. Sin ese permiso, el resultado puede verse o exportarse, pero el SQL queda oculto.</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 mt-3">
              {PERMISSIONS.map(([key, label]) => (
                <label
                  key={key}
                  className="flex items-center gap-3 rounded-xl border border-cyan-100 dark:border-slate-800 px-3 py-3 hover:bg-cyan-50 dark:hover:bg-slate-800 transition"
                >
                  <input
                    type="checkbox"
                    className="w-4 h-4 accent-[#0083B0]"
                    checked={!!draft.permissions[key]}
                    onChange={(e) => changePermission(key, e.target.checked)}
                  />
                  <span className="text-sm font-semibold">{label}</span>
                </label>
              ))}
            </div>
          </div>

          <div className="mt-6">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <div>
                <h4 className="font-bold text-slate-900 dark:text-white">Restricción de vistas clínicas</h4>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                  Déjalo vacío para permitir todas las vistas globales. Escribe una lista solo cuando quieras restringir el perfil.
                </p>
              </div>
              <div className="flex items-center gap-2 flex-wrap justify-end">
                {!draft.allowed_tables_text.trim() && (
                  <span className="px-3 py-1 rounded-full bg-[#C6EB32]/35 text-[#005f80] text-xs font-bold">
                    Sin restricción por vistas
                  </span>
                )}
                <button
                  className="px-3 py-2 rounded-lg bg-[#C6EB32] hover:bg-lime-300 text-[#005f80] font-bold transition"
                  onClick={useAllTables}
                  type="button"
                >
                  Cargar lista completa
                </button>
              </div>
            </div>

            <textarea
              className="mt-3 w-full min-h-32 px-3 py-2.5 rounded-lg border border-cyan-100 dark:border-slate-700 bg-white dark:bg-slate-950 font-mono text-xs"
              placeholder="Vacío = todas las vistas globales. Ej. reporting.vw_pacientes,reporting.vw_diagnosticos"
              value={draft.allowed_tables_text}
              onChange={(e) => setDraft((d) => ({ ...d, allowed_tables_text: e.target.value }))}
            />
          </div>

          <div className="mt-6 flex justify-end">
            <button className="px-5 py-3 rounded-lg bg-[#0083B0] hover:bg-[#006a90] text-white font-bold transition" onClick={save} type="button">
              Guardar perfil
            </button>
          </div>
        </section>
      </section>
    </>
  );
}
