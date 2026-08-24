import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type PropsWithChildren,
  type SetStateAction,
} from "react";
import {
  DB_HEALTH_EVENT,
  emitDatabaseHealth,
  getDatabaseHealth,
  reconnectRemoteDatabase,
  type DatabaseHealthResponse,
} from "../services/health";

/** Poll interval for /api/health/db (spec: ~10 s). */
export const DB_HEALTH_POLL_MS = 10_000;

export type DatabaseProbeState = {
  /** Last known `connected` from a reachable probe; null before first successful HTTP response. */
  connected: boolean | null;
  /** False when the last probe could not reach the HTTP API (network/backend down). */
  reachable: boolean;
  latencyMs: number | null;
  message: string;
  lastCheckedAt: number | null;
};

export type DatabaseStatusState = DatabaseProbeState & {
  reconnecting: boolean;
  retryCount: number;
  reconnect: () => Promise<void>;
};

const DatabaseProbeContext = createContext<DatabaseStatusState | null>(null);

function applySuccessfulProbe(
  data: DatabaseHealthResponse,
  setProbe: Dispatch<SetStateAction<DatabaseProbeState>>,
  setRetryCount: Dispatch<SetStateAction<number>>
) {
  setProbe({
    connected: Boolean(data.connected),
    reachable: true,
    latencyMs: data.latency_ms ?? null,
    message: data.message || "",
    lastCheckedAt: Date.now(),
  });
  if (data.connected) {
    setRetryCount(0);
  } else {
    setRetryCount((n) => n + 1);
  }
}

export function DatabaseStatusProvider({ children }: PropsWithChildren) {
  const [probe, setProbe] = useState<DatabaseProbeState>({
    connected: null,
    reachable: false,
    latencyMs: null,
    message: "",
    lastCheckedAt: null,
  });
  const [reconnecting, setReconnecting] = useState(false);
  const [retryCount, setRetryCount] = useState(0);
  const inFlight = useRef(false);

  const refresh = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      const data = await getDatabaseHealth();
      applySuccessfulProbe(data, setProbe, setRetryCount);
    } catch {
      setProbe((prev) => ({
        ...prev,
        reachable: false,
        lastCheckedAt: Date.now(),
      }));
      setRetryCount((n) => n + 1);
    } finally {
      inFlight.current = false;
    }
  }, []);

  const reconnect = useCallback(async () => {
    setReconnecting(true);
    try {
      const data = await reconnectRemoteDatabase();
      applySuccessfulProbe(data, setProbe, setRetryCount);
      emitDatabaseHealth(Boolean(data.connected));
    } catch {
      setProbe((prev) => ({
        ...prev,
        reachable: false,
        lastCheckedAt: Date.now(),
      }));
      setRetryCount((n) => n + 1);
    } finally {
      setReconnecting(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => {
      if (typeof document !== "undefined" && document.hidden) {
        return;
      }
      void refresh();
    }, DB_HEALTH_POLL_MS);
    return () => window.clearInterval(id);
  }, [refresh]);

  useEffect(() => {
    const onHealth = (event: Event) => {
      const connectedNow = Boolean(
        (event as CustomEvent<{ connected?: boolean }>).detail?.connected
      );
      setProbe((prev) => ({
        ...prev,
        connected: connectedNow,
        reachable: true,
        lastCheckedAt: Date.now(),
      }));
      if (connectedNow) {
        setRetryCount(0);
      }
    };
    window.addEventListener(DB_HEALTH_EVENT, onHealth);
    return () => window.removeEventListener(DB_HEALTH_EVENT, onHealth);
  }, []);

  const value = useMemo<DatabaseStatusState>(
    () => ({
      ...probe,
      reconnecting,
      retryCount,
      reconnect,
    }),
    [probe, reconnecting, retryCount, reconnect]
  );

  return (
    <DatabaseProbeContext.Provider value={value}>{children}</DatabaseProbeContext.Provider>
  );
}

export function useDatabaseProbe(): DatabaseProbeState {
  const ctx = useContext(DatabaseProbeContext);
  if (!ctx) {
    throw new Error("useDatabaseProbe must be used within DatabaseStatusProvider");
  }
  const { connected, reachable, latencyMs, message, lastCheckedAt } = ctx;
  return { connected, reachable, latencyMs, message, lastCheckedAt };
}

/** @deprecated Prefer useSystemHealth().dbStatus for indicator tone. */
export function useDatabaseConnected() {
  const ctx = useContext(DatabaseProbeContext);
  if (!ctx) {
    throw new Error("useDatabaseConnected must be used within DatabaseStatusProvider");
  }
  return {
    connected: ctx.connected,
    reconnecting: ctx.reconnecting,
    retryCount: ctx.retryCount,
    reconnect: ctx.reconnect,
  };
}

export function useDatabaseMetrics() {
  const ctx = useContext(DatabaseProbeContext);
  if (!ctx) {
    throw new Error("useDatabaseMetrics must be used within DatabaseStatusProvider");
  }
  return {
    latencyMs: ctx.latencyMs,
    message: ctx.message,
    lastCheckedAt: ctx.lastCheckedAt,
  };
}

export function useDatabaseStatus(): DatabaseStatusState {
  const ctx = useContext(DatabaseProbeContext);
  if (!ctx) {
    throw new Error("useDatabaseStatus must be used within DatabaseStatusProvider");
  }
  return ctx;
}
