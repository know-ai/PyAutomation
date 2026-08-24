import { useEffect, useState } from "react";
import {
  socketService,
  type SocketConnectionPhase,
} from "../services/socket";

export type SocketConnectionStatus = SocketConnectionPhase;

export function useSocketConnection(): SocketConnectionStatus {
  const [status, setStatus] = useState<SocketConnectionStatus>(() =>
    socketService.getConnectionPhase()
  );

  useEffect(() => {
    return socketService.onConnectionChange(({ phase }) => {
      setStatus(phase);
    });
  }, []);

  return status;
}
