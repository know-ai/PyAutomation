import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Navigate } from "react-router-dom";
import { ResponsiveGridLayout, getCompactor, type Layout, type LayoutItem } from "react-grid-layout";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";
import { MetricTile } from "../components/MetricTile";
import { OpsConfirmModal } from "../components/OpsConfirmModal";
import { OpsHintButton, PerfPanel, PerfStat } from "../components/PerfPanel";
import { PerformanceAlarmModal } from "../components/PerformanceAlarmModal";
import { PerformanceThresholdModal } from "../components/PerformanceThresholdModal";
import { TrendChart } from "../components/TrendChart";
import { useAuthz } from "../hooks/useAuthz";
import { VIEW_IDS } from "../utils/access";
import { usePerformanceAlarms, type PerfAlarmBinding } from "../hooks/usePerformanceAlarms";
import { usePerformanceTrends } from "../hooks/usePerformanceTrends";
import { useTranslation } from "../hooks/useTranslation";
import {
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

function diskTone(
  used: number | null | undefined,
  critical?: boolean | null,
): TileTone {
  if (critical) return "error";
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
    field_stale: snapshot.FIELD_STALE,
    saf_deadletter: snapshot.SAF_DEADLETTER_COUNT,
    hub_lag: snapshot.HUB_LAG_MS,
    saf_shed: snapshot.SAF_SHED,
    saf_ingest: snapshot.SAF_INGEST_AGE_MS,
    saf_rate: snapshot.SAF_RATE_MISMATCH,
    ssd: snapshot.HOST_SSD_ALARM,
    ntp: snapshot.HOST_NTP_ABS_OFFSET_MS,
    node_down: snapshot.HOST_PEER_DOWN,
  };
  const value = map[key];
  return value == null ? null : Number(value);
}

type PerfLayoutItem = {
  i: string;
  x: number;
  y: number;
  w: number;
  h: number;
  minW?: number;
  minH?: number;
};

type PerfLayouts = {
  lg: PerfLayoutItem[];
  md: PerfLayoutItem[];
  sm: PerfLayoutItem[];
};

const LAYOUT_KEY = "performance_dashboard_layout_v1";
const GRID_COMPACTOR = getCompactor(null, false, false);

const DEFAULT_LAYOUT_LG: PerfLayoutItem[] = [
  { i: "gauge-cpu", x: 0, y: 0, w: 2, h: 4, minW: 2, minH: 3 },
  { i: "gauge-rss", x: 2, y: 0, w: 2, h: 4, minW: 2, minH: 3 },
  { i: "gauge-disk", x: 4, y: 0, w: 2, h: 4, minW: 2, minH: 3 },
  { i: "gauge-ssd", x: 6, y: 0, w: 2, h: 4, minW: 2, minH: 3 },
  { i: "gauge-saf", x: 8, y: 0, w: 2, h: 4, minW: 2, minH: 3 },
  { i: "gauge-ntp", x: 10, y: 0, w: 2, h: 4, minW: 2, minH: 3 },
  { i: "panel-http", x: 0, y: 4, w: 3, h: 5, minW: 3, minH: 3 },
  { i: "panel-hmi", x: 3, y: 4, w: 3, h: 5, minW: 3, minH: 3 },
  { i: "panel-db", x: 6, y: 4, w: 3, h: 5, minW: 3, minH: 3 },
  { i: "panel-saf", x: 9, y: 4, w: 3, h: 5, minW: 3, minH: 3 },
  { i: "panel-workers", x: 0, y: 9, w: 6, h: 8, minW: 4, minH: 5 },
  { i: "panel-catalog", x: 6, y: 9, w: 3, h: 4, minW: 3, minH: 3 },
  { i: "panel-derived", x: 9, y: 9, w: 3, h: 4, minW: 3, minH: 3 },
  { i: "panel-acquisition", x: 6, y: 13, w: 6, h: 4, minW: 3, minH: 3 },
  { i: "wavelet", x: 0, y: 17, w: 12, h: 6, minW: 6, minH: 3 },
  { i: "trend-cpu", x: 0, y: 23, w: 3, h: 4, minW: 3, minH: 3 },
  { i: "trend-rss", x: 3, y: 23, w: 3, h: 4, minW: 3, minH: 3 },
  { i: "trend-disk", x: 6, y: 23, w: 3, h: 4, minW: 3, minH: 3 },
  { i: "trend-http", x: 9, y: 23, w: 3, h: 4, minW: 3, minH: 3 },
];

