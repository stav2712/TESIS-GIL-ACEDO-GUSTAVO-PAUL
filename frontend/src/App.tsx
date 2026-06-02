import type { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { hasPermission, isAuthed } from "./auth";
import PlatformShell from "./components/PlatformShell";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";
import Home from "./pages/Home";
import UsersPage from "./pages/UsersPage";
import ProfilesPage from "./pages/ProfilesPage";
import AuditPage from "./pages/AuditPage";
import SystemConfigPage from "./pages/SystemConfigPage";
import TemplatesPage from "./pages/TemplatesPage";

function Protected({ children }: { children: ReactNode }) {
  return isAuthed() ? <>{children}</> : <Navigate to="/login" replace />;
}

function PermissionProtected({
  permission,
  children,
}: {
  permission: string;
  children: ReactNode;
}) {
  if (!isAuthed()) return <Navigate to="/login" replace />;
  return hasPermission(permission) ? <>{children}</> : <Navigate to="/" replace />;
}

function WithShell({ children, fullBleed = false }: { children: ReactNode; fullBleed?: boolean }) {
  return (
    <Protected>
      <PlatformShell fullBleed={fullBleed}>{children}</PlatformShell>
    </Protected>
  );
}

function WithPermissionShell({
  permission,
  children,
  fullBleed = false,
}: {
  permission: string;
  children: ReactNode;
  fullBleed?: boolean;
}) {
  return (
    <PermissionProtected permission={permission}>
      <PlatformShell fullBleed={fullBleed}>{children}</PlatformShell>
    </PermissionProtected>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />

      <Route
        path="/"
        element={
          <WithShell>
            <Home />
          </WithShell>
        }
      />

      <Route
        path="/consultas"
        element={
          <WithPermissionShell permission="can_query" fullBleed>
            <div className="consultas-embedded h-full min-h-0 overflow-hidden">
              <Dashboard />
            </div>
          </WithPermissionShell>
        }
      />

      <Route
        path="/plantillas"
        element={
          <WithPermissionShell permission="can_query">
            <TemplatesPage />
          </WithPermissionShell>
        }
      />

      <Route
        path="/usuarios"
        element={
          <WithPermissionShell permission="can_manage_users">
            <UsersPage />
          </WithPermissionShell>
        }
      />

      <Route
        path="/perfiles"
        element={
          <WithPermissionShell permission="can_manage_profiles">
            <ProfilesPage />
          </WithPermissionShell>
        }
      />

      <Route
        path="/auditoria"
        element={
          <WithPermissionShell permission="can_view_audit">
            <AuditPage />
          </WithPermissionShell>
        }
      />

      <Route
        path="/configuracion"
        element={
          <WithPermissionShell permission="can_view_system_config">
            <SystemConfigPage />
          </WithPermissionShell>
        }
      />

      <Route path="*" element={<Navigate to={isAuthed() ? "/" : "/login"} replace />} />
    </Routes>
  );
}
