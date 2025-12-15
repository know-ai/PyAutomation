import { Navigate, Outlet, Route, Routes } from "react-router-dom";
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
import { UserManagement } from "../pages/UserManagement";
import { Settings } from "../pages/Settings";
import { Events } from "../pages/Events";
import { OperationalLogs } from "../pages/OperationalLogs";
// import { Performance } from "../pages/Performance";
import { MainLayout } from "../layouts/MainLayout";

function ProtectedLayout() {
  const isAuth = useAppSelector((s) => !!s.auth.token);
  if (!isAuth) return <Navigate to="/login" replace />;
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
        <Route path="/machines" element={<Machines />} />
        <Route path="/events" element={<Events />} />
        <Route path="/operational-logs" element={<OperationalLogs />} />
        {/* <Route path="/performance" element={<Performance />} /> */}
        <Route path="/user-management" element={<UserManagement />} />
        <Route path="/settings" element={<Settings />} />
      </Route>

      <Route path="/" element={<Navigate to="/login" replace />} />
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}


