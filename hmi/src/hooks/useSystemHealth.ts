import { useMemo } from "react";
import {
  useDatabaseProbe,
  type DatabaseProbeState,
} from "./useDatabaseStatus";
import { useSocketConnection, type SocketConnectionStatus } from "./useSocketConnection";

export type DbHealthStatus = "connected" | "disconnected" | "unknown";

export type SocketHealthStatus = "connected" | "disconnected" | "reconnecting";

export type SystemHealthState = {
  socketStatus: SocketConnectionStatus;
  /** Socket status normalized for indicators (connecting → reconnecting). */
  socketHealth: SocketHealthStatus;
  dbStatus: DbHealthStatus;
  socketConnected: boolean;
  /** Raw probe: last HTTP result when reachable; null before first success. */
  dbProbe: DatabaseProbeState;
  dbAlarmActive: boolean;
};

function normalizeSocketHealth(status: SocketConnectionStatus): SocketHealthStatus {
  if (status === "connected") return "connected";
  if (status === "disconnected") return "disconnected";
  return "reconnecting";
}

function isSocketLive(status: SocketConnectionStatus): boolean {
  return status === "connected" || status === "reconnecting" || status === "connecting";
}

/** Derive DB indicator state — never mark DB down solely because the socket/backend is unreachable. */
export function deriveDbStatus(
  socketStatus: SocketConnectionStatus,
  probe: Pick<DatabaseProbeState, "connected" | "reachable">
): DbHealthStatus {
  const socketUp = isSocketLive(socketStatus);

  if (socketUp) {
    if (!probe.reachable) {
      return "disconnected";
    }
    if (probe.connected === true) return "connected";
    if (probe.connected === false) return "disconnected";
    return "unknown";
  }

  // Socket down: keep last known DB state; do not infer DB outage from failed HTTP probes.
  if (probe.connected === true) return "connected";
  if (probe.connected === false) return "disconnected";
  return "unknown";
}

export function useSystemHealth(): SystemHealthState {
  const socketStatus = useSocketConnection();
  const dbProbe = useDatabaseProbe();

  const socketHealth = normalizeSocketHealth(socketStatus);
  const dbStatus = useMemo(
    () => deriveDbStatus(socketStatus, dbProbe),
    [socketStatus, dbProbe.connected, dbProbe.reachable]
  );

  return {
    socketStatus,
    socketHealth,
    dbStatus,
    socketConnected: socketStatus === "connected",
    dbProbe,
    dbAlarmActive: dbStatus === "disconnected" && isSocketLive(socketStatus),
  };
}
