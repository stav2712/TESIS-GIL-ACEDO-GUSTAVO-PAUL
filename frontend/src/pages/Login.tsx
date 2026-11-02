import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { authLogin } from "../api";
import { setToken } from "../auth";
import { getTheme, toggleTheme } from "../theme";

export default function Login() {
  const nav = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setErr(null);
    setLoading(true);

    try {
      const token = await authLogin(username.trim(), password);
      setToken(token);
      getTheme();
      nav("/", { replace: true });
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Error al iniciar sesión");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="grid min-h-screen bg-[#006f96] text-white dark:bg-slate-950 lg:grid-cols-[1.05fr_0.95fr] font-['Montserrat']">
      <section className="relative hidden overflow-hidden p-10 lg:flex lg:flex-col lg:justify-between">
        <div className="absolute -left-28 -top-28 h-80 w-80 rounded-full bg-[#C6EB32]/25 blur-2xl" />
        <div className="absolute bottom-20 right-10 h-56 w-56 rounded-full bg-white/10 blur-xl" />

        <div className="relative flex items-center gap-4">
          <div className="grid h-14 w-14 place-items-center rounded-3xl bg-[#C6EB32] text-[#006a90] shadow-xl shadow-cyan-950/20">
            <span className="material-icons text-4xl">analytics</span>
          </div>
          <div className="leading-tight">
            <h1 className="text-2xl font-black tracking-tight">CALIDAD Y SALUD T&F</h1>
            <p className="text-sm font-black uppercase tracking-[0.28em] text-lime-100">Plataforma NL-to-SQL</p>
          </div>
        </div>

        <div className="relative max-w-2xl">
{/*           <p className="inline-flex items-center gap-2 rounded-full bg-white/10 px-4 py-2 text-xs font-black uppercase tracking-[0.22em] ring-1 ring-white/15">
            <span className="material-icons text-[18px]">verified_user</span>
            Acceso seguro
          </p> */}
          <h2 className="mt-6 text-5xl font-black leading-tight tracking-tight">
            Una plataforma para convertir preguntas clínicas en reportes auditables.
          </h2>
          <p className="mt-5 text-lg font-medium leading-relaxed text-cyan-50/90">
            Centraliza consultas, historial, plantillas, perfiles, auditoría y configuración operativa.
          </p>
        </div>

        <div className="relative grid grid-cols-3 gap-3">
{/*           {[
            ["auto_awesome", "NL-to-SQL"],
            ["history", "Historial"],
            ["admin_panel_settings", "Permisos"],
          ].map(([icon, label]) => (
            <div key={label} className="rounded-3xl bg-white/10 p-4 ring-1 ring-white/10 backdrop-blur">
              <span className="material-icons text-3xl text-lime-200">{icon}</span>
              <p className="mt-3 text-sm font-black">{label}</p>
            </div>
          ))} */}
        </div>
      </section>

      <main className="flex min-h-screen items-center justify-center bg-slate-100 px-4 py-8 text-slate-900 dark:bg-slate-950 dark:text-slate-100 sm:px-6">
        <div className="w-full max-w-md">
          <div className="mb-6 text-center lg:hidden">
            <div className="mx-auto grid h-16 w-16 place-items-center rounded-3xl bg-[#C6EB32] text-[#006a90] shadow-lg shadow-cyan-950/10">
              <span className="material-icons text-4xl">analytics</span>
            </div>
            <h1 className="mt-4 text-3xl font-black text-slate-950 dark:text-white">CALIDAD Y SALUD T&F</h1>
            <p className="text-sm font-black uppercase tracking-[0.22em] text-[#0083B0] dark:text-lime-300">Plataforma NL-to-SQL</p>
          </div>

          <div className="rounded-[2rem] border border-slate-200 bg-white p-6 shadow-2xl shadow-slate-950/10 dark:border-slate-800 dark:bg-slate-900 sm:p-8">
            <div>
              <p className="text-xs font-black uppercase tracking-[0.22em] text-[#0083B0] dark:text-lime-300">Bienvenido</p>
              <h2 className="mt-2 text-3xl font-black tracking-tight text-slate-950 dark:text-white">Iniciar sesión</h2>
              <p className="mt-2 text-sm font-medium leading-relaxed text-slate-500 dark:text-slate-400">
                Ingresa con tu usuario para acceder a los módulos habilitados por tu perfil.
              </p>
            </div>

            <form className="mt-6 space-y-4" onSubmit={onSubmit}>
              <label className="block">
                <span className="mb-2 block text-sm font-black text-slate-700 dark:text-slate-200">Usuario</span>
                <span className="relative block">
                  <span className="material-icons pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-400">person_outline</span>
                  <input
                    className="block w-full rounded-2xl border border-slate-200 bg-slate-50 py-3.5 pl-12 pr-4 text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-[#0083B0] focus:bg-white focus:ring-4 focus:ring-cyan-100 dark:border-slate-700 dark:bg-slate-800 dark:text-white dark:focus:border-lime-300 dark:focus:ring-lime-300/10"
                    placeholder="Usuario"
                    value={username}
                    onChange={(event) => setUsername(event.target.value)}
                    autoComplete="username"
                  />
                </span>
              </label>

              <label className="block">
                <span className="mb-2 block text-sm font-black text-slate-700 dark:text-slate-200">Contraseña</span>
                <span className="relative block">
                  <span className="material-icons pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-400">lock_outline</span>
                  <input
                    className="block w-full rounded-2xl border border-slate-200 bg-slate-50 py-3.5 pl-12 pr-4 text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-[#0083B0] focus:bg-white focus:ring-4 focus:ring-cyan-100 dark:border-slate-700 dark:bg-slate-800 dark:text-white dark:focus:border-lime-300 dark:focus:ring-lime-300/10"
                    placeholder="Contraseña"
                    type="password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    autoComplete="current-password"
                  />
                </span>
              </label>

              <button
                className="inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-[#006f96] px-5 py-3.5 text-sm font-black uppercase tracking-wide text-white shadow-lg shadow-cyan-950/10 transition hover:-translate-y-0.5 hover:bg-[#005a78] focus:outline-none focus:ring-4 focus:ring-cyan-100 disabled:translate-y-0 disabled:cursor-not-allowed disabled:opacity-70 dark:bg-lime-300 dark:text-slate-950 dark:hover:bg-lime-200 dark:focus:ring-lime-300/20"
                type="submit"
                disabled={loading}
              >
                <span className="material-icons text-[20px]">{loading ? "hourglass_top" : "login"}</span>
                {loading ? "Ingresando..." : "Iniciar sesión"}
              </button>

              {err && (
                <div className="rounded-2xl border border-red-200 bg-red-50 p-3 text-sm font-bold text-red-700 dark:border-red-400/20 dark:bg-red-500/10 dark:text-red-200">
                  {err}
                </div>
              )}
            </form>
          </div>

          <button
            className="fixed bottom-4 right-4 grid h-11 w-11 place-items-center rounded-2xl border border-white/20 bg-slate-900/80 text-white shadow-lg backdrop-blur transition hover:bg-slate-800 dark:bg-white/10 dark:hover:bg-white/20"
            onClick={() => toggleTheme()}
            aria-label="Cambiar tema"
            type="button"
          >
            <span className="material-icons">brightness_6</span>
          </button>
        </div>
      </main>
    </div>
  );
}
