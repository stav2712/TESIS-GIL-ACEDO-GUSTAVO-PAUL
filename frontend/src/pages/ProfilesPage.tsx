import { useEffect, useMemo, useState } from "react";
import {
  createProfile,
  getSystemConfig,
  getSystemSchema,
  listProfiles,
  updateProfile,
  type ColumnPermissions,
  type Profile,
  type TableAccessMode,
  type SystemConfig,
  type SystemSchema,
} from "../api";

const PERMISSIONS = [
  ["can_query", "Consultar"],
  ["can_export", "Exportar"],
  ["can_view_sql", "Ver SQL generado"],
  ["can_manage_users", "Gestionar usuarios"],
  ["can_manage_profiles", "Gestionar perfiles"],
  ["can_view_audit", "Ver auditoría"],
  ["can_view_system_config", "Ver configuración"],
] as const;

type ColumnMode = "visible" | "hidden" | "forbidden";

type ColumnRulesDraft = {
  hidden: string[];
  forbidden: string[];
};

type ProfileDraft = {
  name: string;
  description: string;
  permissions: Record<string, boolean>;
  allowed_tables: string[];
  table_access_mode: TableAccessMode;
  column_permissions: Record<string, ColumnRulesDraft>;
  max_page_size: number;
};

function emptyPermissions() {
  return Object.fromEntries(PERMISSIONS.map(([k]) => [k, false]));
}

function normalizeName(value: string) {
  return value.trim().toLowerCase();
}

function uniqueNormalized(values: string[] | undefined) {
  return Array.from(new Set((values ?? []).map(normalizeName).filter(Boolean))).sort();
}

function normalizeColumnPermissions(value: ColumnPermissions | undefined): Record<string, ColumnRulesDraft> {
  const normalized: Record<string, ColumnRulesDraft> = {};

  for (const [table, rules] of Object.entries(value ?? {})) {
    const tableName = normalizeName(table);
    if (!tableName) continue;

    const forbidden = uniqueNormalized(rules.forbidden);
    const forbiddenSet = new Set(forbidden);
    const hidden = uniqueNormalized(rules.hidden).filter((col) => !forbiddenSet.has(col));

    if (hidden.length || forbidden.length) {
      normalized[tableName] = { hidden, forbidden };
    }
  }

  return normalized;
}

function toDraft(profile?: Profile): ProfileDraft {
  return {
    name: profile?.name ?? "",
    description: profile?.description ?? "",
    permissions: profile?.permissions ?? emptyPermissions(),
    allowed_tables: uniqueNormalized(profile?.allowed_tables),
    table_access_mode: profile?.table_access_mode === "custom" ? "custom" : "all",
    column_permissions: normalizeColumnPermissions(profile?.column_permissions),
    max_page_size: profile?.max_page_size ?? 50,
  };
}

function compactColumnPermissions(value: Record<string, ColumnRulesDraft>): ColumnPermissions {
  const compact: ColumnPermissions = {};

  for (const [table, rules] of Object.entries(value)) {
    const hidden = uniqueNormalized(rules.hidden);
    const forbidden = uniqueNormalized(rules.forbidden);

    if (hidden.length || forbidden.length) {
      compact[table] = { hidden, forbidden };
    }
  }

  return compact;
}

function countRules(rules: ColumnRulesDraft | undefined) {
  return (rules?.hidden.length ?? 0) + (rules?.forbidden.length ?? 0);
}