const DEFAULT_LAYOUT_MD: PerfLayoutItem[] = [
  { i: "gauge-cpu", x: 0, y: 0, w: 4, h: 4, minW: 3, minH: 3 },
  { i: "gauge-rss", x: 4, y: 0, w: 4, h: 4, minW: 3, minH: 3 },
  { i: "gauge-disk", x: 8, y: 0, w: 4, h: 4, minW: 3, minH: 3 },
  { i: "gauge-ssd", x: 0, y: 4, w: 4, h: 4, minW: 3, minH: 3 },
  { i: "gauge-saf", x: 4, y: 4, w: 4, h: 4, minW: 3, minH: 3 },
  { i: "gauge-ntp", x: 8, y: 4, w: 4, h: 4, minW: 3, minH: 3 },
  { i: "panel-http", x: 0, y: 8, w: 6, h: 5, minW: 4, minH: 3 },
  { i: "panel-hmi", x: 6, y: 8, w: 6, h: 5, minW: 4, minH: 3 },
  { i: "panel-db", x: 0, y: 13, w: 6, h: 5, minW: 4, minH: 3 },
  { i: "panel-saf", x: 6, y: 13, w: 6, h: 5, minW: 4, minH: 3 },
  { i: "panel-workers", x: 0, y: 18, w: 12, h: 6, minW: 6, minH: 4 },
  { i: "panel-catalog", x: 0, y: 24, w: 6, h: 4, minW: 4, minH: 3 },
  { i: "panel-derived", x: 6, y: 24, w: 6, h: 4, minW: 4, minH: 3 },
  { i: "panel-acquisition", x: 0, y: 28, w: 12, h: 5, minW: 6, minH: 3 },
  { i: "wavelet", x: 0, y: 33, w: 12, h: 6, minW: 6, minH: 3 },
  { i: "trend-cpu", x: 0, y: 39, w: 6, h: 4, minW: 4, minH: 3 },
  { i: "trend-rss", x: 6, y: 39, w: 6, h: 4, minW: 4, minH: 3 },
  { i: "trend-disk", x: 0, y: 43, w: 6, h: 4, minW: 4, minH: 3 },
  { i: "trend-http", x: 6, y: 43, w: 6, h: 4, minW: 4, minH: 3 },
];

