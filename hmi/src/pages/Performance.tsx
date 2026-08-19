import { useMemo, useState } from "react";
import { Navigate } from "react-router-dom";
import { MetricTile } from "../components/MetricTile";
import { PerfPanel, PerfStat } from "../components/PerfPanel";
import { PerformanceAlarmModal } from "../components/PerformanceAlarmModal";
import { PerformanceThresholdModal } from "../components/PerformanceThresholdModal";
import { TrendChart } from "../components/TrendChart";
import { useAppSelector } from "../hooks/useAppSelector";
import { usePerformanceAlarms, type PerfAlarmBinding } from "../hooks/usePerformanceAlarms";
import { usePerformanceTrends } from "../hooks/usePerformanceTrends";
import { useTranslation } from "../hooks/useTranslation";
import {
  canViewPerformance,
  type NodePerformanceSnapshot,
  type PerfAlarmKey,
  type PerfAlarmsCatalog,
} from "../services/performance";
import {
  canConfigurePerformanceAlarms,
  formatThresholdLabel,
  toneFromLifecycle,
  type TileTone,
} from "../services/performanceAlarms";
import { patchPerformanceCatalog, refreshPerformanceTrends, valuesOf } from "../services/performanceTrends";

function formatNumber(value: number | null | undefined, digits = 1, unit = ""): string {
  if (value == null || Number.isNaN(Number(value))) return "—";
  const formatted = Number(value).toLocaleString(undefined, {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits > 0 ? Math.min(digits, 1) : 0,
  });
  return unit ? `${formatted} ${unit}` : formatted;
}

