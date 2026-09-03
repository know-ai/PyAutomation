import { AppRoutes } from "./routes";
import { useDisplayDensity } from "./hooks/useDisplayDensity";
import { useAppSelector } from "./hooks/useAppSelector";
import { usePerformanceTrendSampler } from "./hooks/usePerformanceTrends";
import { hasAction, VIEW_IDS } from "./utils/access";
import { ProcessRestartOverlay } from "./components/ProcessRestartOverlay";

function App() {
  useDisplayDensity();
  const token = useAppSelector((state) => state.auth.token);
  const views = useAppSelector((state) => state.authz.views);
  usePerformanceTrendSampler(Boolean(token) && hasAction(views, VIEW_IDS.performance, "view"));
  return (
    <>
      <AppRoutes />
      <ProcessRestartOverlay />
    </>
  );
}

export default App;