const DEFAULT_LAYOUT_SM: PerfLayoutItem[] = [
  { i: "gauge-cpu", x: 0, y: 0, w: 12, h: 4, minW: 12, minH: 3 },
  { i: "gauge-rss", x: 0, y: 4, w: 12, h: 4, minW: 12, minH: 3 },
  { i: "gauge-disk", x: 0, y: 8, w: 12, h: 4, minW: 12, minH: 3 },
  { i: "gauge-ssd", x: 0, y: 12, w: 12, h: 4, minW: 12, minH: 3 },
  { i: "gauge-saf", x: 0, y: 16, w: 12, h: 4, minW: 12, minH: 3 },
  { i: "gauge-ntp", x: 0, y: 20, w: 12, h: 4, minW: 12, minH: 3 },
  { i: "panel-http", x: 0, y: 24, w: 12, h: 5, minW: 12, minH: 3 },
  { i: "panel-hmi", x: 0, y: 29, w: 12, h: 4, minW: 12, minH: 3 },
  { i: "panel-db", x: 0, y: 33, w: 12, h: 5, minW: 12, minH: 3 },
  { i: "panel-saf", x: 0, y: 38, w: 12, h: 5, minW: 12, minH: 3 },
  { i: "panel-workers", x: 0, y: 43, w: 12, h: 7, minW: 12, minH: 4 },
  { i: "panel-catalog", x: 0, y: 50, w: 12, h: 4, minW: 12, minH: 3 },
  { i: "panel-derived", x: 0, y: 54, w: 12, h: 4, minW: 12, minH: 3 },
  { i: "panel-acquisition", x: 0, y: 58, w: 12, h: 5, minW: 12, minH: 3 },
  { i: "wavelet", x: 0, y: 63, w: 12, h: 6, minW: 12, minH: 3 },
  { i: "trend-cpu", x: 0, y: 69, w: 12, h: 4, minW: 12, minH: 3 },
  { i: "trend-rss", x: 0, y: 73, w: 12, h: 4, minW: 12, minH: 3 },
  { i: "trend-disk", x: 0, y: 77, w: 12, h: 4, minW: 12, minH: 3 },
  { i: "trend-http", x: 0, y: 81, w: 12, h: 4, minW: 12, minH: 3 },
];

const DEFAULT_LAYOUTS: PerfLayouts = {
  lg: DEFAULT_LAYOUT_LG,
  md: DEFAULT_LAYOUT_MD,
  sm: DEFAULT_LAYOUT_SM,
};

function asLayoutItems(value: unknown): PerfLayoutItem[] | null {
  if (!Array.isArray(value) || value.length === 0) return null;
  return value.filter((row): row is PerfLayoutItem => Boolean(row && typeof row === "object" && "i" in row));
}

function loadLayouts(fallback: PerfLayouts): PerfLayouts {
  try {
    const raw = localStorage.getItem(LAYOUT_KEY);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as Partial<PerfLayouts>;
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return fallback;
    return {
      lg: asLayoutItems(parsed.lg) || fallback.lg,
      md: asLayoutItems(parsed.md) || fallback.md,
      sm: asLayoutItems(parsed.sm) || fallback.sm,
    };
  } catch {
    return fallback;
  }
}

function persistLayouts(next: PerfLayouts) {
  try {
    localStorage.setItem(LAYOUT_KEY, JSON.stringify(next));
  } catch {
    /* quota */
  }
}

function normalizeItem(item: LayoutItem | PerfLayoutItem): PerfLayoutItem {
  return {
    i: String(item.i),
    x: Number(item.x) || 0,
    y: Number(item.y) || 0,
    w: Number(item.w) || 1,
    h: Number(item.h) || 1,
    minW: item.minW,
    minH: item.minH,
  };
}

function activeLayoutsOf(layouts: PerfLayouts, isMobile: boolean): Record<string, PerfLayoutItem[]> {
  const stacked = layouts.sm;
  if (isMobile) {
    return { lg: stacked, md: stacked, sm: stacked, xs: stacked, xxs: stacked };
  }
  return { ...layouts, sm: layouts.sm, xs: layouts.sm, xxs: layouts.sm };
}

