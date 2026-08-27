import { useEffect, useMemo, useRef, useState } from "react";
import { socketService } from "../services/socket";
import {
  PROCESS_RESTART_EVENT,
  clearProcessRestart,
  markProcessRestartSawDown,
  pingProcessHealth,
  readProcessRestart,
  type ProcessRestartSession,
} from "../services/processRestart";

export type ProcessRestartPhase = "stopping" | "starting" | "connecting";

export type ProcessRestartOverlayState = {
  active: boolean;
  remainingMs: number;
  elapsedMs: number;
  progressPct: number;
  phase: ProcessRestartPhase;
  overtime: boolean;
};

const POLL_MS = 1500;
const TICK_MS = 250;
const MIN_HOLD_MS = 3000;
const PING_OK_STREAK = 2;
const SOCKET_WAIT_MS = 25_000;

export function useProcessRestartOverlay(): ProcessRestartOverlayState {
  const [session, setSession] = useState<ProcessRestartSession | null>(() =>
    readProcessRestart()
  );
  const [now, setNow] = useState(() => Date.now());
  const [socketConnected, setSocketConnected] = useState(
    () => socketService.getConnectionPhase() === "connected"
  );
  const [pingOk, setPingOk] = useState(true);
  const sawDownRef = useRef(Boolean(session?.sawDown));
  const okStreakRef = useRef(0);
  const pingUpSinceRef = useRef<number | null>(null);

  useEffect(() => {
    const sync = () => {
      const next = readProcessRestart();
      setSession(next);
      sawDownRef.current = Boolean(next?.sawDown);
      if (!next) {
        okStreakRef.current = 0;
        pingUpSinceRef.current = null;
      }
    };
    window.addEventListener(PROCESS_RESTART_EVENT, sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(PROCESS_RESTART_EVENT, sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  useEffect(() => {
    if (!session) return undefined;
    setNow(Date.now());
    const id = window.setInterval(() => setNow(Date.now()), TICK_MS);
    return () => window.clearInterval(id);
  }, [session]);

  useEffect(() => {
    return socketService.onConnectionChange(({ connected }) => {
      setSocketConnected(connected);
    });
  }, []);

  useEffect(() => {
    if (!session) return undefined;
    let cancelled = false;

    const poll = async () => {
      const ok = await pingProcessHealth();
      if (cancelled) return;
      setPingOk(ok);
      if (!ok) {
        okStreakRef.current = 0;
        pingUpSinceRef.current = null;
        if (!sawDownRef.current) {
          sawDownRef.current = true;
          markProcessRestartSawDown();
        }
        return;
      }
      okStreakRef.current += 1;
      if (pingUpSinceRef.current == null && sawDownRef.current) {
        pingUpSinceRef.current = Date.now();
      }
    };

    void poll();
    const id = window.setInterval(() => {
      void poll();
    }, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [session]);

  useEffect(() => {
    if (!session) return;
    const elapsed = now - session.startedAt;
    if (elapsed < MIN_HOLD_MS) return;
    const pingReady = pingOk && okStreakRef.current >= PING_OK_STREAK;
    if (!pingReady) return;

    const socketWaitExpired =
      pingUpSinceRef.current != null && now - pingUpSinceRef.current >= SOCKET_WAIT_MS;

    if (sawDownRef.current) {
      if (socketConnected || socketWaitExpired) {
        clearProcessRestart();
      }
      return;
    }

    if (elapsed >= Math.max(session.etaMs, 20_000) && socketConnected) {
      clearProcessRestart();
    }
  }, [session, now, pingOk, socketConnected]);

  return useMemo(() => {
    if (!session) {
      return {
        active: false,
        remainingMs: 0,
        elapsedMs: 0,
        progressPct: 0,
        phase: "stopping" as const,
        overtime: false,
      };
    }
    const elapsedMs = Math.max(0, now - session.startedAt);
    const remainingMs = Math.max(0, session.etaMs - elapsedMs);
    const overtime = elapsedMs >= session.etaMs;
    const progressPct = Math.min(100, Math.round((elapsedMs / session.etaMs) * 100));
    let phase: ProcessRestartPhase = "stopping";
    if (sawDownRef.current && pingOk) {
      phase = "connecting";
    } else if (sawDownRef.current) {
      phase = "starting";
    }
    return {
      active: true,
      remainingMs,
      elapsedMs,
      progressPct,
      phase,
      overtime,
    };
  }, [session, now, pingOk, socketConnected]);
}
