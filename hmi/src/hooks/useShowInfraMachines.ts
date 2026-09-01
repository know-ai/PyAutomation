import { useCallback, useEffect, useState } from "react";
import {
  loadShowInfraMachines,
  persistShowInfraMachines,
  SHOW_INFRA_MACHINES_KEY,
} from "../utils/infraMachines";

export function useShowInfraMachines() {
  const [showInfra, setShow] = useState(loadShowInfraMachines);

  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key === SHOW_INFRA_MACHINES_KEY) {
        setShow(event.newValue === "true");
      }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const setShowInfra = useCallback((next: boolean) => {
    persistShowInfraMachines(next);
    setShow(next);
  }, []);

  return { showInfra, setShowInfra };
}
