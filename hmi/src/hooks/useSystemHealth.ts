import { useMemo } from "react";
import {
  useDatabaseProbe,
  type DatabaseProbeState,
} from "./useDatabaseStatus";
import { useDataFreshness } from "./useDataFreshness";
import { useSocketConnection, type SocketConnectionStatus } from "./useSocketConnection";

export type DbHealthStatus = "connected" | "disconnected" | "unknown";

export type SocketHealthStatus = "connected" | "disconnected" | "reconnecting";

/** Why the RT LED is not green (transport vs data-plane stall). */
export type RtIndicatorReason = "transport" | "data-stale" | null;

export type SystemHealthState = {
  socketStatus: SocketConnectionStatus;
  /**
   * Combined RT indicator: transport phase, or "reconnecting" (warn) when
   * socket is up but on.tag freshness watchdog tripped.
   */
  socketHealth: SocketHealthStatus;
  /** Transport-only phase (ignores data freshness). */
  transportHealth: SocketHealthStatus;
  dataStale: boolean;
  rtReason: RtIndicatorReason;
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

/** Combine transport phase with data-freshness watchdog for the RT LED. */
export function deriveRtSocketHealth(
  socketStatus: SocketConnectionStatus,
  dataStale: boolean
): { socketHealth: SocketHealthStatus; rtReason: RtIndicatorReason } {
  const transportHealth = normalizeSocketHealth(socketStatus);
  if (transportHealth !== "connected") {
    return { socketHealth: transportHealth, rtReason: "transport" };
  }
  if (dataStale) {
    return { socketHealth: "reconnecting", rtReason: "data-stale" };
  }
  return { socketHealth: "connected", rtReason: null };
}

export function useSystemHealth(): SystemHealthState {
  const socketStatus = useSocketConnection();
  const dbProbe = useDatabaseProbe();
  const { dataStale } = useDataFreshness();

  const transportHealth = normalizeSocketHealth(socketStatus);
  const { socketHealth, rtReason } = useMemo(
    () => deriveRtSocketHealth(socketStatus, dataStale),
    [socketStatus, dataStale]
  );
  const dbStatus = useMemo(
    () => deriveDbStatus(socketStatus, dbProbe),
    [socketStatus, dbProbe.connected, dbProbe.reachable]
  );

  return {
    socketStatus,
    socketHealth,
    transportHealth,
    dataStale,
    rtReason,
    dbStatus,
    socketConnected: socketStatus === "connected",
    dbProbe,
    dbAlarmActive: dbStatus === "disconnected" && isSocketLive(socketStatus),
  };
}
