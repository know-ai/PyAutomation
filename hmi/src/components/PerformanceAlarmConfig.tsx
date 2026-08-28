import { useCallback, useEffect, useState } from "react";
import { Button } from "./Button";
import { SettingsChapter } from "./SettingsChapter";
import { useAppSelector } from "../hooks/useAppSelector";
import { useTranslation } from "../hooks/useTranslation";
import {
  canConfigurePerformanceAlarms,
  getPerformanceAlarmConfig,
  updatePerformanceAlarmConfig,
  PERF_ALARM_UNITS,
  type PerformanceAlarmConfig,
} from "../services/performanceAlarms";
import { PERF_ALARM_KEYS, type PerfAlarmKey } from "../services/performance";
import { showToast } from "../utils/toast";

const LABEL_KEYS: Record<PerfAlarmKey, string> = {
  cpu: "performance.cpu",
  disk: "performance.disk",
  saf_queue: "performance.safQueue",
  saf_lag: "performance.safLag",
  metrics_age: "performance.metricsAge",
  db_conn: "performance.dbConnections",
  http_5xx: "performance.http5xx",
  field_stale: "performance.fieldStale",
  saf_deadletter: "performance.safDeadletter",
  hub_lag: "performance.hubLag",
  saf_shed: "performance.safShed",
  saf_ingest: "performance.safIngest",
  saf_rate: "performance.safRate",
  ssd: "performance.ssd",
  ntp: "performance.ntp",
  node_down: "performance.peerDown",
};

type Row = {
  key: PerfAlarmKey;
  enabled: boolean;
  threshold: number;
};

function rowsFromConfig(config: PerformanceAlarmConfig): Row[] {
  const byKey = new Map((config.alarms || []).map((item) => [String(item.key), item]));
  return PERF_ALARM_KEYS.map((key) => {
    const item = byKey.get(key);
    const fallback = Number((config as Record<string, unknown>)[`perf_${key}_threshold`] ?? 0);
    return {
      key,
      enabled: item?.enabled !== false,
      threshold: Number(item?.threshold ?? fallback),
    };
  });
}

export function PerformanceAlarmConfig() {
  const { t } = useTranslation();
  const role = useAppSelector((state) => state.auth.user?.role);
  const canEdit = canConfigurePerformanceAlarms(role);
  const [enabled, setEnabled] = useState(true);
  const [debounce, setDebounce] = useState(3);
  const [rows, setRows] = useState<Row[]>(rowsFromConfig({}));
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const config = await getPerformanceAlarmConfig();
      setEnabled(config.enabled !== false);
      setDebounce(Number(config.debounce_count ?? 3));
      setRows(rowsFromConfig(config));
    } catch (error: any) {
      showToast(error?.response?.data?.message || t("performance.configLoadError"), "error");
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const save = async () => {
    setSaving(true);
    try {
      await updatePerformanceAlarmConfig({
        enabled,
        debounce_count: debounce,
        alarms: rows.map((row) => ({
          key: row.key,
          enabled: row.enabled,
          threshold: row.threshold,
        })),
      });
      showToast(t("performance.configSaved"), "success");
      await load();
    } catch (error: any) {
      showToast(error?.response?.data?.message || t("performance.configSaveError"), "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <SettingsChapter
      id="settings-performance"
      index="03"
      kicker={t("settings.perfAlarmsKicker")}
      title={t("settings.perfAlarmsTitle")}
      lede={t("settings.perfAlarmsLede")}
    >
      <article className="settings-tile">
        <label className="form-check mb-3">
          <input
            className="form-check-input"
            type="checkbox"
            checked={enabled}
            disabled={!canEdit || loading}
            onChange={(event) => setEnabled(event.target.checked)}
          />
          <span className="form-check-label">{t("performance.configEnabled")}</span>
        </label>
        <div className="mb-3" style={{ maxWidth: "12rem" }}>
          <label className="form-label" htmlFor="perf-debounce">
            {t("performance.configDebounce")}
          </label>
          <input
            id="perf-debounce"
            className="form-control"
            type="number"
            min={1}
            max={12}
            value={debounce}
            disabled={!canEdit || loading}
            onChange={(event) => setDebounce(Number(event.target.value))}
          />
          <div className="form-text">{t("performance.configDebounceHint")}</div>
        </div>
        <div className="table-responsive">
          <table className="table table-sm align-middle mb-3">
            <thead>
              <tr>
                <th>{t("performance.configAlarm")}</th>
                <th>{t("performance.configOn")}</th>
                <th>{t("performance.configThreshold")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={row.key}>
                  <td>{t(LABEL_KEYS[row.key])}</td>
                  <td>
                    <input
                      className="form-check-input"
                      type="checkbox"
                      checked={row.enabled}
                      disabled={!canEdit || loading || !enabled}
                      onChange={(event) =>
                        setRows((prev) =>
                          prev.map((item, i) =>
                            i === index ? { ...item, enabled: event.target.checked } : item
                          )
                        )
                      }
                    />
                  </td>
                  <td>
                    <div className="input-group input-group-sm" style={{ maxWidth: "12rem" }}>
                      <input
                        className="form-control"
                        type="number"
                        value={row.threshold}
                        disabled={!canEdit || loading}
                        onChange={(event) =>
                          setRows((prev) =>
                            prev.map((item, i) =>
                              i === index ? { ...item, threshold: Number(event.target.value) } : item
                            )
                          )
                        }
                      />
                      {PERF_ALARM_UNITS[row.key] ? (
                        <span className="input-group-text">{PERF_ALARM_UNITS[row.key]}</span>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {canEdit ? (
          <Button variant="primary" loading={saving} disabled={loading} onClick={() => void save()}>
            {t("common.save")}
          </Button>
        ) : (
          <p className="text-secondary mb-0">{t("performance.configReadOnly")}</p>
        )}
      </article>
    </SettingsChapter>
  );
}