export function Performance() {
  const { t } = useTranslation();
  const { canView, canUse, canRest, views } = useAuthz();
  const allowed = canView(VIEW_IDS.performance);
  const canConfigure = canConfigurePerformanceAlarms(views);
  const canControl = canRest("/api/admin/workers") || canUse(VIEW_IDS.performance);
  const canDestroy = canRest("/api/admin/saf/reset") || canRest("clean-orphans");
  const { snapshot, series, errorStatus, errorMessage } = usePerformanceTrends();
  const [openKey, setOpenKey] = useState<PerfAlarmKey | null>(null);
  const [configKey, setConfigKey] = useState<PerfAlarmKey | null>(null);
  const [waveletRows, setWaveletRows] = useState<TagFilterStatus[]>([]);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [cooldownUntil, setCooldownUntil] = useState<Record<string, number>>({});
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [restartName, setRestartName] = useState<string | null>(null);
  const [resetOpen, setResetOpen] = useState(false);
  const [orphanOpen, setOrphanOpen] = useState(false);
  const [orphanAge, setOrphanAge] = useState(10);
  const [rebuildOpen, setRebuildOpen] = useState(false);
  const [layouts, setLayouts] = useState<PerfLayouts>(() => loadLayouts(DEFAULT_LAYOUTS));
  const [gridWidth, setGridWidth] = useState(0);
  const [gridEpoch, setGridEpoch] = useState(0);
  const gridRef = useRef<HTMLDivElement | null>(null);
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
    if (key === "ssd") return formatNumber(snapshot.HOST_SSD_WEAR_PERCENT, 1, "%");
    if (key === "ntp") return formatNumber(snapshot.HOST_NTP_ABS_OFFSET_MS, 1, "ms");
    if (key === "node_down") return formatNumber(snapshot.HOST_PEER_DOWN_COUNT, 0);
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

  useEffect(() => {
    const el = gridRef.current;
    if (!el) return undefined;
    const measure = () => {
      const next = el.clientWidth;
      if (next > 0) setGridWidth(next);
    };
    measure();
    const tid = window.setTimeout(() => {
      measure();
      setGridEpoch((value) => value + 1);
    }, 0);
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => {
      window.clearTimeout(tid);
      observer.disconnect();
    };
  }, []);

  const isMobile = gridWidth > 0 && gridWidth < 768;
  const activeLayouts = useMemo(() => activeLayoutsOf(layouts, isMobile), [isMobile, layouts]);

  const resetLayout = useCallback(() => {
    try {
      localStorage.removeItem(LAYOUT_KEY);
    } catch {
      /* ignore */
    }
    setLayouts(DEFAULT_LAYOUTS);
    persistLayouts(DEFAULT_LAYOUTS);
    setGridEpoch((value) => value + 1);
  }, []);

  const onLayoutChange = useCallback((_current: Layout, all: Partial<Record<string, Layout>>) => {
    const next: PerfLayouts = {
      lg: (asLayoutItems(all.lg) || DEFAULT_LAYOUTS.lg).map(normalizeItem),
      md: (asLayoutItems(all.md) || DEFAULT_LAYOUTS.md).map(normalizeItem),
      sm: (asLayoutItems(all.sm) || DEFAULT_LAYOUTS.sm).map(normalizeItem),
    };
    setLayouts(next);
    persistLayouts(next);
  }, []);

  if (!allowed) {
    return <Navigate to="/events" replace />;
  }

  return (
    <div className="performance-page">
      <header className="perf-hero">
        <div className="perf-hero__lead">
          <p className="settings-hero__eyebrow">{t("performance.kicker")}</p>
          <h2 className="settings-hero__title">{t("performance.title")}</h2>
        </div>
        <button
          type="button"
          className="btn btn-sm btn-outline-secondary perf-hero__reset"
          onClick={resetLayout}
          title={t("performance.resetLayoutHint")}
        >
          <i className="bi bi-arrow-counterclockwise me-1" aria-hidden="true" />
          {t("performance.resetLayout")}
        </button>
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
          <button
            type="button"
            className={`perf-chip perf-chip--${tileTone("ntp", clockTone)}`}
            onClick={() => setOpenKey("ntp")}
          >
            <i className="bi bi-bell" aria-hidden="true" />
            <strong>{t("performance.ntp")}</strong>{" "}
            {snapshot.clock?.synced
              ? t("performance.ntpSynced")
              : snapshot.clock?.enabled
                ? t("performance.ntpUnsynced")
                : t("performance.ntpDisabled")}
            {snapshot.clock?.offset_ms != null ? ` · ${formatNumber(snapshot.clock.offset_ms, 1, "ms")}` : ""}
          </button>
          <button
            type="button"
            className={`perf-chip perf-chip--${tileTone("node_down", snapshot.HOST_PEER_DOWN ? "error" : "ok")}`}
            onClick={() => setOpenKey("node_down")}
          >
            <i className="bi bi-bell" aria-hidden="true" />
            <strong>{t("performance.peerDown")}</strong>{" "}
            {snapshot.HOST_PEER_DOWN
              ? t("performance.peerDownHint", {
                  count: Number(snapshot.HOST_PEER_DOWN_COUNT || 0),
                  ids: (snapshot.HOST_PEER_DOWN_IDS || []).join(", ") || "—",
                })
              : t("performance.peerOk")}
          </button>
        </div>
      </header>

      {error ? (
        <div className="settings-callout clock-sync-callout clock-sync-callout--error">
          <i className="bi bi-exclamation-triangle" aria-hidden="true" />
          <p className="mb-0">{error}</p>
        </div>
      ) : null}

      <div ref={gridRef} className="perf-dashboard-grid">
        {gridWidth > 0 ? (
          <ResponsiveGridLayout
            key={gridEpoch}
            className="layout"
            width={gridWidth}
            layouts={activeLayouts}
            breakpoints={{ lg: 1200, md: 996, sm: 768, xs: 480, xxs: 0 }}
            cols={{ lg: 12, md: 12, sm: 12, xs: 12, xxs: 12 }}
            rowHeight={60}
            margin={[8, 8]}
            containerPadding={[0, 4]}
            dragConfig={{
              enabled: true,
              bounded: true,
              handle: ".lds-card-handle",
              cancel: ".perf-tile__tools,button,a,input,select,textarea,.perf-info",
              threshold: 3,
            }}
            resizeConfig={{ enabled: true, handles: ["se"] }}
            compactor={GRID_COMPACTOR}
            onLayoutChange={onLayoutChange}
          >
            <div key="gauge-cpu" className="perf-grid-card">
              <MetricTile
                variant="gauge"
                dragHandle
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
            </div>
            <div key="gauge-rss" className="perf-grid-card">
              <MetricTile
                variant="gauge"
                dragHandle
                label={t("performance.rss")}
                value={formatNumber(snapshot.HOST_RSS_MB, 1, "MB")}
                spark={valuesOf(series.rss)}
                info={t("performance.info.rss")}
              />
            </div>
            <div key="gauge-disk" className="perf-grid-card">
              <MetricTile
                variant="gauge"
                dragHandle
                label={t("performance.disk")}
                value={formatNumber(snapshot.HOST_DISK_USED_PERCENT, 1, "%")}
                raw={snapshot.HOST_DISK_USED_PERCENT}
                max={100}
                hint={
                  snapshot.HOST_DISK_NOATIME === false
                    ? t("performance.noatimeMissing")
                    : t("performance.diskFree", { value: formatNumber(snapshot.HOST_DISK_FREE_GB, 1, "GB") })
                }
                tone={tileTone("disk", diskTone(snapshot.HOST_DISK_USED_PERCENT, snapshot.HOST_DISK_CRITICAL))}
                lifecycle={bindings.disk.lifecycle}
                spark={valuesOf(series.disk)}
                alarmable
                threshold={bindings.disk.catalog?.threshold}
                thresholdLabel={thresholdOf(bindings.disk)}
                canConfigure={canConfigure}
                onOpen={() => setOpenKey("disk")}
                onConfigure={() => setConfigKey("disk")}
              />
            </div>
            <div key="gauge-ssd" className="perf-grid-card">
              <MetricTile
                variant="gauge"
                dragHandle
                label={t("performance.ssd")}
                value={
                  snapshot.HOST_SSD_SMART_AVAILABLE
                    ? formatNumber(snapshot.HOST_SSD_WEAR_PERCENT, 1, "%")
                    : t("performance.ssdUnavailable")
                }
                raw={snapshot.HOST_SSD_WEAR_PERCENT}
                max={100}
                hint={
                  snapshot.HOST_SSD_SMART_AVAILABLE
                    ? t("performance.ssdHint", {
                        wear: formatNumber(snapshot.HOST_SSD_WEAR_PERCENT, 1, "%"),
                        temp: formatNumber(snapshot.HOST_SSD_TEMP_C, 1, "°C"),
                      })
                    : t("performance.ssdUnavailable")
                }
                tone={tileTone(
                  "ssd",
                  snapshot.HOST_SSD_ALARM
                    ? "error"
                    : snapshot.HOST_SSD_SMART_AVAILABLE
                      ? "ok"
                      : "unknown"
                )}
                lifecycle={bindings.ssd.lifecycle}
                alarmable
                threshold={bindings.ssd.catalog?.threshold}
                thresholdLabel={thresholdOf(bindings.ssd)}
                canConfigure={canConfigure}
                onOpen={() => setOpenKey("ssd")}
                onConfigure={() => setConfigKey("ssd")}
              />
            </div>
            <div key="gauge-saf" className="perf-grid-card">
              <MetricTile
                variant="gauge"
                dragHandle
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
            </div>
            <div key="gauge-ntp" className="perf-grid-card">
              <MetricTile
                variant="gauge"
                dragHandle
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
                info={t("performance.info.ntp")}
              />
            </div>
            <div key="panel-http" className="perf-grid-card">
              <PerfPanel
                title={t("performance.http")}
                dragHandle
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
            </div>
            <div key="panel-hmi" className="perf-grid-card">
              <PerfPanel title={t("performance.hmi")} tone="ok" dragHandle info={t("performance.info.hmi")}>
                <PerfStat label={t("performance.hmiClients")} value={formatNumber(snapshot.HMI_ACTIVE_CLIENTS, 0)} />
                <PerfStat label={t("performance.threads")} value={formatNumber(snapshot.HOST_THREADS, 0)} />
              </PerfPanel>
            </div>
            <div key="panel-db" className="perf-grid-card">
              <PerfPanel
                title={t("performance.db")}
                dragHandle
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
            </div>
            <div key="panel-saf" className="perf-grid-card">
              <PerfPanel
                title={t("performance.saf")}
                dragHandle
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
                        <OpsHintButton
                          className="btn btn-sm btn-outline-primary"
                          hint={t("performance.opsHint.forceReplicate")}
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
                        </OpsHintButton>
                      ) : null}
                      {canDestroy && queue > 5000 ? (
                        <OpsHintButton
                          className="btn btn-sm btn-danger"
                          hint={t("performance.opsHint.emptyQueue")}
                          disabled={busyKey != null}
                          onClick={() => setResetOpen(true)}
                        >
                          {t("performance.opsEmptyQueue")}
                        </OpsHintButton>
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
            </div>
            <div key="panel-workers" className="perf-grid-card">
              <PerfPanel
                title={t("performance.opsWorkers")}
                tone={worstWorkerTone(workers)}
                dragHandle
                info={t("performance.info.workers")}
                bodyClassName="perf-panel__body--stack"
              >
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
                        <OpsHintButton
                          className="btn btn-sm btn-outline-primary"
                          hint={t(`performance.opsHint.restart${name}`)}
                          disabled={busyKey != null || restarting}
                          onClick={() => setRestartName(name)}
                        >
                          {t("performance.opsRestart")}
                        </OpsHintButton>
                      ) : null}
                    </div>
                  );
                })}
              </PerfPanel>
            </div>
            <div key="panel-catalog" className="perf-grid-card">
              <PerfPanel
                title={t("performance.opsCatalog")}
                tone={orphanRows > 0 ? "warn" : "ok"}
                dragHandle
                info={t("performance.info.catalog")}
                actions={
                  canControl ? (
                    <>
                      <OpsHintButton
                        className="btn btn-sm btn-outline-primary"
                        hint={t("performance.opsHint.forceSync")}
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
                      </OpsHintButton>
                      {canDestroy && orphanRows > 0 ? (
                        <OpsHintButton
                          className="btn btn-sm btn-outline-danger"
                          hint={t("performance.opsHint.cleanOrphans")}
                          disabled={busyKey != null}
                          onClick={() => setOrphanOpen(true)}
                        >
                          {t("performance.opsCleanOrphans")}
                        </OpsHintButton>
                      ) : null}
                    </>
                  ) : null
                }
              >
                <PerfStat label={t("performance.opsOrphanRows")} value={formatNumber(orphanRows, 0)} />
                <PerfStat label={t("performance.opsLastCycle")} value={formatCycle(snapshot.CATALOG_LAST_SYNC)} />
              </PerfPanel>
            </div>
            <div key="panel-derived" className="perf-grid-card">
              <PerfPanel
                title={t("performance.opsDerived")}
                tone="ok"
                dragHandle
                info={t("performance.info.derived")}
                actions={
                  canControl ? (
                    <OpsHintButton
                      className="btn btn-sm btn-outline-primary"
                      hint={t("performance.opsHint.rebuildDerived")}
                      disabled={busyKey != null}
                      onClick={() => setRebuildOpen(true)}
                    >
                      {t("performance.opsRebuildDerived")}
                    </OpsHintButton>
                  ) : null
                }
              >
                <PerfStat
                  label={t("performance.opsDerivedCount")}
                  value={formatNumber(snapshot.DERIVED_TAGS_COUNT, 0)}
                />
              </PerfPanel>
            </div>
            <div key="panel-acquisition" className="perf-grid-card">
              <PerfPanel
                title={t("performance.acquisition")}
                tone={snapshot.ACQUISITION_READY ? "ok" : "error"}
                dragHandle
                info={t("performance.info.acquisition")}
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
            <div key="wavelet" className="perf-grid-card">
              <PerfPanel
                title={t("performance.waveletFilters")}
                tone="ok"
                dragHandle
                info={t("performance.info.wavelet")}
                bodyClassName="perf-panel__body--table"
              >
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
              </PerfPanel>
            </div>
            <div key="trend-cpu" className="perf-grid-card perf-grid-card--chart">
              <TrendChart
                dragHandle
                label={t("performance.cpu")}
                points={series.cpu}
                currentLabel={formatNumber(snapshot.HOST_CPU_PERCENT, 1, "%")}
                unit="%"
                threshold={bindings.cpu.catalog?.threshold}
                redAt={bindings.cpu.catalog?.threshold ?? 85}
              />
            </div>
            <div key="trend-rss" className="perf-grid-card perf-grid-card--chart">
              <TrendChart
                dragHandle
                label={t("performance.rss")}
                points={series.rss}
                currentLabel={formatNumber(snapshot.HOST_RSS_MB, 1, "MB")}
                unit="MB"
              />
            </div>
            <div key="trend-disk" className="perf-grid-card perf-grid-card--chart">
              <TrendChart
                dragHandle
                label={t("performance.disk")}
                points={series.disk}
                currentLabel={formatNumber(snapshot.HOST_DISK_USED_PERCENT, 1, "%")}
                unit="%"
                threshold={bindings.disk.catalog?.threshold}
                redAt={bindings.disk.catalog?.threshold ?? 90}
              />
            </div>
            <div key="trend-http" className="perf-grid-card perf-grid-card--chart">
              <TrendChart
                dragHandle
                label={t("performance.http1m")}
                points={series.http}
                currentLabel={formatNumber(snapshot.HTTP_REQUESTS_1M, 0)}
              />
            </div>
          </ResponsiveGridLayout>
        ) : null}
      </div>

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
