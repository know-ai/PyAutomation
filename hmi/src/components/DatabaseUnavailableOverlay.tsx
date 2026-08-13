import { useLocation } from "react-router-dom";
import { isRemoteDbDependentPath } from "../config/dbDependentRoutes";
import { useDatabaseConnected } from "../hooks/useDatabaseStatus";
import { useTranslation } from "../hooks/useTranslation";

export function DatabaseUnavailableOverlay() {
  const { t } = useTranslation();
  const { pathname } = useLocation();
  const { connected, reconnecting, retryCount, reconnect } = useDatabaseConnected();

  if (connected !== false || !isRemoteDbDependentPath(pathname)) {
    return null;
  }

  return (
    <div className="db-unavailable-overlay" role="alertdialog" aria-modal="true" aria-labelledby="db-unavailable-title">
      <div className="db-unavailable-overlay__card">
        <div className="db-unavailable-overlay__led" aria-hidden="true" />
        <h2 id="db-unavailable-title" className="h5 mb-2">
          {t("dbHealth.overlayTitle")}
        </h2>
        <p className="mb-3">{t("dbHealth.overlayBody")}</p>
        <p className="small text-muted mb-3">
          {t("dbHealth.retryCount")}: {retryCount}
        </p>
        <button
          type="button"
          className="btn btn-warning"
          onClick={() => void reconnect()}
          disabled={reconnecting}
        >
          {reconnecting ? (
            <span className="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true" />
          ) : (
            <i className="bi bi-arrow-repeat me-2" />
          )}
          {t("dbHealth.reconnect")}
        </button>
      </div>
    </div>
  );
}
