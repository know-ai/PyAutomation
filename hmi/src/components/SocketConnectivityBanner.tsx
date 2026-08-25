import { FloatingStatusBanner } from "./FloatingStatusBanner";
import { useSystemHealth } from "../hooks/useSystemHealth";
import { useTranslation } from "../hooks/useTranslation";

const POSITION_KEY = "pya.socketConnectivityBanner.pos";

/**
 * Floating Socket.IO / RT data notice (transport down or data stalled).
 * Same UX as DB degraded banner: overlay, draggable, no layout shift.
 * Stacks vertically with the DB banner when both are visible.
 */
export function SocketConnectivityBanner() {
  const { t } = useTranslation();
  const { socketStatus, dataStale, rtReason } = useSystemHealth();

  const transportDown = socketStatus !== "connected";
  const stalled = rtReason === "data-stale" && dataStale;
  const visible = transportDown || stalled;

  let text = t("realTimeTrends.socketReconnecting");
  let tone: "warning" | "danger" = "warning";
  let icon = "bi bi-broadcast-pin";

  if (stalled && !transportDown) {
    text = t("realTimeTrends.dataStalled");
    tone = "warning";
    icon = "bi bi-hourglass-split";
  } else if (socketStatus === "disconnected") {
    text = t("realTimeTrends.waitingSocket");
    tone = "danger";
    icon = "bi bi-wifi-off";
  } else if (socketStatus === "reconnecting" || socketStatus === "connecting") {
    text = t("realTimeTrends.socketReconnecting");
    tone = "warning";
    icon = "bi bi-arrow-repeat";
  }

  return (
    <FloatingStatusBanner
      id="socket"
      storageKey={POSITION_KEY}
      visible={visible}
      text={text}
      ariaLabel={text}
      moveLabel={t("socket.bannerMove")}
      tone={tone}
      iconClassName={icon}
    />
  );
}
