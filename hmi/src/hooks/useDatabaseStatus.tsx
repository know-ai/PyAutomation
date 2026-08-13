import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PropsWithChildren,
} from "react";
import {
  DB_HEALTH_EVENT,
  emitDatabaseHealth,
  getDatabaseHealth,
  reconnectRemoteDatabase,
  type DatabaseHealthResponse,
} from "../services/health";

export const DB_HEALTH_POLL_MS = 8000;

export type DatabaseStatusState = {
  connected: boolean | null;
  latencyMs: number | null;
  message: string;
  lastCheckedAt: number | null;
  reconnecting: boolean;
  retryCount: number;
  reconnect: () => Promise<void>;
};

const DatabaseStatusContext = createContext<DatabaseStatusState | null>(null);

function applySnapshot(
  data: DatabaseHealthResponse,
  setConnected: (v: boolean) => void,
  setLatencyMs: (v: number | null) => void,
  setMessage: (v: string) => void,
  setLastCheckedAt: (v: number) => void,
  setRetryCount: (fn: (n: number) => number) => void
) {
  setConnected(Boolean(data.connected));
  setLatencyMs(data.latency_ms ?? null);
  setMessage(data.message || "");
  setLastCheckedAt(Date.now());
  if (data.connected) {
    setRetryCount(() => 0);
  } else {
    setRetryCount((n) => n + 1);
  }
}

export function DatabaseStatusProvider({ children }: PropsWithChildren) {
  const [connected, setConnected] = useState<boolean | null>(null);
  const [latencyMs, setLatencyMs] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const [lastCheckedAt, setLastCheckedAt] = useState<number | null>(null);
  const [reconnecting, setReconnecting] = useState(false);
  const [retryCount, setRetryCount] = useState(0);
  const inFlight = useRef(false);

  const refresh = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      const data = await getDatabaseHealth();
      applySnapshot(data, setConnected, setLatencyMs, setMessage, setLastCheckedAt, setRetryCount);
    } catch {
      setConnected(false);
      setLatencyMs(null);
      setLastCheckedAt(Date.now());
      setRetryCount((n) => n + 1);
    } finally {
      inFlight.current = false;
    }
  }, []);

  const reconnect = useCallback(async () => {
    setReconnecting(true);
    try {
      const data = await reconnectRemoteDatabase();
      applySnapshot(data, setConnected, setLatencyMs, setMessage, setLastCheckedAt, setRetryCount);
      emitDatabaseHealth(Boolean(data.connected));
    } catch {
      setConnected(false);
      setLastCheckedAt(Date.now());
      setRetryCount((n) => n + 1);
      emitDatabaseHealth(false);
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
      const connectedNow = Boolean((event as CustomEvent<{ connected?: boolean }>).detail?.connected);
      setConnected(connectedNow);
      setLastCheckedAt(Date.now());
      if (connectedNow) {
        setRetryCount(0);
      }
    };
    window.addEventListener(DB_HEALTH_EVENT, onHealth);
    return () => window.removeEventListener(DB_HEALTH_EVENT, onHealth);
  }, []);

  const value = useMemo<DatabaseStatusState>(
    () => ({
      connected,
      latencyMs,
      message,
      lastCheckedAt,
      reconnecting,
      retryCount,
      reconnect,
    }),
    [connected, latencyMs, message, lastCheckedAt, reconnecting, retryCount, reconnect]
  );

  return <DatabaseStatusContext.Provider value={value}>{children}</DatabaseStatusContext.Provider>;
}

export function useDatabaseStatus(): DatabaseStatusState {
  const ctx = useContext(DatabaseStatusContext);
  if (!ctx) {
    throw new Error("useDatabaseStatus must be used within DatabaseStatusProvider");
  }
  return ctx;
}
