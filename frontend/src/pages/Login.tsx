import { useState } from "react";
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

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    setLoading(true);
    try {
      const token = await authLogin(username.trim(), password);
      setToken(token);

      // “se pasa” el modo elegido (persistido ya en localStorage)
      // dashboard lo leerá y aplicará igual.
      getTheme();

      nav("/", { replace: true });
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Error al iniciar sesión");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="h-screen flex flex-col items-center justify-center transition-colors duration-300 bg-[#0083B0] dark:bg-slate-900 font-['Montserrat']">
      <div className="mb-8 text-center text-white">
        <h1 className="text-4xl font-bold tracking-tight">Clínica</h1>
        <h2 className="text-3xl font-normal tracking-wider">VELTRA</h2>
      </div>

      <div className="w-full max-w-md p-8 rounded-lg shadow-xl transition-colors duration-300 bg-[#C6EB32] dark:bg-slate-800 dark:border dark:border-slate-700">
        <form className="space-y-4" onSubmit={onSubmit}>
          <div className="relative">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <span className="material-icons text-gray-400 text-xl">person_outline</span>
            </div>
            <input
              className="block w-full pl-10 pr-3 py-3 border-none rounded-md bg-white text-gray-900 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-[#0083B0] shadow-sm"
              placeholder="Usuario"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
            />
          </div>

          <div className="relative">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <span className="material-icons text-gray-400 text-xl">lock_outline</span>
            </div>
            <input
              className="block w-full pl-10 pr-3 py-3 border-none rounded-md bg-white text-gray-900 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-[#0083B0] shadow-sm"
              placeholder="Contraseña"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
            />
          </div>

          <button
            className="w-full flex justify-center py-3 px-4 border border-transparent rounded-md shadow-sm text-sm font-bold text-white bg-[#0083B0] hover:bg-[#005f80] focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[#0083B0] uppercase tracking-wide transition-colors duration-200 disabled:opacity-70"
            type="submit"
            disabled={loading}
          >
            {loading ? "Ingresando..." : "Iniciar Sesión"}
          </button>

          {err && (
            <div className="text-sm text-red-700 bg-red-100 rounded-md p-2">
              {err}
            </div>
          )}
        </form>
      </div>

      <button
        className="fixed bottom-4 right-4 p-2 bg-white/10 dark:bg-black/20 rounded-full text-white hover:bg-white/20 transition"
        onClick={() => toggleTheme()}
        aria-label="Cambiar tema"
      >
        <span className="material-icons">brightness_6</span>
      </button>
    </div>
  );
}