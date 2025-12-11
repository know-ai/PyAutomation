import { Navigate, Outlet, Route, Routes } from "react-router-dom";
import { useAppSelector } from "../hooks/useAppSelector";
import { Login } from "../pages/Login";
import { Signup } from "../pages/Signup";
import { ForgotPassword } from "../pages/ForgotPassword";
import { Dashboard } from "../pages/Dashboard";
import { Communications } from "../pages/Communications";
import { Database } from "../pages/Database";
import { Tags } from "../pages/Tags";
import { Alarms } from "../pages/Alarms";
import { Machines } from "../pages/Machines";
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
      <Route path="/forgot-password" element={<ForgotPassword />} />

      <Route element={<ProtectedLayout />}>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/communications" element={<Communications />} />
        <Route path="/database" element={<Database />} />
        <Route path="/tags" element={<Tags />} />
        <Route path="/alarms" element={<Alarms />} />
        <Route path="/machines" element={<Machines />} />
      </Route>

      <Route path="/" element={<Navigate to="/login" replace />} />
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}


