import { useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "./Button";
import { useTranslation } from "../hooks/useTranslation";
import { acknowledgeAlarm, executeAlarmAction, shelveAlarm, type Alarm } from "../services/alarms";
import {
  formatThresholdLabel,
  lifecycleOf,
  type PerfAlarmLifecycle,
} from "../services/performanceAlarms";
import type { PerfAlarmCatalogEntry } from "../services/performance";
import { showToast } from "../utils/toast";
import { alarmStateBadgeClass } from "../utils/alarmState";
import { translateAlarmDescription } from "../utils/alarmCatalog";

type PerformanceAlarmModalProps = {
  open: boolean;
  title: string;
  valueLabel: string;
  canConfigure?: boolean;
  alarm?: Alarm;
  catalog?: PerfAlarmCatalogEntry;
  onClose: () => void;
  onConfigure?: () => void;
};

function stateLabel(life: PerfAlarmLifecycle, t: (key: string) => string): string {
  if (life === "unack") return t("performance.alarmUnack");
  if (life === "ack") return t("performance.alarmAcked");
  if (life === "shelved") return t("performance.alarmShelved");
  if (life === "normal") return t("performance.alarmNormal");
  return t("performance.alarmUnknown");
}

export function PerformanceAlarmModal({
  open,
  title,
  valueLabel,
  canConfigure = false,
  alarm,
  catalog,
  onClose,
  onConfigure,
}: PerformanceAlarmModalProps) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const life = lifecycleOf(alarm);

  if (!open) return null;

  const run = async (action: () => Promise<unknown>, successKey: string) => {
    if (!alarm?.name || busy) return;
    setBusy(true);
    try {
      await action();
      showToast(t(successKey), "success");
    } catch (error: any) {
      showToast(error?.response?.data?.message || t("performance.alarmActionError"), "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="modal fade show d-block perf-alarm-modal"
      tabIndex={-1}
      role="dialog"
      aria-modal="true"
      onClick={onClose}
    >
      <div className="modal-dialog modal-dialog-centered" role="document" onClick={(event) => event.stopPropagation()}>
        <div className="modal-content">
          <div className="modal-header">
            <div>
              <h5 className="modal-title mb-1">{title}</h5>
              <span className={alarmStateBadgeClass(alarm?.state)}>{stateLabel(life, t)}</span>
            </div>
            <button type="button" className="btn-close" aria-label={t("common.close")} onClick={onClose} />
          </div>
          <div className="modal-body">
            <p className="perf-alarm-modal__hero">{valueLabel}</p>
            <dl className="perf-alarm-modal__facts">
              <div>
                <dt>{t("performance.alarmName")}</dt>
                <dd>{alarm?.name || catalog?.alarm || "—"}</dd>
              </div>
              <div>
                <dt>{t("performance.alarmThreshold")}</dt>
                <dd>{formatThresholdLabel(catalog?.threshold, catalog?.unit) || "—"}</dd>
              </div>
              {alarm?.description || alarm?.name ? (
                <div>
                  <dt>{t("tables.description")}</dt>
                  <dd>{translateAlarmDescription(alarm?.description, alarm?.name, t)}</dd>
                </div>
              ) : null}
            </dl>
            <Link className="perf-alarm-modal__events" to="/events">
              {t("performance.alarmEventsLink")}
            </Link>
          </div>
          <div className="modal-footer">
            {life === "unack" ? (
              <Button
                variant="warning"
                disabled={busy}
                onClick={() => void run(() => acknowledgeAlarm(alarm!.name), "performance.alarmAckOk")}
              >
                {t("performance.alarmAck")}
              </Button>
            ) : null}
            {life === "unack" || life === "ack" ? (
              <Button
                variant="secondary"
                disabled={busy}
                onClick={() => void run(() => shelveAlarm(alarm!.name, { hours: 1 }), "performance.alarmShelveOk")}
              >
                {t("performance.alarmShelve")}
              </Button>
            ) : null}
            {life === "shelved" ? (
              <Button
                variant="secondary"
                disabled={busy}
                onClick={() => void run(() => executeAlarmAction("unshelve", alarm!.name), "performance.alarmUnshelveOk")}
              >
                {t("performance.alarmUnshelve")}
              </Button>
            ) : null}
            {canConfigure && onConfigure ? (
              <Button
                variant="secondary"
                onClick={() => {
                  onConfigure();
                }}
              >
                {t("performance.alarmConfigure")}
              </Button>
            ) : null}
            <Button variant="primary" onClick={onClose}>
              {t("common.close")}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
