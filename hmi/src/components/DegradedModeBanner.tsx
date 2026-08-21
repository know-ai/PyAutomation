import { useTranslation } from "../hooks/useTranslation";
import { useDatabaseConnected } from "../hooks/useDatabaseStatus";

/** Persistent header banner when the historian link is down (degraded mode). */
export function DegradedModeBanner() {
  const { t } = useTranslation();
  const { connected, reconnecting, reconnect } = useDatabaseConnected();

  if (connected !== false) {
    return null;
  }

  return (
    <div
      className="alert alert-warning rounded-0 mb-0 py-2 px-3 d-flex flex-wrap align-items-center gap-2"
      role="status"
      aria-live="polite"
    >
      <i className="bi bi-exclamation-triangle-fill" aria-hidden="true" />
      <span className="me-auto">{t("dbHealth.degradedModeBanner")}</span>
      <button
        type="button"
        className="btn btn-sm btn-outline-dark"
        disabled={reconnecting}
        onClick={() => {
          void reconnect();
        }}
      >
        {reconnecting ? t("common.loading") : t("dbHealth.reconnect")}
      </button>
    </div>
  );
}
