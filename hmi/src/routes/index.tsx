import { Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { useEffect } from "react";
import { useAppSelector } from "../hooks/useAppSelector";
import { useAppDispatch } from "../hooks/useAppDispatch";
import { Login } from "../pages/Login";
import { Signup } from "../pages/Signup";
import { Communications } from "../pages/Communications";
import { OpcUaServer } from "../pages/OpcUaServer";
import { Database } from "../pages/Database";
import { Tags } from "../pages/Tags";
import { DataLogger } from "../pages/DataLogger";
import { Trends } from "../pages/Trends";
import { RealTimeTrends } from "../pages/RealTimeTrends";
import { Alarms } from "../pages/Alarms";
import { AlarmsSummary } from "../pages/AlarmsSummary";
import { Machines } from "../pages/Machines";
import { MachinesDetailed } from "../pages/MachinesDetailed";
import { UserManagement } from "../pages/UserManagement";
import { AccessControl } from "../pages/AccessControl";
import { Settings } from "../pages/Settings";
import { Events } from "../pages/Events";
import { OperationalLogs } from "../pages/OperationalLogs";
import { Performance } from "../pages/Performance";
import { LdsDashboard } from "../pages/LdsDashboard";
import { NoAccess } from "../pages/NoAccess";
import { MainLayout } from "../layouts/MainLayout";
import { isSystemUser, SYSTEM_HOME_PATH } from "../utils/systemUser";
import { firstAllowedPath, viewForPath } from "../utils/access";
import { loadAuthzMe } from "../store/slices/authzSlice";

function ProtectedLayout() {
  const isAuth = useAppSelector((s) => !!s.auth.token);
  const user = useAppSelector((s) => s.auth.user);
  const views = useAppSelector((s) => s.authz.views);
  const authzStatus = useAppSelector((s) => s.authz.status);
  const dispatch = useAppDispatch();
  const location = useLocation();

  useEffect(() => {
    if (isAuth && (authzStatus === "idle" || authzStatus === "error")) {
      void dispatch(loadAuthzMe());
    }
  }, [isAuth, authzStatus, dispatch]);

  if (!isAuth) return <Navigate to="/login" replace />;
  const system = isSystemUser(user);
  const path = location.pathname;
  if (system && path !== SYSTEM_HOME_PATH && !path.startsWith("/user-management")) {
    return <Navigate to={SYSTEM_HOME_PATH} replace />;
  }
  if (path === "/no-access") {
    return (
      <MainLayout>
        <Outlet />
      </MainLayout>
    );
  }
  if (!system && authzStatus === "ready") {
    const viewId = viewForPath(path);
    if (viewId && !views[viewId]?.includes("view")) {
      return <Navigate to={firstAllowedPath(views, false)} replace />;
    }
  }
  return (
    <MainLayout>
      <Outlet />
    </MainLayout>
  );
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />

      <Route element={<ProtectedLayout />}>
        <Route path="/communications" element={<Navigate to="/communications/clients" replace />} />
        <Route path="/communications/clients" element={<Communications />} />
        <Route path="/communications/server" element={<OpcUaServer />} />
        <Route path="/database" element={<Database />} />
        <Route path="/tags" element={<Navigate to="/tags/definitions" replace />} />
        <Route path="/tags/definitions" element={<Tags />} />
        <Route path="/tags/datalogger" element={<DataLogger />} />
        <Route path="/tags/trends" element={<Trends />} />
        <Route path="/real-time-trends" element={<RealTimeTrends />} />
        <Route path="/alarms" element={<Navigate to="/alarms/definitions" replace />} />
        <Route path="/alarms/definitions" element={<Alarms />} />
        <Route path="/alarms/summary" element={<AlarmsSummary />} />
        <Route path="/machines" element={<Navigate to="/machines/summary" replace />} />
        <Route path="/machines/summary" element={<Machines />} />
        <Route path="/machines/detailed" element={<MachinesDetailed />} />
        <Route path="/events" element={<Events />} />
        <Route path="/operational-logs" element={<OperationalLogs />} />
        <Route path="/performance" element={<Performance />} />
        <Route path="/lds-dashboard" element={<LdsDashboard />} />
        <Route path="/user-management" element={<UserManagement />} />
        <Route path="/user-management/access" element={<AccessControl />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/no-access" element={<NoAccess />} />
      </Route>

      <Route path="/" element={<Navigate to="/login" replace />} />
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}
