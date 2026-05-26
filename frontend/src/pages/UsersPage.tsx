import { useEffect, useMemo, useState, type FormEvent, type InputHTMLAttributes, type SelectHTMLAttributes } from "react";
import { createUser, listProfiles, listUsers, updateUser, type AppUser, type Profile } from "../api";

function TextInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={[
        "w-full px-3 py-2.5 rounded-lg border border-cyan-100 dark:border-slate-700 bg-white dark:bg-slate-950",
        "text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-[#0083B0]",
        props.className ?? "",
      ].join(" ")}
    />
  );
}

function SelectInput(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className={[
        "w-full px-3 py-2.5 rounded-lg border border-cyan-100 dark:border-slate-700 bg-white dark:bg-slate-950",
        "text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-[#0083B0]",
        props.className ?? "",
      ].join(" ")}
    />
  );
}

type UserForm = {
  username: string;
  password: string;
  full_name: string;
  profile_id: string;
};

type EditUserForm = UserForm & {
  is_active: boolean;
};

const emptyCreateForm: UserForm = {
  username: "",
  password: "",
  full_name: "",
  profile_id: "",
};

function profileValue(user: AppUser) {
  return user.profile_id === null || user.profile_id === undefined ? "" : String(user.profile_id);
}

export default function UsersPage() {
  const [users, setUsers] = useState<AppUser[]>([]);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [q, setQ] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [form, setForm] = useState<UserForm>(emptyCreateForm);
  const [editingUser, setEditingUser] = useState<AppUser | null>(null);
  const [editForm, setEditForm] = useState<EditUserForm>({ ...emptyCreateForm, is_active: true });

  const profileOptions = useMemo(() => profiles.map((p) => ({ value: String(p.id), label: p.name })), [profiles]);

  async function load() {
    const [u, p] = await Promise.all([listUsers(q.trim() || undefined), listProfiles()]);
    setUsers(u);
    setProfiles(p);
  }

  useEffect(() => {
    load().catch((ex) => setErr(ex instanceof Error ? ex.message : "No se pudo cargar usuarios"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    setMsg(null);

    try {
      await createUser({
        username: form.username.trim(),
        password: form.password,
        full_name: form.full_name.trim() || null,
        profile_id: form.profile_id ? Number(form.profile_id) : null,
      });
      setForm(emptyCreateForm);
      setMsg("Usuario creado correctamente.");
      await load();
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "No se pudo crear usuario");
    }
  }

  async function patchUser(userId: number, payload: Parameters<typeof updateUser>[1]) {
    setErr(null);
    setMsg(null);
    try {
      await updateUser(userId, payload);
      setMsg("Usuario actualizado. Si cambiaste su perfil, ese usuario debe volver a iniciar sesión.");
      await load();
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "No se pudo actualizar usuario");
    }
  }

  function openEdit(user: AppUser) {
    setErr(null);
    setMsg(null);
    setEditingUser(user);
    setEditForm({
      username: user.username,
      full_name: user.full_name ?? "",
      password: "",
      profile_id: profileValue(user),
      is_active: user.is_active,
    });
  }

  function closeEdit() {
    setEditingUser(null);
    setEditForm({ ...emptyCreateForm, is_active: true });
  }

  async function onEdit(e: FormEvent) {
    e.preventDefault();
    if (!editingUser) return;

    setErr(null);
    setMsg(null);

    try {
      await updateUser(editingUser.id, {
        username: editForm.username.trim(),
        full_name: editForm.full_name.trim() || null,
        ...(editForm.password.trim() ? { password: editForm.password } : {}),
        ...(editForm.profile_id ? { profile_id: Number(editForm.profile_id) } : {}),
        is_active: editForm.is_active,
      });
      closeEdit();
      setMsg("Usuario modificado correctamente. Si estaba conectado, debe volver a iniciar sesión para recibir permisos actualizados.");
      await load();
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "No se pudo modificar usuario");
    }
  }

  return (
    <>
      <section className="rounded-3xl bg-white dark:bg-slate-900 border border-cyan-100 dark:border-slate-800 p-6 shadow-xl shadow-cyan-950/10">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <p className="text-sm uppercase tracking-[0.25em] text-[#0083B0] dark:text-lime-300 font-bold">Administración</p>
            <h2 className="text-3xl font-bold text-slate-900 dark:text-white">Usuarios</h2>
            <p className="text-slate-500 dark:text-slate-400 mt-1">
              Alta, edición, asignación de perfil y activación/desactivación. El perfil define todos los permisos.
            </p>
          </div>

          <div className="flex gap-2 w-full sm:w-auto">
            <TextInput className="sm:w-64" placeholder="Buscar usuario" value={q} onChange={(e) => setQ(e.target.value)} />
            <button
              className="px-4 py-2.5 rounded-lg bg-[#0083B0] hover:bg-[#006a90] text-white font-bold transition"
              onClick={() => load()}
              type="button"
            >
              Buscar
            </button>
          </div>
        </div>
      </section>

      {err && <div className="mt-4 p-3 rounded-lg bg-red-100 text-red-700 border border-red-200">{err}</div>}
      {msg && <div className="mt-4 p-3 rounded-lg bg-[#C6EB32]/30 text-[#005f80] border border-[#C6EB32]">{msg}</div>}

      <section className="grid grid-cols-1 lg:grid-cols-3 gap-6 mt-6">
        <form onSubmit={onCreate} className="rounded-2xl bg-[#C6EB32] dark:bg-slate-900 border border-lime-200 dark:border-slate-800 p-5 space-y-3 shadow-xl shadow-cyan-950/10">
          <div className="flex items-center gap-2 text-[#005f80] dark:text-white">
            <span className="material-icons">person_add</span>
            <h3 className="font-bold text-lg">Agregar usuario</h3>
          </div>

          <TextInput placeholder="Usuario" value={form.username} onChange={(e) => setForm((f) => ({ ...f, username: e.target.value }))} required />
          <TextInput placeholder="Nombre completo" value={form.full_name} onChange={(e) => setForm((f) => ({ ...f, full_name: e.target.value }))} />
          <TextInput
            placeholder="Contraseña"
            type="password"
            value={form.password}
            onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
            required
          />

          <SelectInput value={form.profile_id} onChange={(e) => setForm((f) => ({ ...f, profile_id: e.target.value }))}>
            <option value="">Perfil por defecto: consulta</option>
            {profileOptions.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </SelectInput>

          <p className="text-xs text-[#005f80]/80 dark:text-slate-400">
            Para crear un administrador, asígnale el perfil <b>admin</b> o un perfil con permisos administrativos.
          </p>

          <button className="w-full px-4 py-3 rounded-lg bg-[#0083B0] hover:bg-[#006a90] text-white font-bold transition" type="submit">
            Crear usuario
          </button>
        </form>

        <div className="lg:col-span-2 rounded-2xl bg-white dark:bg-slate-900 border border-cyan-100 dark:border-slate-800 overflow-hidden shadow-xl shadow-cyan-950/10">
          <div className="px-5 py-4 border-b border-cyan-100 dark:border-slate-800 flex items-center gap-2">
            <span className="material-icons text-[#0083B0] dark:text-lime-300">groups</span>
            <h3 className="font-bold">Usuarios registrados</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[#0083B0] text-white text-left">
                <tr>
                  <th className="p-3">Usuario</th>
                  <th className="p-3">Perfil</th>
                  <th className="p-3">Estado</th>
                  <th className="p-3">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id} className="border-t border-cyan-100 dark:border-slate-800">
                    <td className="p-3">
                      <div className="font-bold text-slate-900 dark:text-white">{u.username}</div>
                      <div className="text-xs text-slate-500 dark:text-slate-400">{u.full_name || "Sin nombre"}</div>
                    </td>
                    <td className="p-3 min-w-44">
                      <SelectInput value={profileValue(u)} onChange={(e) => patchUser(u.id, { profile_id: Number(e.target.value) })}>
                        {profiles.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.name}
                          </option>
                        ))}
                      </SelectInput>
                    </td>
                    <td className="p-3">
                      <span
                        className={[
                          "inline-flex px-2.5 py-1 rounded-full text-xs font-bold",
                          u.is_active ? "bg-lime-100 text-lime-800" : "bg-red-100 text-red-700",
                        ].join(" ")}
                      >
                        {u.is_active ? "Activo" : "Inactivo"}
                      </span>
                    </td>
                    <td className="p-3">
                      <div className="flex flex-wrap gap-2">
                        <button
                          className="px-3 py-2 rounded-lg bg-[#0083B0] hover:bg-[#006a90] text-white font-bold transition"
                          onClick={() => openEdit(u)}
                          type="button"
                        >
                          Editar
                        </button>
                        <button
                          className="px-3 py-2 rounded-lg bg-[#C6EB32] hover:bg-lime-300 text-[#005f80] font-bold transition"
                          onClick={() => patchUser(u.id, { is_active: !u.is_active })}
                          type="button"
                        >
                          {u.is_active ? "Desactivar" : "Activar"}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}

                {users.length === 0 && (
                  <tr>
                    <td colSpan={4} className="p-6 text-center text-slate-500">
                      No hay usuarios.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {editingUser && (
        <div className="fixed inset-0 z-50 bg-slate-950/50 backdrop-blur-sm flex items-center justify-center p-4">
          <form onSubmit={onEdit} className="w-full max-w-xl rounded-3xl bg-white dark:bg-slate-900 border border-cyan-100 dark:border-slate-800 shadow-2xl overflow-hidden">
            <div className="px-6 py-5 bg-[#0083B0] text-white flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <span className="material-icons">manage_accounts</span>
                <div>
                  <h3 className="font-bold text-xl">Modificar usuario</h3>
                  <p className="text-cyan-50 text-sm">Editando a {editingUser.username}</p>
                </div>
              </div>
              <button className="w-10 h-10 rounded-full hover:bg-white/15 transition flex items-center justify-center" onClick={closeEdit} type="button" title="Cerrar">
                <span className="material-icons">close</span>
              </button>
            </div>

            <div className="p-6 space-y-4">
              <label className="block">
                <span className="text-sm font-bold text-slate-600 dark:text-slate-300">Usuario</span>
                <TextInput value={editForm.username} onChange={(e) => setEditForm((f) => ({ ...f, username: e.target.value }))} required />
              </label>

              <label className="block">
                <span className="text-sm font-bold text-slate-600 dark:text-slate-300">Nombre completo</span>
                <TextInput value={editForm.full_name} onChange={(e) => setEditForm((f) => ({ ...f, full_name: e.target.value }))} placeholder="Opcional" />
              </label>

              <label className="block">
                <span className="text-sm font-bold text-slate-600 dark:text-slate-300">Nueva contraseña</span>
                <TextInput
                  type="password"
                  value={editForm.password}
                  onChange={(e) => setEditForm((f) => ({ ...f, password: e.target.value }))}
                  placeholder="Déjalo vacío para mantener la contraseña actual"
                />
              </label>

              <label className="block">
                <span className="text-sm font-bold text-slate-600 dark:text-slate-300">Perfil</span>
                <SelectInput value={editForm.profile_id} onChange={(e) => setEditForm((f) => ({ ...f, profile_id: e.target.value }))} required>
                  <option value="" disabled>
                    Selecciona un perfil
                  </option>
                  {profileOptions.map((p) => (
                    <option key={p.value} value={p.value}>
                      {p.label}
                    </option>
                  ))}
                </SelectInput>
              </label>

              <label className="flex items-center gap-3 rounded-xl border border-cyan-100 dark:border-slate-800 px-3 py-3 hover:bg-cyan-50 dark:hover:bg-slate-800 transition">
                <input
                  type="checkbox"
                  className="w-4 h-4 accent-[#0083B0]"
                  checked={editForm.is_active}
                  onChange={(e) => setEditForm((f) => ({ ...f, is_active: e.target.checked }))}
                />
                <span className="font-semibold">Usuario activo</span>
              </label>

              <p className="text-xs text-slate-500 dark:text-slate-400">
                Si modificas perfil, estado o contraseña de un usuario que ya está conectado, pídele que cierre sesión y vuelva a entrar.
              </p>
            </div>

            <div className="px-6 py-4 bg-slate-50 dark:bg-slate-950 flex justify-end gap-2">
              <button className="px-4 py-2.5 rounded-lg bg-white dark:bg-slate-800 border border-cyan-100 dark:border-slate-700 font-bold" onClick={closeEdit} type="button">
                Cancelar
              </button>
              <button className="px-5 py-2.5 rounded-lg bg-[#C6EB32] hover:bg-lime-300 text-[#005f80] font-bold transition" type="submit">
                Guardar cambios
              </button>
            </div>
          </form>
        </div>
      )}
    </>
  );
}
