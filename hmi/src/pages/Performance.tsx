import { useEffect, useMemo, useState } from "react";
import { Navigate } from "react-router-dom";
import { MetricTile } from "../components/MetricTile";
import { OpsConfirmModal } from "../components/OpsConfirmModal";
import { PerfPanel, PerfStat } from "../components/PerfPanel";
import { PerformanceAlarmModal } from "../components/PerformanceAlarmModal";
import { PerformanceThresholdModal } from "../components/PerformanceThresholdModal";
import { TrendChart } from "../components/TrendChart";
import { useAppSelector } from "../hooks/useAppSelector";
import { usePerformanceAlarms, type PerfAlarmBinding } from "../hooks/usePerformanceAlarms";
import { usePerformanceTrends } from "../hooks/usePerformanceTrends";
import { useTranslation } from "../hooks/useTranslation";
import {
  canControlOps,
  canDestroyOps,
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
import { getWaveletFilterStatuses, type TagFilterStatus } from "../services/tags";
import {
  cleanCatalogOrphans,
  rebuildDerivedTags,
  resetSaf,
  restartWorker,
  retrySaf,
  syncCatalog,
} from "../services/opsControls";
import { showToast } from "../utils/toast";

function formatNumber(value: number | null | undefined, digits = 1, unit = ""): string {
  if (value == null || Number.isNaN(Number(value))) return "—";
  const formatted = Number(value).toLocaleString(undefined, {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits > 0 ? Math.min(digits, 1) : 0,
  });
  return unit ? `${formatted} ${unit}` : formatted;
}

function qualityBadgeTone(quality?: string): string {
  if (quality === "GOOD") return "success";
  if (quality === "UNCERTAIN") return "warning";
  if (quality === "BAD") return "danger";
  return "secondary";
}

type TranslateFn = (key: string, params?: Record<string, string | number>) => string;

function formatWaveletEta(row: TagFilterStatus, t: TranslateFn): string {
  const status = (row.status || "").toLowerCase();
  if (status === "ok" || row.warmup_eta_s === 0) {
    return t("performance.waveletEtaReady");
  }
  if (status !== "warmup" || row.warmup_eta_s == null) {
    return "—";
  }
  const eta = Number(row.warmup_eta_s);
  if (!Number.isFinite(eta)) return "—";
  const fill = row.ring_fill ?? 0;
  const window = row.window ?? 0;
  const progress = window > 0 ? `${fill}/${window}` : "";
  const seconds = eta < 10 ? eta.toFixed(1) : String(Math.round(eta));
  if (progress) {
    return t("performance.waveletEtaProgress", { progress, seconds });
  }
  return t("performance.waveletEtaSeconds", { seconds });
}

function waveletStatusLabel(status: string | undefined, t: TranslateFn): string {
  const key = `tags.waveletStatus.${(status || "").toLowerCase()}`;
  const translated = t(key);
  return translated === key ? status || "—" : translated;
}

function formatUptime(seconds: number | null | undefined): string {
  if (seconds == null || seconds < 0) return "—";
  const total = Math.floor(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  if (h > 47) return `${Math.floor(h / 24)} d ${h % 24} h`;
  return `${h} h ${m} min`;
}

function formatCycle(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function workerLabel(state: string | undefined, t: TranslateFn): string {
  if (state === "alive") return t("performance.opsWorkerAlive");
  if (state === "inactive") return t("performance.opsWorkerInactive");
  if (state === "restarting") return t("performance.opsWorkerRestarting");
  if (state === "error") return t("performance.opsWorkerError");
  return state || "—";
}

const WORKER_KEYS = ["LoggerWorker", "CatalogReplicator", "MetricsSampler"] as const;

function worstWorkerTone(
  workers: NodePerformanceSnapshot["WORKERS"]
): TileTone {
  const states = WORKER_KEYS.map((name) => workers?.[name]?.state);
  if (states.some((state) => state === "error" || state === "inactive")) return "error";
  if (states.some((state) => state === "restarting")) return "warn";
  if (states.every((state) => state === "alive")) return "ok";
  return "unknown";
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
  const canControl = canControlOps(role);
  const canDestroy = canDestroyOps(role);
  const { snapshot, series, errorStatus, errorMessage } = usePerformanceTrends();
  const [openKey, setOpenKey] = useState<PerfAlarmKey | null>(null);
  const [configKey, setConfigKey] = useState<PerfAlarmKey | null>(null);
  const [trendsOpen, setTrendsOpen] = useState(true);
  const [waveletRows, setWaveletRows] = useState<TagFilterStatus[]>([]);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [cooldownUntil, setCooldownUntil] = useState<Record<string, number>>({});
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [restartName, setRestartName] = useState<string | null>(null);
  const [resetOpen, setResetOpen] = useState(false);
  const [orphanOpen, setOrphanOpen] = useState(false);
  const [orphanAge, setOrphanAge] = useState(10);
  const [rebuildOpen, setRebuildOpen] = useState(false);
  const bindings = usePerformanceAlarms(snapshot.PERF_ALARMS);
  const queue = Number(snapshot.SAF_QUEUE_DEPTH || 0);
  const orphanRows = Number(snapshot.CATALOG_ORPHAN_ROWS ?? snapshot.CATALOG_PENDING_ROWS ?? 0);
  const workers = snapshot.WORKERS || {};
  const cooldownLeft = (key: string) => Math.max(0, Math.ceil(((cooldownUntil[key] || 0) - nowMs) / 1000));
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

  const runOps = async (
    key: string,
    action: () => Promise<unknown>,
    success: string | ((result: unknown) => string)
  ): Promise<boolean> => {
    if (busyKey) return false;
    setBusyKey(key);
    try {
      const result = await action();
      showToast(typeof success === "function" ? success(result) : success, "success");
      window.setTimeout(() => {
        void refreshPerformanceTrends();
      }, 800);
      return true;
    } catch (error: any) {
      showToast(error?.response?.data?.message || t("performance.opsActionError"), "error");
      return false;
    } finally {
      setBusyKey(null);
    }
  };

  const armCooldown = (key: string) => {
    setCooldownUntil((prev) => ({ ...prev, [key]: Date.now() + 30000 }));
  };

  const openBinding = openKey ? bindings[openKey] : undefined;
  const configBinding = configKey ? bindings[configKey] : undefined;
  const safMax = Math.max(Number(bindings.saf_queue.catalog?.threshold || 5000) * 1.25, Number(snapshot.SAF_QUEUE_DEPTH || 0), 1);

  useEffect(() => {
    if (!Object.values(cooldownUntil).some((until) => until > Date.now())) return undefined;
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [cooldownUntil]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      const rows = await getWaveletFilterStatuses();
      if (!cancelled) setWaveletRows(rows);
    };
    load();
    const timer = window.setInterval(load, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

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
            actions={
              canControl && (queue > 1000 || (canDestroy && queue > 5000)) ? (
                <>
                  {queue > 1000 ? (
                    <button
                      type="button"
                      className="btn btn-sm btn-outline-primary"
                      disabled={busyKey != null || cooldownLeft("saf-retry") > 0}
                      onClick={() =>
                        void runOps(
                          "saf-retry",
                          async () => {
                            await retrySaf();
                            armCooldown("saf-retry");
                          },
                          t("performance.opsRetryOk")
                        )
                      }
                    >
                      {busyKey === "saf-retry"
                        ? t("performance.opsExecuting")
                        : cooldownLeft("saf-retry") > 0
                          ? t("performance.opsCooldown", { seconds: cooldownLeft("saf-retry") })
                          : t("performance.opsForceReplicate")}
                    </button>
                  ) : null}
                  {canDestroy && queue > 5000 ? (
                    <button
                      type="button"
                      className="btn btn-sm btn-danger"
                      disabled={busyKey != null}
                      onClick={() => setResetOpen(true)}
                    >
                      {t("performance.opsEmptyQueue")}
                    </button>
                  ) : null}
                </>
              ) : null
            }
          >
            <PerfStat label={t("performance.safQueue")} value={formatNumber(snapshot.SAF_QUEUE_DEPTH, 0)} />
            <PerfStat label={t("performance.safLag")} value={formatNumber(snapshot.SAF_REPLICATION_LAG_MS, 0, "ms")} />
            <PerfStat
              label={t("performance.safDisk")}
              value={formatNumber((snapshot.SAF_DISK_BYTES || 0) / (1024 * 1024), 1, "MB")}
            />
            <div className="perf-ops-bar" aria-hidden="true">
              <span style={{ width: `${Math.min(100, (queue / safMax) * 100)}%` }} />
            </div>
          </PerfPanel>

          <PerfPanel title={t("performance.opsWorkers")} tone={worstWorkerTone(workers)}>
            {WORKER_KEYS.map((name) => {
              const row = workers[name] || {};
              const state = row.state;
              const restarting = state === "restarting" || busyKey === `restart-${name}`;
              return (
                <div key={name} className="perf-ops-worker">
                  <div className="perf-ops-worker__meta">
                    <PerfStat label={name} value={restarting ? t("performance.opsRestarting") : workerLabel(state, t)} />
                    <PerfStat label={t("performance.opsLastCycle")} value={formatCycle(row.last_cycle_utc)} />
                  </div>
                  {canControl ? (
                    <button
                      type="button"
                      className="btn btn-sm btn-outline-primary"
                      disabled={busyKey != null || restarting}
                      onClick={() => setRestartName(name)}
                    >
                      {t("performance.opsRestart")}
                    </button>
                  ) : null}
                </div>
              );
            })}
          </PerfPanel>

          <PerfPanel
            title={t("performance.opsCatalog")}
            tone={orphanRows > 0 ? "warn" : "ok"}
            actions={
              canControl ? (
                <>
                  <button
                    type="button"
                    className="btn btn-sm btn-outline-primary"
                    disabled={busyKey != null || cooldownLeft("catalog-sync") > 0}
                    onClick={() =>
                      void runOps(
                        "catalog-sync",
                        async () => {
                          await syncCatalog();
                          armCooldown("catalog-sync");
                        },
                        t("performance.opsSyncOk")
                      )
                    }
                  >
                    {busyKey === "catalog-sync"
                      ? t("performance.opsExecuting")
                      : cooldownLeft("catalog-sync") > 0
                        ? t("performance.opsCooldown", { seconds: cooldownLeft("catalog-sync") })
                        : t("performance.opsForceSync")}
                  </button>
                  {canDestroy && orphanRows > 0 ? (
                    <button
                      type="button"
                      className="btn btn-sm btn-outline-danger"
                      disabled={busyKey != null}
                      onClick={() => setOrphanOpen(true)}
                    >
                      {t("performance.opsCleanOrphans")}
                    </button>
                  ) : null}
                </>
              ) : null
            }
          >
            <PerfStat label={t("performance.opsOrphanRows")} value={formatNumber(orphanRows, 0)} />
            <PerfStat label={t("performance.opsLastCycle")} value={formatCycle(snapshot.CATALOG_LAST_SYNC)} />
          </PerfPanel>

          <PerfPanel
            title={t("performance.opsDerived")}
            tone="ok"
            actions={
              canControl ? (
                <button
                  type="button"
                  className="btn btn-sm btn-outline-primary"
                  disabled={busyKey != null}
                  onClick={() => setRebuildOpen(true)}
                >
                  {t("performance.opsRebuildDerived")}
                </button>
              ) : null
            }
          >
            <PerfStat
              label={t("performance.opsDerivedCount")}
              value={formatNumber(snapshot.DERIVED_TAGS_COUNT, 0)}
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

      <section className="perf-section" aria-label={t("performance.waveletFilters")}>
        <h3 className="perf-section__title">{t("performance.waveletFilters")}</h3>
        {waveletRows.length === 0 ? (
          <p className="text-muted mb-0">{t("performance.waveletEmpty")}</p>
        ) : (
          <div className="table-responsive">
            <table className="table table-sm align-middle mb-0">
              <thead>
                <tr>
                  <th>{t("performance.waveletSource")}</th>
                  <th>{t("performance.waveletFiltered")}</th>
                  <th>{t("performance.waveletStatus")}</th>
                  <th>{t("performance.waveletEta")}</th>
                  <th>{t("performance.waveletQuality")}</th>
                  <th>{t("performance.waveletAge")}</th>
                  <th>{t("performance.waveletRate")}</th>
                </tr>
              </thead>
              <tbody>
                {waveletRows.map((row) => {
                  const age = row.age_ms ?? null;
                  const status = (row.status || "").toLowerCase();
                  const tone =
                    status === "ok"
                      ? "success"
                      : status === "warmup"
                        ? "info"
                        : status === "hold"
                          ? "warning"
                          : status === "failed"
                            ? "danger"
                            : age == null
                              ? "secondary"
                              : age > 5000
                                ? "danger"
                                : age > 1000
                                  ? "warning"
                                  : "success";
                  return (
                    <tr key={row.source || row.filtered_tag}>
                      <td><code>{row.source}</code></td>
                      <td><code>{row.filtered_tag}</code></td>
                      <td>
                        <span className={`badge text-bg-${tone}`}>{waveletStatusLabel(row.status, t)}</span>
                      </td>
                      <td>
                        <span
                          className={status === "warmup" ? "text-info fw-semibold" : "text-muted"}
                          title={
                            status === "warmup" && row.window
                              ? t("performance.waveletEtaHint", {
                                  remaining: row.warmup_remaining ?? 0,
                                  window: row.window,
                                })
                              : undefined
                          }
                        >
                          {formatWaveletEta(row, t)}
                        </span>
                      </td>
                      <td>
                        <span className={`badge text-bg-${qualityBadgeTone(row.last_publication_quality)}`}>
                          {row.last_publication_quality || "—"}
                        </span>
                      </td>
                      <td>{age == null ? "—" : `${(age / 1000).toFixed(2)} s`}</td>
                      <td>{row.raw_rate == null ? "—" : `${row.raw_rate} Hz`}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
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
      <OpsConfirmModal
        open={Boolean(restartName)}
        title={t("performance.opsRestartTitle", { name: restartName || "" })}
        body={t("performance.opsRestartBody", { name: restartName || "" })}
        busy={Boolean(restartName) && busyKey === `restart-${restartName}`}
        onCancel={() => setRestartName(null)}
        onConfirm={async () => {
          const name = restartName;
          if (!name) return;
          const ok = await runOps(
            `restart-${name}`,
            () => restartWorker(name),
            t("performance.opsRestartOk", { name })
          );
          if (ok) setRestartName(null);
        }}
      />
      <OpsConfirmModal
        open={resetOpen}
        title={t("performance.opsResetTitle")}
        body={t("performance.opsResetBody")}
        danger
        requireCheckbox
        checkboxLabel={t("performance.opsResetCheck")}
        requireTypedConfirm
        typedToken="CONFIRMAR"
        busy={busyKey === "saf-reset"}
        onCancel={() => setResetOpen(false)}
        onConfirm={async () => {
          const ok = await runOps(
            "saf-reset",
            () => resetSaf(),
            (result) =>
              t("performance.opsResetOk", {
                count: Number((result as { dropped?: number } | null)?.dropped || 0),
              })
          );
          if (ok) setResetOpen(false);
        }}
      />
      <OpsConfirmModal
        open={orphanOpen}
        title={t("performance.opsOrphanTitle")}
        body={t("performance.opsOrphanBody")}
        requireCheckbox
        checkboxLabel={t("performance.opsOrphanCheck")}
        extra={
          <label className="perf-ops-typed">
            <span>{t("performance.opsOrphanAge")}</span>
            <select
              className="form-select"
              value={orphanAge}
              onChange={(event) => setOrphanAge(Number(event.target.value))}
            >
              {[5, 10, 30, 60].map((minutes) => (
                <option key={minutes} value={minutes}>
                  {minutes} min
                </option>
              ))}
            </select>
          </label>
        }
        busy={busyKey === "catalog-orphans"}
        onCancel={() => setOrphanOpen(false)}
        onConfirm={async () => {
          const ok = await runOps(
            "catalog-orphans",
            () => cleanCatalogOrphans(orphanAge),
            (result) =>
              t("performance.opsOrphansOk", {
                count: Number((result as { dropped?: number } | null)?.dropped || 0),
              })
          );
          if (ok) setOrphanOpen(false);
        }}
      />
      <OpsConfirmModal
        open={rebuildOpen}
        title={t("performance.opsRebuildTitle")}
        body={t("performance.opsRebuildBody")}
        busy={busyKey === "rebuild-derived"}
        onCancel={() => setRebuildOpen(false)}
        onConfirm={async () => {
          const ok = await runOps(
            "rebuild-derived",
            () => rebuildDerivedTags(),
            (result) => {
              const payload = result as { ensured?: number; removed?: number } | null;
              return t("performance.opsRebuildOk", {
                ensured: Number(payload?.ensured || 0),
                removed: Number(payload?.removed || 0),
              });
            }
          );
          if (ok) setRebuildOpen(false);
        }}
      />
    </div>
  );
}
