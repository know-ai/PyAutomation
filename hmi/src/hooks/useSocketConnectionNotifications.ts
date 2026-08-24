import { useEffect, useRef } from "react";
import { socketService } from "../services/socket";
import { useTranslation } from "./useTranslation";
import { showToast } from "../utils/toast";

/** Minimum outage duration before showing connection lost/restored toasts. */
const TOAST_DEBOUNCE_MS = 2000;

/**
 * Non-intrusive Socket.IO connection toasts with debounce to avoid flicker on brief blips.
 */
export function useSocketConnectionNotifications(): void {
  const { t } = useTranslation();
  const prevConnectedRef = useRef(socketService.getIsConnected());
  const disconnectAtRef = useRef<number | null>(null);
  const lostTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lostToastShownRef = useRef(false);

  useEffect(() => {
    return socketService.onConnectionChange(({ connected, reconnect }) => {
      const prevConnected = prevConnectedRef.current;
      prevConnectedRef.current = connected;

      if (connected) {
        if (lostTimerRef.current) {
          clearTimeout(lostTimerRef.current);
          lostTimerRef.current = null;
        }
        const outageStart = disconnectAtRef.current;
        disconnectAtRef.current = null;
        if (
          reconnect &&
          outageStart !== null &&
          Date.now() - outageStart >= TOAST_DEBOUNCE_MS
        ) {
          showToast(t("socket.toastRestored"), "success");
        }
        lostToastShownRef.current = false;
        return;
      }

      if (!prevConnected) {
        return;
      }

      disconnectAtRef.current = Date.now();
      if (lostTimerRef.current) {
        clearTimeout(lostTimerRef.current);
      }
      lostTimerRef.current = setTimeout(() => {
        lostTimerRef.current = null;
        if (!socketService.getIsConnected() && !lostToastShownRef.current) {
          lostToastShownRef.current = true;
          showToast(t("socket.toastLost"), "warning");
        }
      }, TOAST_DEBOUNCE_MS);
    });
  }, [t]);
}
