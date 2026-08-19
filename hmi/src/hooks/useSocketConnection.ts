import { useEffect, useState } from "react";
import { socketService } from "../services/socket";

export type SocketConnectionStatus = "connected" | "disconnected" | "connecting";

function resolveStatus(connected: boolean, connecting: boolean): SocketConnectionStatus {
  if (connecting) return "connecting";
  return connected ? "connected" : "disconnected";
}

export function useSocketConnection(): SocketConnectionStatus {
  const [status, setStatus] = useState<SocketConnectionStatus>(() =>
    resolveStatus(socketService.getIsConnected(), false)
  );

  useEffect(() => {
    return socketService.onConnectionChange(({ connected, connecting }) => {
      setStatus(resolveStatus(connected, connecting));
    });
  }, []);

  return status;
}
