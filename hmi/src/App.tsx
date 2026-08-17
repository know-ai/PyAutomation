import { AppRoutes } from "./routes";
import { useDisplayDensity } from "./hooks/useDisplayDensity";

function App() {
  useDisplayDensity();
  return <AppRoutes />;
}

export default App;


