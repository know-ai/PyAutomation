import { AppRoutes } from "./routes";
import { useDisplayDensity } from "./hooks/useDisplayDensity";
import { useAppSelector } from "./hooks/useAppSelector";
import { usePerformanceTrendSampler } from "./hooks/usePerformanceTrends";
import { canViewPerformance } from "./services/performance";
import { ProcessRestartOverlay } from "./components/ProcessRestartOverlay";

function App() {
  useDisplayDensity();
  const token = useAppSelector((state) => state.auth.token);
  const role = useAppSelector((state) => state.auth.user?.role);
  usePerformanceTrendSampler(Boolean(token) && canViewPerformance(role));
  return (
    <>
      <AppRoutes />
      <ProcessRestartOverlay />
    </>
  );
}

export default App;


