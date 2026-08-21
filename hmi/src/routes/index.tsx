import { Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { useAppSelector } from "../hooks/useAppSelector";
import { Login } from "../pages/Login";
import { Signup } from "../pages/Signup";
// import { ForgotPassword } from "../pages/ForgotPassword";
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
import { Settings } from "../pages/Settings";
import { Events } from "../pages/Events";
import { OperationalLogs } from "../pages/OperationalLogs";
import { Performance } from "../pages/Performance";
import { MainLayout } from "../layouts/MainLayout";
import { isSystemUser, SYSTEM_HOME_PATH } from "../utils/systemUser";
import {
  canViewPerformance,
  canViewSettings,
  canViewUserManagement,
} from "../utils/access";

function ProtectedLayout() {
  const isAuth = useAppSelector((s) => !!s.auth.token);
  const user = useAppSelector((s) => s.auth.user);
  const location = useLocation();
  if (!isAuth) return <Navigate to="/login" replace />;
  if (isSystemUser(user) && location.pathname !== SYSTEM_HOME_PATH) {
    return <Navigate to={SYSTEM_HOME_PATH} replace />;
  }
  const role = user?.role;
  const path = location.pathname;
  if (!isSystemUser(user)) {
    if (path === "/performance" || path.startsWith("/performance/")) {
      if (!canViewPerformance(role)) return <Navigate to="/communications" replace />;
    }
    if (path === "/settings" || path.startsWith("/settings/")) {
      if (!canViewSettings(role)) return <Navigate to="/communications" replace />;
    }
    if (path === "/user-management" || path.startsWith("/user-management/")) {
      if (!canViewUserManagement(role)) return <Navigate to="/communications" replace />;
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
      {/* <Route path="/forgot-password" element={<ForgotPassword />} /> */}

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
        <Route path="/user-management" element={<UserManagement />} />
        <Route path="/settings" element={<Settings />} />
      </Route>

      <Route path="/" element={<Navigate to="/login" replace />} />
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}


