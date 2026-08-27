import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { useProcessRestartOverlay } from "../hooks/useProcessRestartOverlay";
import { useTranslation } from "../hooks/useTranslation";
import { showToast } from "../utils/toast";

function formatClock(ms: number): string {
  const total = Math.max(0, Math.ceil(ms / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

export function ProcessRestartOverlay() {
  const { t } = useTranslation();
  const { active, remainingMs, elapsedMs, progressPct, phase, overtime } =
    useProcessRestartOverlay();
  const wasActive = useRef(false);

  useEffect(() => {
    if (wasActive.current && !active) {
      showToast(t("processRestart.ready"), "success");
    }
    wasActive.current = active;
  }, [active, t]);

  useEffect(() => {
    if (!active) return undefined;
    document.body.classList.add("process-restart-lock");
    const onKeyDown = (event: KeyboardEvent) => {
      event.preventDefault();
      event.stopPropagation();
    };
    window.addEventListener("keydown", onKeyDown, true);
    return () => {
      document.body.classList.remove("process-restart-lock");
      window.removeEventListener("keydown", onKeyDown, true);
    };
  }, [active]);

  if (!active) return null;

  const phaseKey =
    phase === "starting"
      ? "processRestart.waitingUp"
      : phase === "connecting"
        ? "processRestart.waitingSocket"
        : "processRestart.waitingDown";

  return createPortal(
    <div
      className="process-restart-overlay"
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="process-restart-title"
      aria-describedby="process-restart-body"
    >
      <div className="process-restart-overlay__card">
        <div className="spinner-border text-warning mb-3" role="status" aria-hidden="true" />
        <h2 id="process-restart-title" className="h5 mb-2">
          {t("processRestart.title")}
        </h2>
        <p id="process-restart-body" className="mb-3">
          {t("processRestart.body")}
        </p>
        <p className="small text-muted mb-3">{t(phaseKey)}</p>
        <div
          className="progress process-restart-overlay__bar mb-3"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={overtime ? undefined : progressPct}
        >
          <div
            className="progress-bar progress-bar-striped progress-bar-animated bg-warning"
            style={{ width: overtime ? "100%" : `${Math.max(6, progressPct)}%` }}
          />
        </div>
        <p className="process-restart-overlay__eta mb-1">
          {overtime
            ? t("processRestart.overtime")
            : t("processRestart.remaining", { time: formatClock(remainingMs) })}
        </p>
        <p className="small text-muted mb-0">
          {t("processRestart.elapsed", { time: formatClock(elapsedMs) })}
        </p>
      </div>
    </div>,
    document.body
  );
}
