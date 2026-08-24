import clsx from "clsx";
import { useSystemHealth } from "../hooks/useSystemHealth";
import { useTranslation } from "../hooks/useTranslation";

export function SocketBadge() {
  const { t } = useTranslation();
  const { socketStatus, socketHealth } = useSystemHealth();

  const level =
    socketHealth === "connected"
      ? "ok"
      : socketHealth === "reconnecting"
        ? "warn"
        : "alarm";
  const title =
    socketStatus === "connected"
      ? t("socket.badgeConnected")
      : socketStatus === "reconnecting"
        ? t("socket.badgeReconnecting")
        : socketStatus === "connecting"
          ? t("socket.badgeConnecting")
          : t("socket.badgeDisconnected");

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