export default function ProfilesPage() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [config, setConfig] = useState<SystemConfig | null>(null);
  const [schema, setSchema] = useState<SystemSchema | null>(null);
  const [selectedId, setSelectedId] = useState<number | "new">("new");
  const [draft, setDraft] = useState<ProfileDraft>(toDraft());
  const [selectedColumnTable, setSelectedColumnTable] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [schemaMsg, setSchemaMsg] = useState<string | null>(null);

  const selectedProfile = useMemo(
    () => (selectedId === "new" ? undefined : profiles.find((p) => p.id === selectedId)),
    [profiles, selectedId]
  );

  const allTables = useMemo(() => uniqueNormalized(config?.allowed_tables), [config?.allowed_tables]);
  const isCustomTableAccess = draft.table_access_mode === "custom";

  const effectiveAllowedTables = useMemo(() => {
    if (!allTables.length) return isCustomTableAccess ? draft.allowed_tables : [];
    if (!isCustomTableAccess) return allTables;

    const all = new Set(allTables);
    return draft.allowed_tables.filter((table) => all.has(table));
  }, [allTables, draft.allowed_tables, isCustomTableAccess]);

  const selectedTableColumns = useMemo(() => {
    if (!selectedColumnTable) return [];
    return schema?.tables?.[selectedColumnTable] ?? [];
  }, [schema?.tables, selectedColumnTable]);

  async function load() {
    const [p, c] = await Promise.all([listProfiles(), getSystemConfig()]);
    setProfiles(p);
    setConfig(c);

    try {
      const s = await getSystemSchema();
      setSchema(s);
      if (Object.keys(s.errors ?? {}).length) {
        setSchemaMsg("Algunas vistas no devolvieron columnas. Puedes guardar permisos de vistas igual.");
      } else {
        setSchemaMsg(null);
      }
    } catch (ex) {
      setSchema(null);
      setSchemaMsg(ex instanceof Error ? ex.message : "No se pudieron cargar las columnas de las vistas.");
    }
  }

  useEffect(() => {
    load().catch((ex) => setErr(ex instanceof Error ? ex.message : "No se pudo cargar perfiles"));
  }, []);

  useEffect(() => {
    if (!effectiveAllowedTables.length) {
      setSelectedColumnTable("");
      return;
    }

    if (!selectedColumnTable || !effectiveAllowedTables.includes(selectedColumnTable)) {
      setSelectedColumnTable(effectiveAllowedTables[0]);
    }
  }, [effectiveAllowedTables, selectedColumnTable]);

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

  function allowAllTables() {
    setDraft((d) => ({ ...d, table_access_mode: "all", allowed_tables: [] }));
  }

  function denyAllTables() {
    setDraft((d) => ({ ...d, table_access_mode: "custom", allowed_tables: [] }));
  }

  function setTableAllowed(table: string, allowed: boolean) {
    setDraft((d) => {
      const current = new Set(d.table_access_mode === "custom" ? d.allowed_tables : allTables);
      if (allowed) current.add(table);
      else current.delete(table);

      const next = allTables.filter((item) => current.has(item));
      return {
        ...d,
        table_access_mode: "custom",
        allowed_tables: next,
      };
    });
  }

  function isTableAllowed(table: string) {
    return draft.table_access_mode !== "custom" || draft.allowed_tables.includes(table);
  }

  function columnMode(table: string, column: string): ColumnMode {
    const rules = draft.column_permissions[table];
    const col = normalizeName(column);

    if (rules?.forbidden.includes(col)) return "forbidden";
    if (rules?.hidden.includes(col)) return "hidden";
    return "visible";
  }

  function setColumnMode(table: string, column: string, mode: ColumnMode) {
    const tableName = normalizeName(table);
    const col = normalizeName(column);
    if (!tableName || !col) return;

    setDraft((d) => {
      const current = d.column_permissions[tableName] ?? { hidden: [], forbidden: [] };
      let hidden = uniqueNormalized(current.hidden).filter((x) => x !== col);
      let forbidden = uniqueNormalized(current.forbidden).filter((x) => x !== col);

      if (mode === "hidden") hidden = uniqueNormalized([...hidden, col]);
      if (mode === "forbidden") forbidden = uniqueNormalized([...forbidden, col]);

      const nextRules = { hidden, forbidden };
      const nextPermissions = { ...d.column_permissions };

      if (countRules(nextRules)) nextPermissions[tableName] = nextRules;
      else delete nextPermissions[tableName];

      return { ...d, column_permissions: nextPermissions };
    });
  }

  function clearColumnRules(table: string) {
    const tableName = normalizeName(table);
    setDraft((d) => {
      const next = { ...d.column_permissions };
      delete next[tableName];
      return { ...d, column_permissions: next };
    });
  }

  async function save() {
    setErr(null);
    setMsg(null);

    const payload = {
      description: draft.description.trim(),
      permissions: draft.permissions,
      allowed_tables: draft.table_access_mode === "custom" ? draft.allowed_tables : [],
      table_access_mode: draft.table_access_mode,
      column_permissions: compactColumnPermissions(draft.column_permissions),
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
          Controla qué puede hacer cada perfil, qué vistas clínicas puede consultar y qué columnas se ocultan o bloquean por vista.
        </p>
      </section>

      {err && <div className="mt-4 p-3 rounded-lg bg-red-100 text-red-700 border border-red-200">{err}</div>}
      {msg && <div className="mt-4 p-3 rounded-lg bg-[#C6EB32]/30 text-[#005f80] border border-[#C6EB32]">{msg}</div>}
      {schemaMsg && <div className="mt-4 p-3 rounded-lg bg-amber-50 text-amber-700 border border-amber-200">{schemaMsg}</div>}

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
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
              El permiso “Ver SQL generado” permite mostrar el SQL en auditoría y también incluirlo en la metadata de exportaciones Excel/PDF.
              Sin ese permiso, el resultado puede verse o exportarse, pero el SQL queda oculto.
            </p>

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
                  Permitir todas usa siempre la lista global. Si marcas o desmarcas tarjetas, el perfil queda restringido exactamente a esas vistas; si no marcas ninguna, no podrá consultar vistas clínicas.
                </p>
              </div>
              <div className="flex items-center gap-2 flex-wrap justify-end">
                <span className="px-3 py-1 rounded-full bg-[#C6EB32]/35 text-[#005f80] text-xs font-bold">
                  {isCustomTableAccess ? `${draft.allowed_tables.length} vistas seleccionadas` : "Sin restricción por vistas"}
                </span>
                <button
                  className="px-3 py-2 rounded-lg bg-cyan-50 dark:bg-slate-800 hover:bg-cyan-100 dark:hover:bg-slate-700 text-[#005f80] dark:text-lime-300 font-bold transition"
                  onClick={allowAllTables}
                  type="button"
                >
                  Permitir todas
                </button>
                <button
                  className="px-3 py-2 rounded-lg bg-red-50 dark:bg-red-950/30 hover:bg-red-100 dark:hover:bg-red-950/50 text-red-700 dark:text-red-300 font-bold transition"
                  onClick={denyAllTables}
                  type="button"
                >
                  Ninguna vista
                </button>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3 max-h-80 overflow-y-auto pr-1">
              {allTables.map((table) => {
                const allowed = isTableAllowed(table);
                const rules = draft.column_permissions[table];
                const ruleCount = countRules(rules);

                return (
                  <label
                    key={table}
                    className={[
                      "rounded-xl border px-3 py-3 transition cursor-pointer",
                      allowed
                        ? "border-cyan-100 dark:border-slate-700 bg-white dark:bg-slate-950"
                        : "border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/60 opacity-70",
                    ].join(" ")}
                  >
                    <div className="flex items-start gap-3">
                      <input
                        type="checkbox"
                        className="mt-1 w-4 h-4 accent-[#0083B0]"
                        checked={allowed}
                        onChange={(e) => setTableAllowed(table, e.target.checked)}
                      />
                      <div className="min-w-0 flex-1">
                        <p className="font-semibold text-sm break-all">{table}</p>
                        <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-1">
                          {schema?.tables?.[table]?.length ?? 0} columnas {ruleCount ? `· ${ruleCount} reglas` : ""}
                        </p>
                      </div>
                    </div>
                  </label>
                );
              })}
            </div>
          </div>

          <div className="mt-6 rounded-2xl border border-cyan-100 dark:border-slate-800 bg-cyan-50/50 dark:bg-slate-950 p-4">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <div>
                <h4 className="font-bold text-slate-900 dark:text-white">Permisos por columnas</h4>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                  Visible muestra normal. Ocultar ejecuta la consulta, pero elimina esa columna del resultado y exportación. Prohibir bloquea consultas que usen ese campo.
                </p>
              </div>

              <select
                className="px-3 py-2.5 rounded-lg border border-cyan-100 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm max-w-full"
                value={selectedColumnTable}
                onChange={(e) => setSelectedColumnTable(e.target.value)}
                disabled={!effectiveAllowedTables.length}
              >
                {effectiveAllowedTables.map((table) => (
                  <option key={table} value={table}>
                    {table}
                  </option>
                ))}
              </select>
            </div>

            {!selectedColumnTable && (
              <div className="mt-4 text-sm text-slate-500 dark:text-slate-400">
                Selecciona al menos una vista para configurar columnas.
              </div>
            )}

            {selectedColumnTable && (
              <div className="mt-4">
                <div className="flex items-center justify-between gap-3 flex-wrap mb-3">
                  <div className="text-sm text-slate-600 dark:text-slate-300 break-all">
                    Vista activa: <span className="font-bold">{selectedColumnTable}</span>
                  </div>
                  <button
                    className="px-3 py-2 rounded-lg bg-white dark:bg-slate-900 border border-cyan-100 dark:border-slate-700 text-sm font-bold hover:bg-cyan-50 dark:hover:bg-slate-800 transition"
                    onClick={() => clearColumnRules(selectedColumnTable)}
                    type="button"
                  >
                    Limpiar reglas de esta vista
                  </button>
                </div>

                {!selectedTableColumns.length ? (
                  <div className="rounded-xl bg-white dark:bg-slate-900 border border-cyan-100 dark:border-slate-800 p-4 text-sm text-slate-500 dark:text-slate-400">
                    No se pudieron leer columnas para esta vista. Revisa que query_service esté activo y que la vista exista en la base clínica.
                  </div>
                ) : (
                  <div className="rounded-xl border border-cyan-100 dark:border-slate-800 overflow-hidden bg-white dark:bg-slate-900">
                    <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-3 px-4 py-3 text-xs font-bold uppercase tracking-wide bg-white dark:bg-slate-900 border-b border-cyan-100 dark:border-slate-800 text-slate-500 dark:text-slate-400">
                      <span>Columna</span>
                      <span>Regla</span>
                    </div>

                    <div className="max-h-96 overflow-y-auto divide-y divide-cyan-50 dark:divide-slate-800">
                      {selectedTableColumns.map((column) => {
                        const mode = columnMode(selectedColumnTable, column);
                        return (
                          <div key={column} className="grid grid-cols-1 md:grid-cols-[minmax(0,1fr)_auto] gap-3 px-4 py-3 items-center">
                            <div className="min-w-0">
                              <p className="font-mono text-sm break-all text-slate-900 dark:text-slate-100">{column}</p>
                            </div>

                            <div className="inline-flex rounded-lg border border-cyan-100 dark:border-slate-700 overflow-hidden text-xs font-bold justify-self-start md:justify-self-end">
                              {(["visible", "hidden", "forbidden"] as const).map((option) => (
                                <button
                                  key={option}
                                  className={[
                                    "px-3 py-2 transition",
                                    mode === option
                                      ? option === "visible"
                                        ? "bg-[#C6EB32] text-[#005f80]"
                                        : option === "hidden"
                                          ? "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200"
                                          : "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-200"
                                      : "bg-white dark:bg-slate-900 hover:bg-cyan-50 dark:hover:bg-slate-800",
                                  ].join(" ")}
                                  onClick={() => setColumnMode(selectedColumnTable, column, option)}
                                  type="button"
                                >
                                  {option === "visible" ? "Visible" : option === "hidden" ? "Ocultar" : "Prohibir"}
                                </button>
                              ))}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            )}
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
