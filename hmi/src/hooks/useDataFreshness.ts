import { useEffect, useState } from "react";
import { socketService } from "../services/socket";
import { useSocketConnection } from "./useSocketConnection";

/** No on.tag while socket is up → data considered stalled (LED warn). Mirrors SocketService.DATA_STALE_MS. */
export const DATA_STALE_MS = 5_000;

export type DataFreshnessState = {
  /** True when socket is connected but no on.tag for ≥ DATA_STALE_MS. */
  dataStale: boolean;
  lastOnTagAt: number | null;
  ageMs: number | null;
};

/**
 * Watchdog: detect RT data-plane stalls independently of Engine.IO transport state.
 * Arms after the socket reaches "connected"; resets on every on.tag.
 */
export function useDataFreshness(): DataFreshnessState {
  const socketStatus = useSocketConnection();
  const [lastOnTagAt, setLastOnTagAt] = useState<number | null>(() =>
    socketService.getLastOnTagAt()
  );
  const [now, setNow] = useState(() => Date.now());
  const [armedAt, setArmedAt] = useState<number | null>(null);

  useEffect(() => {
    return socketService.onTagActivity((at) => {
      setLastOnTagAt(at);
    });
  }, []);

  useEffect(() => {
    if (socketStatus === "connected") {
      setArmedAt((prev) => prev ?? Date.now());
      return;
    }
    setArmedAt(null);
  }, [socketStatus]);

  useEffect(() => {
    if (socketStatus !== "connected") {
      return;
    }
    const id = window.setInterval(() => setNow(Date.now()), 500);
    return () => window.clearInterval(id);
  }, [socketStatus]);

  if (socketStatus !== "connected" || armedAt === null) {
    return { dataStale: false, lastOnTagAt, ageMs: null };
  }

  const baseline = lastOnTagAt ?? armedAt;
  const ageMs = Math.max(0, now - baseline);
  return {
    dataStale: ageMs >= DATA_STALE_MS,
    lastOnTagAt,
    ageMs,
  };
}
