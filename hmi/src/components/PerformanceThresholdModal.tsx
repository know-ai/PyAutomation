import { useEffect, useMemo, useState } from "react";
import { Button } from "./Button";
import { useTranslation } from "../hooks/useTranslation";
import {
  formatThresholdLabel,
  previewExceeds,
  updatePerformanceAlarmConfig,
  PERF_ALARM_UNITS,
} from "../services/performanceAlarms";
import type { PerfAlarmCatalogEntry, PerfAlarmKey, PerfAlarmsCatalog } from "../services/performance";
import { showToast } from "../utils/toast";

type PerformanceThresholdModalProps = {
  open: boolean;
  alarmKey: PerfAlarmKey | null;
  title: string;
  currentValue?: number | null;
  currentLabel: string;
  catalog?: PerfAlarmCatalogEntry;
  debounceCount?: number;
  onClose: () => void;
  onSaved?: (catalog: PerfAlarmsCatalog) => void;
};

export function PerformanceThresholdModal({
  open,
  alarmKey,
  title,
  currentValue,
  currentLabel,
  catalog,
  debounceCount = 3,
  onClose,
  onSaved,
}: PerformanceThresholdModalProps) {
  const { t } = useTranslation();
  const [threshold, setThreshold] = useState(Number(catalog?.threshold ?? 0));
  const [debounce, setDebounce] = useState(debounceCount);
  const [enabled, setEnabled] = useState(catalog?.enabled !== false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setThreshold(Number(catalog?.threshold ?? 0));
    setDebounce(debounceCount);
    setEnabled(catalog?.enabled !== false);
  }, [open, catalog, debounceCount]);

  const unit = catalog?.unit || (alarmKey ? PERF_ALARM_UNITS[alarmKey] : "");
  const wouldExceed = useMemo(
    () => enabled && previewExceeds(currentValue, threshold),
    [currentValue, threshold, enabled]
  );

  if (!open || !alarmKey) return null;

  const save = async () => {
    setSaving(true);
    try {
      const next = await updatePerformanceAlarmConfig({
        debounce_count: debounce,
        alarms: [{ key: alarmKey, enabled, threshold }],
      });
      showToast(t("performance.configSaved"), "success");
      onSaved?.(next);
      onClose();
    } catch (error: any) {
      showToast(error?.response?.data?.message || t("performance.configSaveError"), "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal fade show d-block perf-alarm-modal" tabIndex={-1} role="dialog" aria-modal="true" onClick={onClose}>
      <div className="modal-dialog modal-dialog-centered" role="document" onClick={(event) => event.stopPropagation()}>
        <div className="modal-content">
          <div className="modal-header">
            <h5 className="modal-title">{t("performance.configModalTitle", { name: title })}</h5>
            <button type="button" className="btn-close" aria-label={t("common.close")} onClick={onClose} />
          </div>
          <div className="modal-body">
            <p className="perf-config__current">
              {t("performance.configCurrent", { value: currentLabel })}
              <span className={wouldExceed ? "text-danger" : "text-success"}>
                {" "}
                ({wouldExceed ? t("performance.configWouldAlarm") : t("performance.configWouldNormal")})
              </span>
            </p>
            <label className="form-check mb-3">
              <input
                className="form-check-input"
                type="checkbox"
                checked={enabled}
                onChange={(event) => setEnabled(event.target.checked)}
              />
              <span className="form-check-label">{t("performance.configEnabledOne")}</span>
            </label>
            <div className="mb-3">
              <label className="form-label" htmlFor="perf-th">
                {t("performance.configThreshold")}
              </label>
              <div className="input-group">
                <input
                  id="perf-th"
                  className="form-control"
                  type="number"
                  value={threshold}
                  onChange={(event) => setThreshold(Number(event.target.value))}
                />
                {unit ? <span className="input-group-text">{unit}</span> : null}
              </div>
              <div className="form-text">{formatThresholdLabel(threshold, unit)}</div>
            </div>
            <div>
              <label className="form-label" htmlFor="perf-db">
                {t("performance.configDebounce")}
              </label>
              <input
                id="perf-db"
                className="form-control"
                type="number"
                min={1}
                max={12}
                value={debounce}
                onChange={(event) => setDebounce(Number(event.target.value))}
              />
              <div className="form-text">{t("performance.configDebounceHint")}</div>
            </div>
          </div>
          <div className="modal-footer">
            <Button variant="secondary" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button variant="primary" loading={saving} onClick={() => void save()}>
              {t("common.save")}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