function formatUptime(seconds: number | null | undefined): string {
  if (seconds == null || seconds < 0) return "—";
  const total = Math.floor(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  if (h > 47) return `${Math.floor(h / 24)} d ${h % 24} h`;
  return `${h} h ${m} min`;
}

function cpuTone(value: number | null | undefined): TileTone {
  if (value == null) return "unknown";
  if (value >= 90) return "error";
  if (value >= 70) return "warn";
  return "ok";
}

function diskTone(used: number | null | undefined): TileTone {
  if (used == null) return "unknown";
  if (used >= 90) return "error";
  if (used >= 80) return "warn";
  return "ok";
}

function ageTone(ms: number | null | undefined): TileTone {
  if (ms == null) return "unknown";
  if (ms >= 60000) return "error";
  if (ms >= 15000) return "warn";
  return "ok";
}

function thresholdOf(binding: PerfAlarmBinding): string {
  return formatThresholdLabel(binding.catalog?.threshold, binding.catalog?.unit);
}

function numericValue(snapshot: NodePerformanceSnapshot, key: PerfAlarmKey): number | null {
  const map: Record<PerfAlarmKey, number | null | undefined> = {
    cpu: snapshot.HOST_CPU_PERCENT,
    disk: snapshot.HOST_DISK_USED_PERCENT,
    saf_queue: snapshot.SAF_QUEUE_DEPTH,
    saf_lag: snapshot.SAF_REPLICATION_LAG_MS,
    metrics_age: snapshot.METRICS_AGE_MS,
    db_conn: snapshot.DB_ACTIVE_CONNECTIONS,
    http_5xx: snapshot.HTTP_5XX_1M,
  };
  const value = map[key];
  return value == null ? null : Number(value);
}

export function Performance() {
  const { t } = useTranslation();
  const role = useAppSelector((state) => state.auth.user?.role);
  const allowed = canViewPerformance(role);
  const canConfigure = canConfigurePerformanceAlarms(role);
  const { snapshot, series, errorStatus, errorMessage } = usePerformanceTrends();
  const [openKey, setOpenKey] = useState<PerfAlarmKey | null>(null);
  const [configKey, setConfigKey] = useState<PerfAlarmKey | null>(null);
  const [trendsOpen, setTrendsOpen] = useState(true);
  const bindings = usePerformanceAlarms(snapshot.PERF_ALARMS);
  const error =
    errorStatus === 403
      ? t("performance.forbidden")
      : errorStatus || errorMessage
        ? errorMessage || t("performance.loadError")
        : null;

  const tileTone = (key: PerfAlarmKey, fallback: TileTone): TileTone =>
    toneFromLifecycle(bindings[key]?.lifecycle || "normal", fallback);

  const clockTone: TileTone = useMemo(() => {
    if (!snapshot.clock?.enabled) return "unknown";
    if (snapshot.clock.synced === false) return "error";
    if (snapshot.clock.warn) return "warn";
    if (snapshot.clock.synced) return "ok";
    return "unknown";
  }, [snapshot.clock]);

  const mergeCatalog = (next: PerfAlarmsCatalog) => {
    patchPerformanceCatalog(next);
    void refreshPerformanceTrends();
  };

  const valueLabel = (key: PerfAlarmKey | null): string => {
    if (key === "cpu") return formatNumber(snapshot.HOST_CPU_PERCENT, 1, "%");
    if (key === "disk") return formatNumber(snapshot.HOST_DISK_USED_PERCENT, 1, "%");
    if (key === "saf_queue") return formatNumber(snapshot.SAF_QUEUE_DEPTH, 0);
    if (key === "saf_lag") return formatNumber(snapshot.SAF_REPLICATION_LAG_MS, 0, "ms");
    if (key === "metrics_age") return formatNumber(snapshot.METRICS_AGE_MS, 0, "ms");
    if (key === "db_conn") return formatNumber(snapshot.DB_ACTIVE_CONNECTIONS, 0);
    if (key === "http_5xx") return formatNumber(snapshot.HTTP_5XX_1M, 0);
    return "—";
  };

  const openBinding = openKey ? bindings[openKey] : undefined;
  const configBinding = configKey ? bindings[configKey] : undefined;
  const safMax = Math.max(Number(bindings.saf_queue.catalog?.threshold || 5000) * 1.25, Number(snapshot.SAF_QUEUE_DEPTH || 0), 1);

  if (!allowed) {
    return <Navigate to="/events" replace />;
  }

  return (
    <div className="settings-page performance-page">
      <header className="settings-hero perf-hero">
        <p className="settings-hero__eyebrow">{t("performance.kicker")}</p>
        <h2 className="settings-hero__title">{t("performance.title")}</h2>
        <p className="settings-hero__lede">{t("performance.lede")}</p>
        <div className="perf-hero__chips">
          <span className="perf-chip">
            <strong>{t("performance.node")}</strong> {snapshot.NODE_ID || "—"}
          </span>
          <span className="perf-chip">
            <strong>{t("performance.area")}</strong> {snapshot.NODE_AREA || "—"}
          </span>
          <span className="perf-chip">
            <strong>{t("performance.uptime")}</strong> {formatUptime(snapshot.uptime_s)}
          </span>
          <button
            type="button"
            className={`perf-chip perf-chip--${tileTone("metrics_age", ageTone(snapshot.METRICS_AGE_MS))}`}
            onClick={() => setOpenKey("metrics_age")}
          >
            <i className="bi bi-bell" aria-hidden="true" />
            <strong>{t("performance.metricsAge")}</strong> {formatNumber(snapshot.METRICS_AGE_MS, 0, "ms")}
          </button>
          <span className={`perf-chip perf-chip--${clockTone}`}>
            <strong>{t("performance.ntp")}</strong>{" "}
            {snapshot.clock?.synced
              ? t("performance.ntpSynced")
              : snapshot.clock?.enabled
                ? t("performance.ntpUnsynced")
                : t("performance.ntpDisabled")}
            {snapshot.clock?.offset_ms != null ? ` · ${formatNumber(snapshot.clock.offset_ms, 1, "ms")}` : ""}
          </span>
        </div>
      </header>

      {error ? (
        <div className="settings-callout clock-sync-callout clock-sync-callout--error">
          <i className="bi bi-exclamation-triangle" aria-hidden="true" />
          <p className="mb-0">{error}</p>
        </div>
      ) : null}

      <section className="perf-section" aria-label={t("performance.critical")}>
        <h3 className="perf-section__title">{t("performance.critical")}</h3>
        <div className="perf-gauges">
          <MetricTile
            variant="gauge"
            label={t("performance.cpu")}
            value={formatNumber(snapshot.HOST_CPU_PERCENT, 1, "%")}
            raw={snapshot.HOST_CPU_PERCENT}
            max={100}
            tone={tileTone("cpu", cpuTone(snapshot.HOST_CPU_PERCENT))}
            lifecycle={bindings.cpu.lifecycle}
            spark={valuesOf(series.cpu)}
            alarmable
            threshold={bindings.cpu.catalog?.threshold}
            thresholdLabel={thresholdOf(bindings.cpu)}
            canConfigure={canConfigure}
            onOpen={() => setOpenKey("cpu")}
            onConfigure={() => setConfigKey("cpu")}
          />
          <MetricTile
            variant="gauge"
            label={t("performance.rss")}
            value={formatNumber(snapshot.HOST_RSS_MB, 1, "MB")}
            spark={valuesOf(series.rss)}
            hint={t("performance.informative")}
          />
          <MetricTile
            variant="gauge"
            label={t("performance.disk")}
            value={formatNumber(snapshot.HOST_DISK_USED_PERCENT, 1, "%")}
            raw={snapshot.HOST_DISK_USED_PERCENT}
            max={100}
            hint={t("performance.diskFree", { value: formatNumber(snapshot.HOST_DISK_FREE_GB, 1, "GB") })}
            tone={tileTone("disk", diskTone(snapshot.HOST_DISK_USED_PERCENT))}
            lifecycle={bindings.disk.lifecycle}
            spark={valuesOf(series.disk)}
            alarmable
            threshold={bindings.disk.catalog?.threshold}
            thresholdLabel={thresholdOf(bindings.disk)}
            canConfigure={canConfigure}
            onOpen={() => setOpenKey("disk")}
            onConfigure={() => setConfigKey("disk")}
          />
          <MetricTile
            variant="gauge"
            label={t("performance.safQueue")}
            value={formatNumber(snapshot.SAF_QUEUE_DEPTH, 0)}
            raw={snapshot.SAF_QUEUE_DEPTH}
            max={safMax}
            tone={tileTone("saf_queue", (snapshot.SAF_QUEUE_DEPTH || 0) > 0 ? "warn" : "ok")}
            lifecycle={bindings.saf_queue.lifecycle}
            spark={valuesOf(series.saf)}
            alarmable
            threshold={bindings.saf_queue.catalog?.threshold}
            thresholdLabel={thresholdOf(bindings.saf_queue)}
            canConfigure={canConfigure}
            onOpen={() => setOpenKey("saf_queue")}
            onConfigure={() => setConfigKey("saf_queue")}
          />
          <MetricTile
            variant="gauge"
            label={t("performance.ntp")}
            value={
              snapshot.clock?.synced
                ? t("performance.ntpSynced")
                : snapshot.clock?.enabled
                  ? t("performance.ntpUnsynced")
                  : t("performance.ntpDisabled")
            }
            tone={clockTone}
            hint={t("performance.ntpOffset", { value: formatNumber(snapshot.clock?.offset_ms, 1, "ms") })}
          />
        </div>
      </section>

      <section className="perf-section" aria-label={t("performance.subsystems")}>
        <h3 className="perf-section__title">{t("performance.subsystems")}</h3>
        <div className="perf-panels">
          <PerfPanel
            title={t("performance.http")}
            tone={tileTone("http_5xx", (snapshot.HTTP_5XX_1M || 0) > 0 ? "error" : "ok")}
            lifecycle={bindings.http_5xx.lifecycle}
            alarmable
            thresholdLabel={thresholdOf(bindings.http_5xx)}
            canConfigure={canConfigure}
            spark={valuesOf(series.http)}
            onOpen={() => setOpenKey("http_5xx")}
            onConfigure={() => setConfigKey("http_5xx")}
          >
            <PerfStat label={t("performance.http1m")} value={formatNumber(snapshot.HTTP_REQUESTS_1M, 0)} />
            <PerfStat label={t("performance.http5xx")} value={formatNumber(snapshot.HTTP_5XX_1M, 0)} />
            <PerfStat label={t("performance.httpInFlight")} value={formatNumber(snapshot.HTTP_IN_FLIGHT, 0)} />
          </PerfPanel>

          <PerfPanel title={t("performance.hmi")} tone="ok">
            <PerfStat label={t("performance.hmiClients")} value={formatNumber(snapshot.HMI_ACTIVE_CLIENTS, 0)} />
            <PerfStat label={t("performance.threads")} value={formatNumber(snapshot.HOST_THREADS, 0)} />
          </PerfPanel>

          <PerfPanel
            title={t("performance.db")}
            tone={tileTone("db_conn", snapshot.DB_CONNECTED ? "ok" : "error")}
            lifecycle={bindings.db_conn.lifecycle}
            alarmable
            thresholdLabel={thresholdOf(bindings.db_conn)}
            canConfigure={canConfigure}
            onOpen={() => setOpenKey("db_conn")}
            onConfigure={() => setConfigKey("db_conn")}
          >
            <PerfStat
              label={t("performance.dbConnected")}
              value={snapshot.DB_CONNECTED ? t("common.yes") : t("common.no")}
            />
            <PerfStat label={t("performance.dbLatency")} value={formatNumber(snapshot.DB_LATENCY_MS, 1, "ms")} />
            <PerfStat label={t("performance.dbConnections")} value={formatNumber(snapshot.DB_ACTIVE_CONNECTIONS, 0)} />
            <PerfStat
              label={t("performance.dbTxn")}
              value={
                snapshot.DB_TXN_PER_MIN == null
                  ? t("performance.dbTxnUnavailable")
                  : formatNumber(snapshot.DB_TXN_PER_MIN, 0)
              }
            />
          </PerfPanel>

          <PerfPanel
            title={t("performance.saf")}
            tone={tileTone("saf_lag", tileTone("saf_queue", "ok"))}
            lifecycle={
              bindings.saf_lag.lifecycle === "unack" || bindings.saf_queue.lifecycle === "unack"
                ? "unack"
                : bindings.saf_lag.lifecycle === "ack" || bindings.saf_queue.lifecycle === "ack"
                  ? "ack"
                  : bindings.saf_lag.lifecycle === "shelved" || bindings.saf_queue.lifecycle === "shelved"
                    ? "shelved"
                    : "normal"
            }
            alarmable
            thresholdLabel={thresholdOf(bindings.saf_lag)}
            canConfigure={canConfigure}
            onOpen={() => setOpenKey("saf_lag")}
            onConfigure={() => setConfigKey("saf_lag")}
          >
            <PerfStat label={t("performance.safQueue")} value={formatNumber(snapshot.SAF_QUEUE_DEPTH, 0)} />
            <PerfStat label={t("performance.safLag")} value={formatNumber(snapshot.SAF_REPLICATION_LAG_MS, 0, "ms")} />
            <PerfStat
              label={t("performance.safDisk")}
              value={formatNumber((snapshot.SAF_DISK_BYTES || 0) / (1024 * 1024), 1, "MB")}
            />
          </PerfPanel>

          <PerfPanel
            title={t("performance.acquisition")}
            tone={snapshot.ACQUISITION_READY ? "ok" : "error"}
          >
            <PerfStat
              label={t("performance.acquisitionReady")}
              value={snapshot.ACQUISITION_READY ? t("common.yes") : t("common.no")}
            />
            <PerfStat label={t("performance.opc")} value={formatNumber(snapshot.OPC_MONITORED_COUNT, 0)} />
            <PerfStat label={t("performance.cvt")} value={formatNumber(snapshot.CVT_TAG_COUNT, 0)} />
            <PerfStat label={t("performance.sampleLag")} value={formatNumber(snapshot.SAMPLE_LAG_MS, 2, "ms")} />
          </PerfPanel>
        </div>
      </section>

      <section className="perf-section" aria-label={t("performance.trends")}>
        <button
          type="button"
          className="perf-section__toggle"
          onClick={() => setTrendsOpen((open) => !open)}
          aria-expanded={trendsOpen}
        >
          <h3 className="perf-section__title mb-0">{t("performance.trends")}</h3>
          <i className={`bi bi-chevron-${trendsOpen ? "up" : "down"}`} aria-hidden="true" />
        </button>
        {trendsOpen ? (
          <div className="perf-trends">
            <TrendChart
              label={t("performance.cpu")}
              points={series.cpu}
              currentLabel={formatNumber(snapshot.HOST_CPU_PERCENT, 1, "%")}
              unit="%"
              threshold={bindings.cpu.catalog?.threshold}
              redAt={bindings.cpu.catalog?.threshold ?? 85}
            />
            <TrendChart
              label={t("performance.rss")}
              points={series.rss}
              currentLabel={formatNumber(snapshot.HOST_RSS_MB, 1, "MB")}
              unit="MB"
            />
            <TrendChart
              label={t("performance.disk")}
              points={series.disk}
              currentLabel={formatNumber(snapshot.HOST_DISK_USED_PERCENT, 1, "%")}
              unit="%"
              threshold={bindings.disk.catalog?.threshold}
              redAt={bindings.disk.catalog?.threshold ?? 90}
            />
            <TrendChart
              label={t("performance.http1m")}
              points={series.http}
              currentLabel={formatNumber(snapshot.HTTP_REQUESTS_1M, 0)}
            />
          </div>
        ) : null}
      </section>

      <PerformanceAlarmModal
        open={Boolean(openKey)}
        title={openKey ? t(`performance.alarmTitle.${openKey}`) : t("performance.title")}
        valueLabel={valueLabel(openKey)}
        canConfigure={canConfigure}
        alarm={openBinding?.alarm}
        catalog={openBinding?.catalog}
        onClose={() => setOpenKey(null)}
        onConfigure={() => {
          setConfigKey(openKey);
          setOpenKey(null);
        }}
      />
      <PerformanceThresholdModal
        open={Boolean(configKey)}
        alarmKey={configKey}
        title={configKey ? t(`performance.alarmTitle.${configKey}`) : ""}
        currentValue={configKey ? numericValue(snapshot, configKey) : null}
        currentLabel={valueLabel(configKey)}
        catalog={configBinding?.catalog}
        debounceCount={snapshot.PERF_ALARMS?.debounce_count}
        onClose={() => setConfigKey(null)}
        onSaved={mergeCatalog}
      />
    </div>
  );
}
