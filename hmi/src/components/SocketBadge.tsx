import clsx from "clsx";
import { useSocketConnection } from "../hooks/useSocketConnection";
import { useTranslation } from "../hooks/useTranslation";

export function SocketBadge() {
  const { t } = useTranslation();
  const status = useSocketConnection();

  const level =
    status === "connected"
      ? "ok"
      : status === "reconnecting" || status === "connecting"
        ? "warn"
        : "alarm";
  const title =
    status === "connected"
      ? t("socket.badgeConnected")
      : status === "reconnecting"
        ? t("socket.badgeReconnecting")
        : status === "connecting"
          ? t("socket.badgeConnecting")
          : t("socket.badgeDisconnected");

  return (
    <span
      className={clsx("socket-badge", `socket-badge--${level}`)}
      title={title}
      aria-label={title}
    >
      <i className="bi bi-broadcast-pin" aria-hidden="true" />
    </span>
  );
}
