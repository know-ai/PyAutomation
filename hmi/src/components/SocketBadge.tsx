import clsx from "clsx";
import { useSystemHealth } from "../hooks/useSystemHealth";
import { useTranslation } from "../hooks/useTranslation";

export function SocketBadge() {
  const { t } = useTranslation();
  const { socketStatus, socketHealth, rtReason } = useSystemHealth();

  const level =
    socketHealth === "connected"
      ? "ok"
      : socketHealth === "reconnecting"
        ? "warn"
        : "alarm";

  let title: string;
  if (rtReason === "data-stale") {
    title = t("socket.badgeDataStale");
  } else if (socketStatus === "connected") {
    title = t("socket.badgeConnected");
  } else if (socketStatus === "reconnecting") {
    title = t("socket.badgeReconnecting");
  } else if (socketStatus === "connecting") {
    title = t("socket.badgeConnecting");
  } else {
    title = t("socket.badgeDisconnected");
  }

  return (
    <span
      className={clsx("socket-badge", `socket-badge--${level}`)}
      title={title}
      aria-label={`${t("socket.indicatorLabel")}: ${title}`}
    >
      <span className="socket-badge__tag" aria-hidden="true">
        {t("socket.indicatorShort")}
      </span>
      <i className="bi bi-broadcast-pin" aria-hidden="true" />
    </span>
  );
}
