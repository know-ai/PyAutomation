import { useMemo, useState } from "react";
import clsx from "clsx";
import { useDatabaseStatus } from "../hooks/useDatabaseStatus";
import { useSystemHealth } from "../hooks/useSystemHealth";
import { useTranslation } from "../hooks/useTranslation";

function formatCheckedAt(ts: number | null, locale: string): string {
  if (!ts) return "—";
  return new Date(ts).toLocaleTimeString(locale === "es" ? "es-PE" : "en-US");
}

export function DatabaseStatus({ compact = false }: { compact?: boolean }) {
  const { t, locale } = useTranslation();
  const { dbStatus, socketHealth } = useSystemHealth();
  const { latencyMs, message, lastCheckedAt, reconnecting, reconnect } = useDatabaseStatus();
  const [open, setOpen] = useState(false);

  const tone =
    dbStatus === "connected" ? "ok" : dbStatus === "disconnected" ? "error" : "unknown";
  const label =
    dbStatus === "connected"
      ? t("dbHealth.connected")
      : dbStatus === "disconnected"
        ? t("dbHealth.disconnected")
        : t("dbHealth.unknown");

  const tooltip = useMemo(() => {
    const lines = [
      `${t("dbHealth.status")}: ${label}`,
      dbStatus === "connected"
        ? `${t("dbHealth.latency")}: ${latencyMs != null ? `${Math.round(latencyMs)} ms` : "—"}`
        : null,
      `${t("dbHealth.lastCheck")}: ${formatCheckedAt(lastCheckedAt, locale)}`,
      socketHealth === "disconnected" ? t("dbHealth.staleWhileSocketDown") : null,
      message || null,
    ];
    return lines.filter(Boolean).join("\n");
  }, [dbStatus, label, lastCheckedAt, latencyMs, locale, message, socketHealth, t]);

  return (
    <div
      className={clsx("db-health", compact && "db-health--compact")}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      <button
        type="button"
        className="db-health__trigger"
        title={tooltip}
        aria-label={`${t("dbHealth.indicatorLabel")}: ${label}`}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="db-health__tag" aria-hidden="true">
          {t("dbHealth.indicatorShort")}
        </span>
        <span className={`db-health__led db-health__led--${tone}`} aria-hidden="true" />
        {!compact && <span className="d-none d-xl-inline small">{label}</span>}
      </button>
      {open && (
        <div className="db-health__tooltip" role="status">
          <div className="fw-semibold mb-1">{t("dbHealth.title")}</div>
          <div>
            {t("dbHealth.status")}: {label}
          </div>
          {dbStatus === "connected" && (
            <div>
              {t("dbHealth.latency")}: {latencyMs != null ? `${Math.round(latencyMs)} ms` : "—"}
            </div>
          )}
          <div>
            {t("dbHealth.lastCheck")}: {formatCheckedAt(lastCheckedAt, locale)}
          </div>
          {socketHealth === "disconnected" && dbStatus !== "disconnected" && (
            <div className="text-muted small mt-1">{t("dbHealth.staleWhileSocketDown")}</div>
          )}
          {message && <div className="text-muted small mt-1">{message}</div>}
          {dbStatus === "disconnected" && socketHealth !== "disconnected" && (
            <button
              type="button"
              className="btn btn-sm btn-warning mt-2"
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                void reconnect();
              }}
              disabled={reconnecting}
            >
              {reconnecting ? (
                <span className="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true" />
              ) : (
                <i className="bi bi-arrow-repeat me-1" />
              )}
              {t("dbHealth.reconnect")}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
