import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { ResponsiveGridLayout, getCompactor, type Layout, type LayoutItem } from "react-grid-layout";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";
import { MetricTile } from "../components/MetricTile";
import { PerfPanel, PerfStat } from "../components/PerfPanel";
import { TrendChart } from "../components/TrendChart";
import { useTranslation } from "../hooks/useTranslation";
import {
  getLdsDashboardSnapshot,
  type LdsDashboardSnapshot,
  type LdsEngineRow,
} from "../services/ldsDashboard";
import {
  getLdsDynamicMetrics,
  getLdsEvents,
  getLdsThresholds,
  type LdsDynamicMetrics,
  type LdsEngineAlarmCount,
  type LdsEventRow,
  type LdsEventStats,
  type LdsThresholdRow,
} from "../services/ldsAnalytics";
import {
  classifyLdsEvent,
  getLdsValidationHistory,
  getLdsValidationPending,
  reportLdsMissedLeak,
  type LdsValidationRow,
} from "../services/ldsValidation";
import { listHmiExtensions } from "../services/hmiExtensions";
import { pollIntervalMs } from "../services/performance";
import { VIEW_IDS } from "../utils/access";
import { useAuthz } from "../hooks/useAuthz";

type DashLayoutItem = {
  i: string;
  x: number;
  y: number;
  w: number;
  h: number;
  minW?: number;
  minH?: number;
};

type DashLayouts = {
  lg: DashLayoutItem[];
  md: DashLayoutItem[];
  sm: DashLayoutItem[];
};

const LAYOUT_KEY = "lds_dashboard_layout_v4";
const LAYOUT_KEY_NORMATIVA = "lds_dashboard_normativa_layout_v1";
const LAYOUT_KEY_ALARMAS = "lds_dashboard_alarmas_layout_v1";
const LAYOUT_KEYS_LEGACY = [
  "lds_dashboard_layout_v1",
  "lds_dashboard_layout_v2",
  "lds_dashboard_layout_v3",
  LAYOUT_KEY,
];
const GRID_COMPACTOR = getCompactor(null, false, false);

const DEFAULT_LAYOUT_LG: DashLayoutItem[] = [
  { i: "lds-status", x: 0, y: 0, w: 4, h: 3, minW: 3, minH: 2 },
  { i: "bayes", x: 4, y: 0, w: 4, h: 4, minW: 3, minH: 3 },
  { i: "operation", x: 8, y: 0, w: 4, h: 3, minW: 3, minH: 2 },
  { i: "engines", x: 0, y: 4, w: 6, h: 4, minW: 4, minH: 3 },
  { i: "kpis", x: 6, y: 4, w: 6, h: 4, minW: 4, minH: 3 },
  { i: "trend", x: 0, y: 8, w: 12, h: 5, minW: 6, minH: 3 },
];

const DEFAULT_LAYOUT_MD: DashLayoutItem[] = [
  { i: "lds-status", x: 0, y: 0, w: 6, h: 3, minW: 4, minH: 2 },
  { i: "bayes", x: 6, y: 0, w: 6, h: 4, minW: 4, minH: 3 },
  { i: "operation", x: 0, y: 3, w: 6, h: 3, minW: 4, minH: 2 },
  { i: "kpis", x: 6, y: 4, w: 6, h: 4, minW: 4, minH: 3 },
  { i: "engines", x: 0, y: 8, w: 12, h: 4, minW: 6, minH: 3 },
  { i: "trend", x: 0, y: 12, w: 12, h: 5, minW: 6, minH: 3 },
];

const DEFAULT_LAYOUT_SM: DashLayoutItem[] = [
  { i: "lds-status", x: 0, y: 0, w: 12, h: 3, minW: 12, minH: 2 },
  { i: "bayes", x: 0, y: 3, w: 12, h: 4, minW: 12, minH: 3 },
  { i: "operation", x: 0, y: 7, w: 12, h: 3, minW: 12, minH: 2 },
  { i: "engines", x: 0, y: 10, w: 12, h: 4, minW: 12, minH: 3 },
  { i: "kpis", x: 0, y: 14, w: 12, h: 4, minW: 12, minH: 3 },
  { i: "trend", x: 0, y: 18, w: 12, h: 5, minW: 12, minH: 3 },
];

const DEFAULT_LAYOUTS: DashLayouts = {
  lg: DEFAULT_LAYOUT_LG,
  md: DEFAULT_LAYOUT_MD,
  sm: DEFAULT_LAYOUT_SM,
};

const DEFAULT_NORMATIVA_LG: DashLayoutItem[] = [
  { i: "sensitivity", x: 0, y: 0, w: 3, h: 4, minW: 2, minH: 3 },
  { i: "accuracy", x: 3, y: 0, w: 3, h: 4, minW: 2, minH: 3 },
  { i: "reliability", x: 6, y: 0, w: 3, h: 4, minW: 2, minH: 3 },
  { i: "robustness", x: 9, y: 0, w: 3, h: 4, minW: 2, minH: 3 },
  { i: "trfl", x: 0, y: 4, w: 12, h: 7, minW: 6, minH: 4 },
];

const DEFAULT_NORMATIVA_MD: DashLayoutItem[] = [
  { i: "sensitivity", x: 0, y: 0, w: 6, h: 4, minW: 4, minH: 3 },
  { i: "accuracy", x: 6, y: 0, w: 6, h: 4, minW: 4, minH: 3 },
  { i: "reliability", x: 0, y: 4, w: 6, h: 4, minW: 4, minH: 3 },
  { i: "robustness", x: 6, y: 4, w: 6, h: 4, minW: 4, minH: 3 },
  { i: "trfl", x: 0, y: 8, w: 12, h: 7, minW: 6, minH: 4 },
];

const DEFAULT_NORMATIVA_SM: DashLayoutItem[] = [
  { i: "sensitivity", x: 0, y: 0, w: 12, h: 4, minW: 12, minH: 3 },
  { i: "accuracy", x: 0, y: 4, w: 12, h: 4, minW: 12, minH: 3 },
  { i: "reliability", x: 0, y: 8, w: 12, h: 4, minW: 12, minH: 3 },
  { i: "robustness", x: 0, y: 12, w: 12, h: 4, minW: 12, minH: 3 },
  { i: "trfl", x: 0, y: 16, w: 12, h: 7, minW: 12, minH: 4 },
];

const DEFAULT_NORMATIVA_LAYOUTS: DashLayouts = {
  lg: DEFAULT_NORMATIVA_LG,
  md: DEFAULT_NORMATIVA_MD,
  sm: DEFAULT_NORMATIVA_SM,
};

const DEFAULT_ALARMAS_LG: DashLayoutItem[] = [
  { i: "alarm-thresholds", x: 0, y: 0, w: 6, h: 3, minW: 3, minH: 2 },
  { i: "alarm-engines", x: 6, y: 0, w: 6, h: 3, minW: 3, minH: 2 },
  { i: "alarm-states", x: 0, y: 3, w: 8, h: 4, minW: 4, minH: 3 },
  { i: "alarm-far", x: 8, y: 3, w: 4, h: 4, minW: 3, minH: 3 },
  { i: "alarm-trend", x: 0, y: 7, w: 12, h: 4, minW: 6, minH: 3 },
];

const DEFAULT_ALARMAS_MD: DashLayoutItem[] = [
  { i: "alarm-thresholds", x: 0, y: 0, w: 6, h: 3, minW: 4, minH: 2 },
  { i: "alarm-engines", x: 6, y: 0, w: 6, h: 3, minW: 4, minH: 2 },
  { i: "alarm-states", x: 0, y: 3, w: 12, h: 4, minW: 6, minH: 3 },
  { i: "alarm-far", x: 0, y: 7, w: 12, h: 3, minW: 6, minH: 2 },
  { i: "alarm-trend", x: 0, y: 10, w: 12, h: 4, minW: 6, minH: 3 },
];

const DEFAULT_ALARMAS_SM: DashLayoutItem[] = [
  { i: "alarm-thresholds", x: 0, y: 0, w: 12, h: 3, minW: 12, minH: 2 },
  { i: "alarm-engines", x: 0, y: 3, w: 12, h: 3, minW: 12, minH: 2 },
  { i: "alarm-states", x: 0, y: 6, w: 12, h: 4, minW: 12, minH: 3 },
  { i: "alarm-far", x: 0, y: 10, w: 12, h: 4, minW: 12, minH: 3 },
  { i: "alarm-trend", x: 0, y: 14, w: 12, h: 4, minW: 12, minH: 3 },
];

const DEFAULT_ALARMAS_LAYOUTS: DashLayouts = {
  lg: DEFAULT_ALARMAS_LG,
  md: DEFAULT_ALARMAS_MD,
  sm: DEFAULT_ALARMAS_SM,
};

type TabId = "overview" | "engines" | "normativa" | "events" | "validation" | "alarms";
type Translate = (key: string, params?: Record<string, string | number>) => string;

function formatNumber(value: number | null | undefined, digits = 1, unit = ""): string {
  if (value == null || Number.isNaN(Number(value))) return "—";
  const formatted = Number(value).toLocaleString(undefined, {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits > 0 ? Math.min(digits, 1) : 0,
  });
  return unit ? `${formatted} ${unit}` : formatted;
}

function asLayoutItems(value: unknown): DashLayoutItem[] | null {
  if (!Array.isArray(value) || value.length === 0) return null;
  return value.filter((row): row is DashLayoutItem => Boolean(row && typeof row === "object" && "i" in row));
}

function loadLayouts(key: string, fallback: DashLayouts): DashLayouts {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as Partial<DashLayouts>;
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return fallback;
    const next = upgradeOverviewLayouts({
      lg: asLayoutItems(parsed.lg) || fallback.lg,
      md: asLayoutItems(parsed.md) || fallback.md,
      sm: asLayoutItems(parsed.sm) || fallback.sm,
    });
    if (JSON.stringify(next) !== raw) persistLayouts(key, next);
    return next;
  } catch {
    return fallback;
  }
}

function upgradeOverviewLayouts(layouts: DashLayouts): DashLayouts {
  const bump = (items: DashLayoutItem[]): DashLayoutItem[] => {
    const bayes = items.find((item) => item.i === "bayes");
    if (!bayes || Number(bayes.h) >= 4) return items;
    return items.map((item) => {
      if (item.i === "bayes") return { ...item, h: 4, minH: Math.max(item.minH || 0, 3) };
      if ((item.i === "engines" || item.i === "kpis") && Number(item.y) === 3) {
        return { ...item, y: 4, h: item.h === 5 ? 4 : item.h };
      }
      return item;
    });
  };
  return { lg: bump(layouts.lg), md: bump(layouts.md), sm: bump(layouts.sm) };
}

function persistLayouts(key: string, next: DashLayouts) {
  try {
    localStorage.setItem(key, JSON.stringify(next));
  } catch {
    /* quota */
  }
}

function activeLayoutsOf(layouts: DashLayouts, isMobile: boolean): Record<string, DashLayoutItem[]> {
  const stacked = layouts.sm;
  if (isMobile) {
    return { lg: stacked, md: stacked, sm: stacked, xs: stacked, xxs: stacked };
  }
  return { ...layouts, sm: layouts.sm, xs: layouts.sm, xxs: layouts.sm };
}

function stateTone(state?: string): "ok" | "warn" | "error" | "unknown" {
  const value = (state || "").toLowerCase();
  if (value === "leaking" || value === "leak") return "error";
  if (value.includes("pre_alarm") || value.includes("pre-alarm")) return "warn";
  if (value === "running") return "ok";
  if (value.includes("start") || value.includes("wait")) return "unknown";
  return "unknown";
}

function engineList(data: LdsDashboardSnapshot | null): LdsEngineRow[] {
  return Object.values(data?.engines || {});
}

function clockLabel(timestamp: number | undefined, t: Translate): { text: string; iso: string } {
  if (!timestamp) return { text: t("ldsDashboard.waitingData"), iso: "" };
  const date = new Date(Number(timestamp) * 1000);
  if (Number.isNaN(date.getTime())) return { text: t("ldsDashboard.waitingData"), iso: "" };
  const text = t("ldsDashboard.lastUpdate", {
    time: date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }),
  });
  return { text, iso: date.toISOString() };
}

function operationKey(data: LdsDashboardSnapshot | null): "SS" | "SI" | "TS" | "" {
  const raw = String(data?.lds_operation_key || data?.lds_operation || "").toUpperCase();
  if (raw.includes("SI") || raw.includes("SHUT")) return "SI";
  if (raw.includes("SS") || raw.includes("STABLE") || raw.includes("STEADY")) return "SS";
  if (raw.includes("TS") || raw.includes("TRANS")) return "TS";
  return "";
}

function kpiTone(value: number | null | undefined, kind: "high" | "low"): "ok" | "warn" | "error" | "unknown" {
  if (value == null || Number.isNaN(Number(value))) return "unknown";
  const n = Number(value);
  if (kind === "low") {
    if (n <= 5) return "ok";
    if (n <= 15) return "warn";
    return "error";
  }
  if (n >= 90) return "ok";
  if (n >= 70) return "warn";
  return "error";
}

function eventKind(type?: string): "pre" | "leak" | "other" {
  const value = String(type || "").toUpperCase();
  if (value.includes("PRE")) return "pre";
  if (value.includes("LEAK")) return "leak";
  return "other";
}

function eventLabel(type: string | undefined, t: Translate): string {
  const kind = eventKind(type);
  if (kind === "pre") return t("ldsDashboard.eventPreAlarm");
  if (kind === "leak") return t("ldsDashboard.eventLeak");
  return type || "—";
}

const ENGINE_COLORS: Record<string, string> = {
  NPW: "#0d6efd",
  PPA: "#6f42c1",
  PFM: "#fd7e14",
  OBSERVER: "#20c997",
  LDS: "#0dcaf0",
};

function coverageMap(data: LdsDashboardSnapshot | null): Record<string, Record<string, boolean>> {
  const fromRoot = data?.engines_coverage;
  const fromTrfl = data?.trfl_compliance?.engines_coverage;
  if (fromRoot && typeof fromRoot === "object") return fromRoot;
  if (fromTrfl && typeof fromTrfl === "object") return fromTrfl as Record<string, Record<string, boolean>>;
  return {};
}

export function LdsDashboard() {
  const { t } = useTranslation();
  const { canView } = useAuthz();
  const [tab, setTab] = useState<TabId>("overview");
  const [eventsEngine, setEventsEngine] = useState("");
  const [data, setData] = useState<LdsDashboardSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [layouts, setLayouts] = useState<DashLayouts>(() => loadLayouts(LAYOUT_KEY, DEFAULT_LAYOUTS));
  const [normativaLayouts, setNormativaLayouts] = useState<DashLayouts>(() =>
    loadLayouts(LAYOUT_KEY_NORMATIVA, DEFAULT_NORMATIVA_LAYOUTS)
  );
  const [alarmsLayouts, setAlarmsLayouts] = useState<DashLayouts>(() =>
    loadLayouts(LAYOUT_KEY_ALARMAS, DEFAULT_ALARMAS_LAYOUTS)
  );
  const gridRef = useRef<HTMLDivElement | null>(null);
  const normativaRef = useRef<HTMLDivElement | null>(null);
  const alarmsRef = useRef<HTMLDivElement | null>(null);
  const [gridWidth, setGridWidth] = useState(0);
  const [normativaWidth, setNormativaWidth] = useState(0);
  const [alarmsWidth, setAlarmsWidth] = useState(0);
  const [gridEpoch, setGridEpoch] = useState(0);
  const [normativaEpoch, setNormativaEpoch] = useState(0);
  const [alarmsEpoch, setAlarmsEpoch] = useState(0);
  const [dashboardEnabled, setDashboardEnabled] = useState<boolean | null>(null);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    void listHmiExtensions()
      .then((items) => {
        if (cancelled) return;
        setDashboardEnabled(
          items.some((row) => row.id === "lds-dashboard" || row.path === "/lds-dashboard")
        );
      })
      .catch(() => {
        if (!cancelled) setDashboardEnabled(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const tick = useCallback(async () => {
    try {
      const next = await getLdsDashboardSnapshot();
      setData(next);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "error");
    }
  }, []);

  useEffect(() => {
    if (!dashboardEnabled) return undefined;
    void tick();
    const arm = () => {
      if (timerRef.current) window.clearInterval(timerRef.current);
      // Overview/engines need 3s; events/validation have their own polls — ease snapshot load.
      const baseMs = pollIntervalMs(Boolean(document.hidden));
      const intervalMs =
        tab === "events" || tab === "validation" ? Math.max(baseMs, 10000) : baseMs;
      timerRef.current = window.setInterval(() => {
        void tick();
      }, intervalMs);
    };
    arm();
    const onVis = () => {
      arm();
      if (!document.hidden) void tick();
    };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      document.removeEventListener("visibilitychange", onVis);
      if (timerRef.current) window.clearInterval(timerRef.current);
    };
  }, [tick, tab, dashboardEnabled]);

  useEffect(() => {
    const isGridTab = tab === "overview" || tab === "normativa" || tab === "alarms";
    if (!isGridTab) return undefined;
    const el = tab === "overview" ? gridRef.current : tab === "normativa" ? normativaRef.current : alarmsRef.current;
    if (!el) return undefined;
    const setWidth = tab === "overview" ? setGridWidth : tab === "normativa" ? setNormativaWidth : setAlarmsWidth;
    const bumpEpoch = tab === "overview" ? setGridEpoch : tab === "normativa" ? setNormativaEpoch : setAlarmsEpoch;
    const measure = () => {
      const next = el.clientWidth;
      if (next > 0) setWidth(next);
    };
    measure();
    const tid = window.setTimeout(() => {
      measure();
      bumpEpoch((value) => value + 1);
    }, 0);
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => {
      window.clearTimeout(tid);
      observer.disconnect();
    };
  }, [tab]);

  const activeWidth = tab === "normativa" ? normativaWidth : tab === "alarms" ? alarmsWidth : gridWidth;
  const isMobile = activeWidth > 0 && activeWidth < 768;
  const activeLayouts = useMemo(() => activeLayoutsOf(layouts, isMobile), [isMobile, layouts]);
  const activeNormativaLayouts = useMemo(
    () => activeLayoutsOf(normativaLayouts, isMobile),
    [isMobile, normativaLayouts]
  );
  const activeAlarmsLayouts = useMemo(() => activeLayoutsOf(alarmsLayouts, isMobile), [alarmsLayouts, isMobile]);

  const trendPoints = useMemo(
    () => (data?.trend || []).map((row) => ({ t: Number(row.t) || 0, v: Number(row.v) || 0 })),
    [data]
  );

  const resetLayout = useCallback(() => {
    if (tab === "normativa") {
      try {
        localStorage.removeItem(LAYOUT_KEY_NORMATIVA);
      } catch {
        /* ignore */
      }
      setNormativaLayouts(DEFAULT_NORMATIVA_LAYOUTS);
      persistLayouts(LAYOUT_KEY_NORMATIVA, DEFAULT_NORMATIVA_LAYOUTS);
      setNormativaEpoch((value) => value + 1);
      return;
    }
    if (tab === "alarms") {
      try {
        localStorage.removeItem(LAYOUT_KEY_ALARMAS);
      } catch {
        /* ignore */
      }
      setAlarmsLayouts(DEFAULT_ALARMAS_LAYOUTS);
      persistLayouts(LAYOUT_KEY_ALARMAS, DEFAULT_ALARMAS_LAYOUTS);
      setAlarmsEpoch((value) => value + 1);
      return;
    }
    for (const key of LAYOUT_KEYS_LEGACY) {
      try {
        localStorage.removeItem(key);
      } catch {
        /* ignore */
      }
    }
    setLayouts(DEFAULT_LAYOUTS);
    persistLayouts(LAYOUT_KEY, DEFAULT_LAYOUTS);
    setGridEpoch((value) => value + 1);
  }, [tab]);

  const onLayoutChange = useCallback((current: Layout, all: Partial<Record<string, Layout>>) => {
    const next: DashLayouts = {
      lg: (asLayoutItems(all.lg) || (current as DashLayoutItem[])).map(normalizeItem),
      md: (asLayoutItems(all.md) || DEFAULT_LAYOUTS.md).map(normalizeItem),
      sm: (asLayoutItems(all.sm) || DEFAULT_LAYOUTS.sm).map(normalizeItem),
    };
    if (isMobile) {
      next.sm = (current as DashLayoutItem[]).map(normalizeItem);
    }
    setLayouts(next);
    persistLayouts(LAYOUT_KEY, next);
  }, [isMobile]);

  const onNormativaLayoutChange = useCallback((current: Layout, all: Partial<Record<string, Layout>>) => {
    const next: DashLayouts = {
      lg: (asLayoutItems(all.lg) || (current as DashLayoutItem[])).map(normalizeItem),
      md: (asLayoutItems(all.md) || DEFAULT_NORMATIVA_LAYOUTS.md).map(normalizeItem),
      sm: (asLayoutItems(all.sm) || DEFAULT_NORMATIVA_LAYOUTS.sm).map(normalizeItem),
    };
    if (isMobile) {
      next.sm = (current as DashLayoutItem[]).map(normalizeItem);
    }
    setNormativaLayouts(next);
    persistLayouts(LAYOUT_KEY_NORMATIVA, next);
  }, [isMobile]);

  const onAlarmsLayoutChange = useCallback((current: Layout, all: Partial<Record<string, Layout>>) => {
    const next: DashLayouts = {
      lg: (asLayoutItems(all.lg) || (current as DashLayoutItem[])).map(normalizeItem),
      md: (asLayoutItems(all.md) || DEFAULT_ALARMAS_LAYOUTS.md).map(normalizeItem),
      sm: (asLayoutItems(all.sm) || DEFAULT_ALARMAS_LAYOUTS.sm).map(normalizeItem),
    };
    if (isMobile) {
      next.sm = (current as DashLayoutItem[]).map(normalizeItem);
    }
    setAlarmsLayouts(next);
    persistLayouts(LAYOUT_KEY_ALARMAS, next);
  }, [isMobile]);

  if (!canView(VIEW_IDS.ldsDashboard)) {
    return <Navigate to="/communications" replace />;
  }
  if (dashboardEnabled === false) {
    return <Navigate to="/communications" replace />;
  }
  if (dashboardEnabled !== true) {
    return null;
  }

  const tabs: { id: TabId; label: string }[] = [
    { id: "overview", label: t("ldsDashboard.tabOverview") },
    { id: "engines", label: t("ldsDashboard.tabEngines") },
    { id: "normativa", label: t("ldsDashboard.tabNormativa") },
    { id: "events", label: t("ldsDashboard.tabEvents") },
    { id: "validation", label: t("ldsDashboard.tabValidation") },
    { id: "alarms", label: t("ldsDashboard.tabAlarms") },
  ];

  const engines = engineList(data);
  const motors = data?.bayesian?.motors || {};
  const reliability = data?.api_reliability || {};
  const robustness = data?.api_robustness || {};
  const trfl = data?.trfl_compliance || {};
  const sensitivity = data?.api_sensitivity || {};
  const accuracy = data?.api_accuracy || {};
  const alarms = data?.alarms || [];
  const dynamic = data?.dynamic || null;
  const freshness = clockLabel(data?.timestamp, t);
  const mode = operationKey(data);
  const coverage = coverageMap(data);

  return (
    <div className="performance-page lds-dashboard-page">
      <header className="d-flex flex-wrap align-items-start justify-content-between gap-3 mb-3">
        <div>
          <h1 className="h4 mb-1">{t("ldsDashboard.title")}</h1>
          <p className="text-secondary mb-0">{t("ldsDashboard.subtitle")}</p>
        </div>
        <div className="d-flex flex-wrap align-items-center gap-2">
          {tab === "overview" || tab === "normativa" || tab === "alarms" ? (
            <button
              type="button"
              className="btn btn-sm btn-outline-secondary"
              onClick={resetLayout}
              title={t("ldsDashboard.resetLayoutHint")}
            >
              <i className="bi bi-arrow-counterclockwise me-1" aria-hidden="true" />
              {t("ldsDashboard.resetLayout")}
            </button>
          ) : null}
          <span className="lds-freshness" title={freshness.iso || undefined}>
            <i className="bi bi-clock me-1" aria-hidden="true" />
            {freshness.text}
          </span>
          {error ? <span className="badge text-bg-warning">{t("ldsDashboard.fetchError")}</span> : null}
        </div>
      </header>

      <ul className="nav nav-pills lds-dashboard-tabs mb-3">
        {tabs.map((item) => (
          <li className="nav-item" key={item.id}>
            <button
              type="button"
              className={`nav-link ${tab === item.id ? "active" : ""}`}
              onClick={() => setTab(item.id)}
            >
              {item.label}
            </button>
          </li>
        ))}
      </ul>

      <div
        ref={gridRef}
        className={`lds-dashboard-grid${tab === "overview" ? "" : " lds-dashboard-grid--parked"}`}
        aria-hidden={tab !== "overview"}
      >
        {tab === "overview" && gridWidth > 0 ? (
          <DashFreeGrid
            gridEpoch={gridEpoch}
            width={gridWidth}
            layouts={activeLayouts}
            onLayoutChange={onLayoutChange}
          >
            <div key="lds-status" className="lds-grid-card">
              <PerfPanel
                title={t("ldsDashboard.ldsState")}
                tone={stateTone(data?.lds_state)}
                info={t("ldsDashboard.infoStatus")}
                subtitle={freshness.text}
                dragHandle
              >
                <div className="lds-stat-grid">
                  <PerfStat label={t("ldsDashboard.state")} value={data?.lds_state || "—"} />
                  <PerfStat
                    label={t("ldsDashboard.likelihood")}
                    value={formatNumber(data?.lds_likelihood, 1, "%")}
                  />
                  <PerfStat
                    label={t("ldsDashboard.threshold")}
                    value={formatNumber(data?.lds_threshold, 1, "%")}
                  />
                </div>
              </PerfPanel>
            </div>
            <div key="bayes" className="lds-grid-card">
              <PerfPanel title={t("ldsDashboard.bayes")} tone="ok" info={t("ldsDashboard.infoBayes")} dragHandle>
                <div className="lds-stat-grid">
                  <PerfStat
                    label={t("ldsDashboard.posterior")}
                    value={formatNumber(
                      data?.bayesian?.posterior != null
                        ? Number(data.bayesian.posterior) * 100
                        : data?.lds_likelihood,
                      1,
                      "%"
                    )}
                  />
                  <PerfStat
                    label={t("ldsDashboard.usedMotors")}
                    value={String(data?.bayesian?.used_motor_count ?? "—")}
                  />
                </div>
                <div className="lds-bayes-bars">
                  {Object.entries(motors).length === 0 ? (
                    <EmptyState icon="bi-sliders" title={t("ldsDashboard.noMotors")} />
                  ) : (
                    Object.entries(motors).map(([name, row]) => {
                      const pct = Number(row?.probability ?? 0) * 100;
                      return (
                        <div key={name} className="lds-bayes-row">
                          <span>{name}</span>
                          <div className="lds-bayes-track">
                            <div className="lds-bayes-fill" style={{ width: `${Math.max(0, Math.min(100, pct))}%` }} />
                          </div>
                          <strong>{formatNumber(pct, 0, "%")}</strong>
                        </div>
                      );
                    })
                  )}
                </div>
              </PerfPanel>
            </div>
            <div key="operation" className="lds-grid-card">
              <PerfPanel title={t("ldsDashboard.operation")} tone="ok" info={t("ldsDashboard.infoOperation")} dragHandle>
                <div className="lds-stat-grid">
                  <PerfStat label={t("ldsDashboard.mode")} value={data?.lds_operation || "—"} />
                </div>
                <p className="small text-secondary mb-0 mt-1">{t("ldsDashboard.operationHint")}</p>
              </PerfPanel>
            </div>
            <div key="engines" className="lds-grid-card">
              <PerfPanel title={t("ldsDashboard.engines")} tone="ok" info={t("ldsDashboard.infoEngines")} dragHandle>
                <EngineTable engines={engines} t={t} />
              </PerfPanel>
            </div>
            <div key="kpis" className="lds-grid-card">
              <PerfPanel title={t("ldsDashboard.apiKpis")} tone="ok" info={t("ldsDashboard.infoDynamicKpis")} dragHandle>
                <div className="lds-metrics-grid">
                  <MetricTile
                    label={t("ldsDashboard.sensitivity")}
                    value={formatNumber(dynamic?.sensitivity, 1, "%")}
                    hint={t("ldsDashboard.sensitivityFieldHint")}
                    tone={kpiTone(dynamic?.sensitivity, "high")}
                    info={false}
                    onOpen={() => setTab("alarms")}
                  />
                  <MetricTile
                    label={t("ldsDashboard.accuracy")}
                    value={formatNumber(dynamic?.precision, 1, "%")}
                    hint={t("ldsDashboard.precisionHint")}
                    tone={kpiTone(dynamic?.precision, "high")}
                    info={false}
                    onOpen={() => setTab("alarms")}
                  />
                  <MetricTile
                    label={t("ldsDashboard.robustness")}
                    value={formatNumber(dynamic?.robustness, 1, "%")}
                    hint={t("ldsDashboard.robustnessCoverageHint")}
                    tone={kpiTone(dynamic?.robustness, "high")}
                    info={false}
                    onOpen={() => setTab("normativa")}
                  />
                  <MetricTile
                    label={t("ldsDashboard.falseAlarmRate")}
                    value={formatNumber(dynamic?.false_alarm_rate, 1, "%")}
                    hint={t("ldsDashboard.falseAlarmRateHint")}
                    tone={kpiTone(dynamic?.false_alarm_rate, "low")}
                    info={false}
                    onOpen={() => setTab("alarms")}
                  />
                </div>
              </PerfPanel>
            </div>
            <div key="trend" className="lds-grid-card lds-grid-card--chart">
              <PerfPanel
                title={t("ldsDashboard.trend")}
                tone="ok"
                info={t("ldsDashboard.infoTrend")}
                dragHandle
                className="lds-card--chart"
                bodyClassName="lds-chart-body"
              >
                <div className="lds-chart-container">
                  <TrendChart
                    label={t("ldsDashboard.likelihood")}
                    points={trendPoints}
                    currentLabel={formatNumber(data?.lds_likelihood, 1, "%")}
                    unit="%"
                    threshold={data?.lds_threshold ?? null}
                  />
                </div>
              </PerfPanel>
            </div>
          </DashFreeGrid>
        ) : null}
      </div>

      {tab === "engines" ? (
        <PerfPanel title={t("ldsDashboard.enginesDetail")} tone="ok" info={t("ldsDashboard.infoEngines")}>
          <EngineTable engines={engines} t={t} detailed />
        </PerfPanel>
      ) : null}

      <div
        ref={normativaRef}
        className={`lds-dashboard-grid${tab === "normativa" ? "" : " lds-dashboard-grid--parked"}`}
        aria-hidden={tab !== "normativa"}
      >
        {tab === "normativa" && normativaWidth > 0 ? (
          <DashFreeGrid
            gridEpoch={normativaEpoch}
            width={normativaWidth}
            layouts={activeNormativaLayouts}
            onLayoutChange={onNormativaLayoutChange}
          >
            <div key="sensitivity" className="lds-grid-card">
              <PerfPanel title={t("ldsDashboard.sensitivity")} tone="unknown" info={t("ldsDashboard.infoKpis")} dragHandle>
                <p className="small text-secondary mb-2">{String(sensitivity.note || "")}</p>
                <div className="lds-stat-grid">
                  <PerfStat label={t("ldsDashboard.threshold")} value={formatNumber(data?.lds_threshold, 1, "%")} />
                </div>
              </PerfPanel>
            </div>
            <div key="accuracy" className="lds-grid-card">
              <PerfPanel title={t("ldsDashboard.accuracy")} tone="unknown" info={t("ldsDashboard.infoKpis")} dragHandle>
                <p className="small text-secondary mb-2">{String(accuracy.note || "")}</p>
                <div className="lds-stat-grid">
                  <PerfStat label={t("ldsDashboard.location")} value={formatNumber(Number(accuracy.location_m), 1, "m")} />
                  <PerfStat label={t("ldsDashboard.flow")} value={formatNumber(Number(accuracy.flow_kg_s), 3, "kg/s")} />
                </div>
              </PerfPanel>
            </div>
            <div key="reliability" className="lds-grid-card">
              <PerfPanel title={t("ldsDashboard.reliability")} tone="ok" info={t("ldsDashboard.infoKpis")} dragHandle>
                <p className="small text-secondary mb-2">{String(reliability.note || "")}</p>
                <div className="lds-stat-grid">
                  <PerfStat label={t("ldsDashboard.falseAlarms24h")} value={String(reliability.false_alarms_24h ?? "—")} />
                  <PerfStat label={t("ldsDashboard.confirmed24h")} value={String(reliability.confirmed_24h ?? "—")} />
                </div>
              </PerfPanel>
            </div>
            <div key="robustness" className="lds-grid-card">
              <PerfPanel title={t("ldsDashboard.robustness")} tone="ok" info={t("ldsDashboard.infoRobustness")} dragHandle>
                <RobustnessBreakdown t={t} robustness={robustness} dynamic={dynamic} />
              </PerfPanel>
            </div>
            <div key="trfl" className="lds-grid-card">
              <PerfPanel title={t("ldsDashboard.trflTitle")} tone={trfl.dual_system ? "ok" : "warn"} info={t("ldsDashboard.infoCoverage")} dragHandle>
                <p className="small text-secondary mb-2">{String(trfl.note || "")}</p>
                <CoverageMatrix coverage={coverage} current={mode} t={t} />
                <div className="lds-stat-grid mt-3">
                  <PerfStat label={t("ldsDashboard.dualSystem")} value={trfl.dual_system ? t("ldsDashboard.yes") : t("ldsDashboard.no")} />
                  <PerfStat
                    label={t("ldsDashboard.independent")}
                    value={((trfl.independent_running as string[]) || []).join(", ") || "—"}
                  />
                </div>
              </PerfPanel>
            </div>
          </DashFreeGrid>
        ) : null}
        {tab === "normativa" ? <ValidationAuditLog t={t} items={dynamic?.recent_validations || []} /> : null}
      </div>

      {tab === "events" ? (
        <EventsAnalytics t={t} engines={engines} engineFilter={eventsEngine} onEngineFilter={setEventsEngine} />
      ) : null}

      {tab === "validation" ? <FieldValidation t={t} engines={engines} /> : null}

      <div
        ref={alarmsRef}
        className={`lds-dashboard-grid${tab === "alarms" ? "" : " lds-dashboard-grid--parked"}`}
        aria-hidden={tab !== "alarms"}
      >
        {tab === "alarms" && alarmsWidth > 0 ? (
          <AlarmsAnalytics
            t={t}
            snapshot={dynamic}
            liveAlarms={alarms}
            width={alarmsWidth}
            layouts={activeAlarmsLayouts}
            gridEpoch={alarmsEpoch}
            onLayoutChange={onAlarmsLayoutChange}
            onSelectEngine={(name) => {
              setEventsEngine(name);
              setTab("events");
            }}
          />
        ) : null}
      </div>
    </div>
  );
}

function verdictLabel(verdict: string | null | undefined, t: Translate): string {
  if (verdict === "TRUE_POSITIVE") return t("ldsDashboard.verdictTrue");
  if (verdict === "FALSE_POSITIVE") return t("ldsDashboard.verdictFalse");
  if (verdict === "FALSE_POSITIVE_AUTO") return t("ldsDashboard.verdictFalseAuto");
  if (verdict === "MISSED_LEAK") return t("ldsDashboard.verdictMissed");
  return "—";
}

function localDateTimeValue(date = new Date()): string {
  const copy = new Date(date);
  copy.setMinutes(copy.getMinutes() - copy.getTimezoneOffset());
  return copy.toISOString().slice(0, 16);
}

function FieldValidation({ t, engines }: { t: Translate; engines: LdsEngineRow[] }) {
  const [subTab, setSubTab] = useState<"pending" | "history">("pending");
  const [pending, setPending] = useState<LdsValidationRow[]>([]);
  const [history, setHistory] = useState<LdsValidationPageLike>({ events: [], total: 0 });
  const [offset, setOffset] = useState(0);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [classifyRow, setClassifyRow] = useState<LdsValidationRow | null>(null);
  const [missedOpen, setMissedOpen] = useState(false);

  const reload = useCallback(async () => {
    try {
      const [nextPending, nextHistory] = await Promise.all([
        getLdsValidationPending(),
        getLdsValidationHistory({ range: "7d", limit: 10, offset }),
      ]);
      setPending(nextPending.events || []);
      setHistory({ events: nextHistory.events || [], total: Number(nextHistory.total || 0) });
      setLoadError(null);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "error");
    }
  }, [offset]);

  useEffect(() => {
    void reload();
    const timer = window.setInterval(() => {
      void reload();
    }, 15000);
    return () => window.clearInterval(timer);
  }, [reload]);

  const rows = subTab === "pending" ? pending : history.events;
  const engineNames = Array.from(new Set(["LDS", "NPW", "PPA", "PFM", "OBSERVER", ...engines.map((row) => row.name)]));

  return (
    <PerfPanel title={t("ldsDashboard.tabValidation")} tone={loadError ? "warn" : "ok"} info={t("ldsDashboard.infoValidation")}>
      <div className="lds-validation-toolbar">
        <div className="btn-group btn-group-sm" role="tablist">
          <button
            type="button"
            className={`btn ${subTab === "pending" ? "btn-primary" : "btn-outline-secondary"}`}
            onClick={() => setSubTab("pending")}
          >
            {t("ldsDashboard.pending")}
            <span className="badge text-bg-light ms-2">{pending.length}</span>
          </button>
          <button
            type="button"
            className={`btn ${subTab === "history" ? "btn-primary" : "btn-outline-secondary"}`}
            onClick={() => setSubTab("history")}
          >
            {t("ldsDashboard.history")}
          </button>
        </div>
        <button type="button" className="btn btn-sm btn-outline-danger" onClick={() => setMissedOpen(true)}>
          <i className="bi bi-plus-lg me-1" aria-hidden="true" />
          {t("ldsDashboard.reportMissed")}
        </button>
      </div>
      {loadError ? (
        <EmptyState icon="bi-exclamation-triangle" title={t("ldsDashboard.fetchError")} tone="warn" />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={subTab === "pending" ? "bi-check2-circle" : "bi-clock-history"}
          title={subTab === "pending" ? t("ldsDashboard.noPending") : t("ldsDashboard.noHistory")}
          tone={subTab === "pending" ? "ok" : "neutral"}
        />
      ) : (
        <div className="lds-table-wrap">
          <table className="table table-sm mb-0 lds-table">
            <thead>
              <tr>
                <th>{t("ldsDashboard.time")}</th>
                <th>{t("ldsDashboard.engine")}</th>
                <th>{t("ldsDashboard.likelihood")}</th>
                <th>{t("ldsDashboard.source")}</th>
                {subTab === "history" ? <th>{t("ldsDashboard.verdict")}</th> : null}
                {subTab === "history" ? <th>{t("ldsDashboard.classifiedBy")}</th> : null}
                {subTab === "pending" ? <th>{t("ldsDashboard.action")}</th> : null}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td>{row.timestamp ? new Date(Number(row.timestamp) * 1000).toLocaleString() : "—"}</td>
                  <td>
                    <span className="lds-engine-dot" style={{ background: ENGINE_COLORS[row.engine || ""] || "var(--bs-primary)" }} />
                    {row.engine || "—"}
                  </td>
                  <td>
                    <LikelihoodBar value={row.likelihood} />
                  </td>
                  <td>
                    {row.source_kind === "manual" ? t("ldsDashboard.sourceManual") : t("ldsDashboard.sourceAuto")}
                  </td>
                  {subTab === "history" ? (
                    <td>
                      <span className={`lds-event-pill lds-event-pill--${row.operator_verdict === "FALSE_POSITIVE" || row.operator_verdict === "FALSE_POSITIVE_AUTO" ? "leak" : row.operator_verdict === "MISSED_LEAK" ? "other" : "pre"}`}>
                        {verdictLabel(row.operator_verdict, t)}
                      </span>
                      {row.operator_verdict === "FALSE_POSITIVE_AUTO" || row.automatic ? (
                        <span className="badge text-bg-secondary ms-1">{t("ldsDashboard.badgeAutomatic")}</span>
                      ) : null}
                    </td>
                  ) : null}
                  {subTab === "history" ? (
                    <td>
                      {row.classified_by_kind === "system" || row.operator_verdict === "FALSE_POSITIVE_AUTO"
                        ? t("ldsDashboard.classifiedBySystem")
                        : row.classified_by
                          ? `@${row.classified_by}`
                          : "—"}
                    </td>
                  ) : null}
                  {subTab === "pending" ? (
                    <td>
                      <button type="button" className="btn btn-sm btn-outline-primary" onClick={() => setClassifyRow(row)}>
                        <i className="bi bi-pencil-square me-1" aria-hidden="true" />
                        {t("ldsDashboard.classify")}
                      </button>
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {subTab === "history" ? (
        <div className="lds-pager">
          <span className="text-secondary small">
            {t("ldsDashboard.eventsShowing", {
              from: history.total === 0 ? 0 : offset + 1,
              to: Math.min(offset + history.events.length, history.total),
              total: history.total,
            })}
          </span>
          <div className="btn-group btn-group-sm">
            <button type="button" className="btn btn-outline-secondary" disabled={offset <= 0} onClick={() => setOffset(Math.max(0, offset - 10))}>
              {t("ldsDashboard.prevPage")}
            </button>
            <button
              type="button"
              className="btn btn-outline-secondary"
              disabled={offset + 10 >= history.total}
              onClick={() => setOffset(offset + 10)}
            >
              {t("ldsDashboard.nextPage")}
            </button>
          </div>
        </div>
      ) : null}

      {classifyRow ? (
        <ClassifyModal
          t={t}
          row={classifyRow}
          busy={busy}
          onClose={() => setClassifyRow(null)}
          onConfirm={async (payload) => {
            setBusy(true);
            try {
              await classifyLdsEvent({ leak_id: Number(classifyRow.id), ...payload });
              setClassifyRow(null);
              await reload();
            } finally {
              setBusy(false);
            }
          }}
        />
      ) : null}
      {missedOpen ? (
        <MissedModal
          t={t}
          engines={engineNames}
          busy={busy}
          onClose={() => setMissedOpen(false)}
          onConfirm={async (payload) => {
            setBusy(true);
            try {
              await reportLdsMissedLeak(payload);
              setMissedOpen(false);
              setSubTab("history");
              await reload();
            } finally {
              setBusy(false);
            }
          }}
        />
      ) : null}
    </PerfPanel>
  );
}

type LdsValidationPageLike = { events: LdsValidationRow[]; total: number };

function LikelihoodBar({ value }: { value?: number | null }) {
  if (value == null || Number.isNaN(Number(value))) return <span>—</span>;
  const pct = Math.max(0, Math.min(100, Number(value)));
  return (
    <span className="lds-likely">
      <span className="lds-likely-track">
        <span className="lds-likely-fill" style={{ width: `${pct}%` }} />
      </span>
      {formatNumber(pct, 0, "%")}
    </span>
  );
}

function ClassifyModal({
  t,
  row,
  busy,
  onClose,
  onConfirm,
}: {
  t: Translate;
  row: LdsValidationRow;
  busy: boolean;
  onClose: () => void;
  onConfirm: (payload: {
    verdict: "TRUE_POSITIVE" | "FALSE_POSITIVE";
    field_location?: number | null;
    field_flow?: number | null;
    field_size?: number | null;
    notes?: string;
  }) => Promise<void>;
}) {
  const [verdict, setVerdict] = useState<"TRUE_POSITIVE" | "FALSE_POSITIVE" | "">("");
  const [location, setLocation] = useState("");
  const [flow, setFlow] = useState("");
  const [size, setSize] = useState("");
  const [notes, setNotes] = useState("");
  return (
    <div className="modal fade show d-block lds-field-modal" tabIndex={-1} role="dialog" aria-modal="true" onClick={onClose}>
      <div className="modal-dialog modal-dialog-centered" role="document" onClick={(event) => event.stopPropagation()}>
        <form
          className="modal-content"
          onSubmit={(event) => {
            event.preventDefault();
            if (!verdict || busy) return;
            void onConfirm({
              verdict,
              field_location: verdict === "TRUE_POSITIVE" && location !== "" ? Number(location) : null,
              field_flow: verdict === "TRUE_POSITIVE" && flow !== "" ? Number(flow) : null,
              field_size: verdict === "TRUE_POSITIVE" && size !== "" ? Number(size) : null,
              notes,
            });
          }}
        >
          <div className="modal-header">
            <h5 className="modal-title">{t("ldsDashboard.validateEvent", { id: row.id || "—" })}</h5>
            <button type="button" className="btn-close" aria-label={t("ldsDashboard.close")} onClick={onClose} />
          </div>
          <div className="modal-body">
            <dl className="lds-field-facts">
              <div>
                <dt>{t("ldsDashboard.time")}</dt>
                <dd>{row.timestamp ? new Date(Number(row.timestamp) * 1000).toLocaleString() : "—"}</dd>
              </div>
              <div>
                <dt>{t("ldsDashboard.engine")}</dt>
                <dd>{row.engine || "—"}</dd>
              </div>
              <div>
                <dt>{t("ldsDashboard.likelihood")}</dt>
                <dd>{formatNumber(row.likelihood, 1, "%")}</dd>
              </div>
            </dl>
            <div className="lds-verdict-toggle">
              <button type="button" className={`lds-verdict-btn lds-verdict-btn--true${verdict === "TRUE_POSITIVE" ? " is-active" : ""}`} onClick={() => setVerdict("TRUE_POSITIVE")}>
                {t("ldsDashboard.trueLeak")}
              </button>
              <button type="button" className={`lds-verdict-btn lds-verdict-btn--false${verdict === "FALSE_POSITIVE" ? " is-active" : ""}`} onClick={() => setVerdict("FALSE_POSITIVE")}>
                {t("ldsDashboard.falseAlarm")}
              </button>
            </div>
            {verdict === "TRUE_POSITIVE" ? (
              <FieldInputs
                t={t}
                location={location}
                flow={flow}
                size={size}
                notes={notes}
                onLocation={setLocation}
                onFlow={setFlow}
                onSize={setSize}
                onNotes={setNotes}
                showMeasurements
              />
            ) : (
              <FieldInputs
                t={t}
                location={location}
                flow={flow}
                size={size}
                notes={notes}
                onLocation={setLocation}
                onFlow={setFlow}
                onSize={setSize}
                onNotes={setNotes}
                showMeasurements={false}
              />
            )}
            {verdict === "FALSE_POSITIVE" ? (
              <p className="small text-secondary mb-0 mt-2">{t("ldsDashboard.falseAlarmNoField")}</p>
            ) : null}
          </div>
          <div className="modal-footer">
            <button type="button" className="btn btn-outline-secondary" onClick={onClose} disabled={busy}>
              {t("ldsDashboard.cancel")}
            </button>
            <button type="submit" className="btn btn-primary" disabled={!verdict || busy}>
              {t("ldsDashboard.confirmClass")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function MissedModal({
  t,
  engines,
  busy,
  onClose,
  onConfirm,
}: {
  t: Translate;
  engines: string[];
  busy: boolean;
  onClose: () => void;
  onConfirm: (payload: { timestamp?: string; engine?: string; location?: number | null; flow?: number | null; size?: number | null; notes?: string }) => Promise<void>;
}) {
  const [when, setWhen] = useState(localDateTimeValue());
  const [engine, setEngine] = useState(engines[0] || "LDS");
  const [location, setLocation] = useState("");
  const [flow, setFlow] = useState("");
  const [size, setSize] = useState("");
  const [notes, setNotes] = useState("");
  return (
    <div className="modal fade show d-block lds-field-modal" tabIndex={-1} role="dialog" aria-modal="true" onClick={onClose}>
      <div className="modal-dialog modal-dialog-centered" role="document" onClick={(event) => event.stopPropagation()}>
        <form
          className="modal-content"
          onSubmit={(event) => {
            event.preventDefault();
            if (busy) return;
            void onConfirm({
              timestamp: when,
              engine,
              location: location === "" ? null : Number(location),
              flow: flow === "" ? null : Number(flow),
              size: size === "" ? null : Number(size),
              notes,
            });
          }}
        >
          <div className="modal-header">
            <h5 className="modal-title">{t("ldsDashboard.reportMissed")}</h5>
            <button type="button" className="btn-close" aria-label={t("ldsDashboard.close")} onClick={onClose} />
          </div>
          <div className="modal-body">
            <label className="lds-field-input">
              <span>{t("ldsDashboard.incidentTime")}</span>
              <input className="form-control form-control-sm" type="datetime-local" value={when} onChange={(event) => setWhen(event.target.value)} required />
            </label>
            <label className="lds-field-input">
              <span>{t("ldsDashboard.engine")}</span>
              <select className="form-select form-select-sm" value={engine} onChange={(event) => setEngine(event.target.value)}>
                {engines.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
            <FieldInputs t={t} location={location} flow={flow} size={size} notes={notes} onLocation={setLocation} onFlow={setFlow} onSize={setSize} onNotes={setNotes} />
          </div>
          <div className="modal-footer">
            <button type="button" className="btn btn-outline-secondary" onClick={onClose} disabled={busy}>
              {t("ldsDashboard.cancel")}
            </button>
            <button type="submit" className="btn btn-danger" disabled={busy}>
              {t("ldsDashboard.confirmMissed")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function FieldInputs({
  t,
  location,
  flow,
  size,
  notes,
  onLocation,
  onFlow,
  onSize,
  onNotes,
  showMeasurements = true,
}: {
  t: Translate;
  location: string;
  flow: string;
  size: string;
  notes: string;
  onLocation: (value: string) => void;
  onFlow: (value: string) => void;
  onSize: (value: string) => void;
  onNotes: (value: string) => void;
  showMeasurements?: boolean;
}) {
  return (
    <div className="lds-field-grid">
      {showMeasurements ? (
        <>
          <label className="lds-field-input">
            <span>{t("ldsDashboard.fieldLocation")}</span>
            <input className="form-control form-control-sm" type="number" step="0.1" value={location} onChange={(event) => onLocation(event.target.value)} />
          </label>
          <label className="lds-field-input">
            <span>{t("ldsDashboard.fieldFlow")}</span>
            <input className="form-control form-control-sm" type="number" step="0.001" value={flow} onChange={(event) => onFlow(event.target.value)} />
          </label>
          <label className="lds-field-input">
            <span>{t("ldsDashboard.fieldSize")}</span>
            <input className="form-control form-control-sm" type="number" step="0.01" value={size} onChange={(event) => onSize(event.target.value)} />
          </label>
        </>
      ) : null}
      <label className="lds-field-input lds-field-input--wide">
        <span>{t("ldsDashboard.fieldNotes")}</span>
        <textarea className="form-control form-control-sm" rows={3} value={notes} onChange={(event) => onNotes(event.target.value)} />
      </label>
    </div>
  );
}

function ValidationAuditLog({
  t,
  items,
}: {
  t: Translate;
  items: Array<{
    id?: number;
    verdict?: string;
    classified_by?: string | null;
    validated_at?: number | null;
    engine?: string;
  }>;
}) {
  return (
    <PerfPanel title={t("ldsDashboard.auditLog")} tone="ok" info={t("ldsDashboard.infoAudit")}>
      {items.length === 0 ? (
        <EmptyState icon="bi-journal-text" title={t("ldsDashboard.noHistory")} />
      ) : (
        <ul className="lds-audit-list">
          {items.map((row, index) => (
            <li key={`${row.id}-${index}`}>
              {row.verdict === "FALSE_POSITIVE_AUTO"
                ? t("ldsDashboard.auditLineAuto", {
                    engine: row.engine || "—",
                    time: row.validated_at ? new Date(Number(row.validated_at) * 1000).toLocaleString() : "—",
                  })
                : t("ldsDashboard.auditLine", {
                    id: row.id ?? "—",
                    verdict: verdictLabel(row.verdict, t),
                    user: row.classified_by || "—",
                    time: row.validated_at ? new Date(Number(row.validated_at) * 1000).toLocaleString() : "—",
                  })}
            </li>
          ))}
        </ul>
      )}
    </PerfPanel>
  );
}

function RobustnessBreakdown({
  t,
  robustness,
  dynamic,
}: {
  t: Translate;
  robustness: Record<string, unknown>;
  dynamic: LdsDynamicMetrics | null;
}) {
  const detail = dynamic?.robustness_detail || {};
  const score = dynamic?.robustness ?? robustness.score ?? (Number(robustness.availability_ratio) * 100 || null);
  const states = (detail.states_covered || (robustness.states_covered as string[]) || []) as string[];
  const diags = (detail.diagnostics_covered || (robustness.diagnostics_covered as string[]) || []) as string[];
  const idle = (detail.idle_engines || (robustness.idle_engines as string[]) || []) as string[];
  const mark = (ok: boolean) => (ok ? "✅" : "❌");
  const breakdown = `${t("ldsDashboard.statesCovered")}: SS${mark(states.includes("SS"))} SI${mark(states.includes("SI"))} TS${mark(states.includes("TS"))} → ${states.length}/3. ${t("ldsDashboard.diagsCovered")}: ${t("ldsDashboard.capDetection")}${mark(diags.includes("detection"))} ${t("ldsDashboard.capLocation")}${mark(diags.includes("location"))} ${t("ldsDashboard.capSize")}${mark(diags.includes("size"))} ${t("ldsDashboard.capFlow")}${mark(diags.includes("flow"))} → ${diags.length}/4`;
  return (
    <div>
      <div className="lds-stat-grid mb-2" title={breakdown}>
        <PerfStat label={t("ldsDashboard.robustness")} value={formatNumber(Number(score), 1, "%")} />
      </div>
      <details className="lds-robust-details">
        <summary className="small">{t("ldsDashboard.robustnessBreakdown")}</summary>
        <p className="small mb-1">
          {t("ldsDashboard.statesCovered")}: SS{mark(states.includes("SS"))} SI{mark(states.includes("SI"))} TS
          {mark(states.includes("TS"))} → {states.length}/3
        </p>
        <p className="small mb-1">
          {t("ldsDashboard.diagsCovered")}: {t("ldsDashboard.capDetection")}
          {mark(diags.includes("detection"))} {t("ldsDashboard.capLocation")}
          {mark(diags.includes("location"))} {t("ldsDashboard.capSize")}
          {mark(diags.includes("size"))} {t("ldsDashboard.capFlow")}
          {mark(diags.includes("flow"))} → {diags.length}/4
        </p>
      </details>
      {idle.length > 0 ? (
        <p className="small text-warning mb-0">
          {t("ldsDashboard.idleEngines", { names: idle.join(", ") })}
        </p>
      ) : (
        <p className="small text-secondary mb-0">{t("ldsDashboard.noIdleEngines")}</p>
      )}
    </div>
  );
}

const EVENT_RANGES = ["1h", "6h", "12h", "24h", "7d", "30d"] as const;
const EVENT_LIMITS = [10, 25, 50] as const;

function EventsAnalytics({
  t,
  engines,
  engineFilter,
  onEngineFilter,
}: {
  t: Translate;
  engines: LdsEngineRow[];
  engineFilter: string;
  onEngineFilter: (value: string) => void;
}) {
  const [range, setRange] = useState<(typeof EVENT_RANGES)[number]>("6h");
  const [limit, setLimit] = useState<(typeof EVENT_LIMITS)[number]>(10);
  const [offset, setOffset] = useState(0);
  const engine = engineFilter;
  const setEngine = onEngineFilter;
  const [page, setPage] = useState<{ events: LdsEventRow[]; total: number; stats?: LdsEventStats } | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    setOffset(0);
  }, [range, limit, engine]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const next = await getLdsEvents({
          range,
          limit,
          offset,
          engine: engine || undefined,
          stats: true,
        });
        if (!cancelled) {
          setPage({ events: next.events || [], total: Number(next.total || 0), stats: next.stats });
          setLoadError(null);
        }
      } catch (err) {
        if (!cancelled) setLoadError(err instanceof Error ? err.message : "error");
      }
    };
    void load();
    const timer = window.setInterval(() => {
      void load();
    }, 15000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [range, limit, offset, engine]);

  const events = page?.events || [];
  const total = page?.total || 0;
  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + events.length, total);
  const engineNames = Array.from(
    new Set(["", ...engines.map((row) => row.name), ...events.map((row) => row.engine_name || "")].filter(Boolean))
  );

  return (
    <PerfPanel title={t("ldsDashboard.tabEvents")} tone={loadError ? "warn" : "ok"} info={t("ldsDashboard.infoEvents")}>
      <div className="lds-events-toolbar">
        <label className="lds-filter">
          <span>{t("ldsDashboard.timeRange")}</span>
          <select
            className="form-select form-select-sm"
            value={range}
            onChange={(event) => setRange(event.target.value as (typeof EVENT_RANGES)[number])}
          >
            {EVENT_RANGES.map((key) => (
              <option key={key} value={key}>
                {t(`ldsDashboard.range.${key}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="lds-filter">
          <span>{t("ldsDashboard.pageSize")}</span>
          <select
            className="form-select form-select-sm"
            value={limit}
            onChange={(event) => setLimit(Number(event.target.value) as (typeof EVENT_LIMITS)[number])}
          >
            {EVENT_LIMITS.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </label>
        <label className="lds-filter">
          <span>{t("ldsDashboard.engine")}</span>
          <select className="form-select form-select-sm" value={engine} onChange={(event) => setEngine(event.target.value)}>
            <option value="">{t("ldsDashboard.allEngines")}</option>
            {engineNames.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <span className="badge text-bg-secondary">{t("ldsDashboard.eventsTotal", { total })}</span>
      </div>
      <EventCharts t={t} stats={page?.stats} />
      {loadError ? (
        <EmptyState icon="bi-exclamation-triangle" title={t("ldsDashboard.fetchError")} tone="warn" />
      ) : events.length === 0 ? (
        <EmptyState icon="bi-clock-history" title={t("ldsDashboard.noEvents")} />
      ) : (
        <div className="lds-table-wrap">
          <table className="table table-sm mb-0 lds-table lds-events-table">
            <thead>
              <tr>
                <th>{t("ldsDashboard.time")}</th>
                <th>{t("ldsDashboard.engine")}</th>
                <th>{t("ldsDashboard.event")}</th>
                <th>{t("ldsDashboard.likelihood")}</th>
                <th>{t("ldsDashboard.currentState")}</th>
              </tr>
            </thead>
            <tbody>
              {events.map((row, index) => {
                const kind = eventKind(row.event_type);
                return (
                  <tr key={`${row.id ?? row.timestamp}-${index}`} className={`lds-event-row lds-event-row--${kind}`}>
                    <td>{row.timestamp ? new Date(Number(row.timestamp) * 1000).toLocaleString() : "—"}</td>
                    <td>{row.engine_name || "—"}</td>
                    <td>
                      <span className={`lds-event-pill lds-event-pill--${kind}`}>{eventLabel(row.event_type, t)}</span>
                    </td>
                    <td>{formatNumber(row.likelihood_value, 1, "%")}</td>
                    <td>{row.current_state || "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <div className="lds-pager">
        <span className="text-secondary small">{t("ldsDashboard.eventsShowing", { from, to, total })}</span>
        <div className="btn-group btn-group-sm">
          <button
            type="button"
            className="btn btn-outline-secondary"
            disabled={offset <= 0}
            onClick={() => setOffset(Math.max(0, offset - limit))}
          >
            {t("ldsDashboard.prevPage")}
          </button>
          <button
            type="button"
            className="btn btn-outline-secondary"
            disabled={offset + limit >= total}
            onClick={() => setOffset(offset + limit)}
          >
            {t("ldsDashboard.nextPage")}
          </button>
        </div>
      </div>
    </PerfPanel>
  );
}

function AlarmsAnalytics({
  t,
  snapshot,
  liveAlarms,
  onSelectEngine,
  width,
  layouts,
  gridEpoch,
  onLayoutChange,
}: {
  t: Translate;
  snapshot: LdsDynamicMetrics | null;
  liveAlarms: Array<{ name?: string; state?: string; priority?: number }>;
  onSelectEngine?: (engine: string) => void;
  width: number;
  layouts: Record<string, DashLayoutItem[]>;
  gridEpoch: number;
  onLayoutChange: (current: Layout, all: Partial<Record<string, Layout>>) => void;
}) {
  const [metrics, setMetrics] = useState<LdsDynamicMetrics | null>(snapshot);
  const [thresholds, setThresholds] = useState<LdsThresholdRow[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    if (snapshot) setMetrics(snapshot);
  }, [snapshot]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const [dyn, rows] = await Promise.all([getLdsDynamicMetrics("24h"), getLdsThresholds()]);
        if (!cancelled) {
          setMetrics(dyn);
          setThresholds(rows);
          setLoadError(null);
        }
      } catch (err) {
        if (!cancelled) setLoadError(err instanceof Error ? err.message : "error");
      }
    };
    void load();
    const timer = window.setInterval(() => {
      void load();
    }, 30000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  const byEngine = metrics?.alarms_by_engine || {};
  const hourly = metrics?.hourly || [];

  return (
    <div className="lds-alarms-analytics">
      <DashFreeGrid width={width} layouts={layouts} gridEpoch={gridEpoch} onLayoutChange={onLayoutChange}>
        <div key="alarm-thresholds" className="lds-grid-card">
          <PerfPanel title={t("ldsDashboard.thresholdConfig")} tone="ok" info={t("ldsDashboard.infoThresholds")} dragHandle>
            {thresholds.length === 0 ? (
              <EmptyState icon="bi-sliders" title={t("ldsDashboard.noThresholds")} />
            ) : (
              <div className="lds-table-wrap">
                <table className="table table-sm mb-0 lds-table">
                  <thead>
                    <tr>
                      <th>{t("ldsDashboard.engine")}</th>
                      <th>SS</th>
                      <th>SI</th>
                      <th>TS</th>
                      <th>{t("ldsDashboard.unit")}</th>
                      <th>{t("ldsDashboard.state")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {thresholds.map((row) => (
                      <tr key={row.engine}>
                        <td>{row.engine}</td>
                        <td>{formatNumber(row.SS, 2)}</td>
                        <td>{formatNumber(row.SI, 2)}</td>
                        <td>{formatNumber(row.TS, 2)}</td>
                        <td>{row.unit || "—"}</td>
                        <td>{row.state || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </PerfPanel>
        </div>
        <div key="alarm-engines" className="lds-grid-card">
          <PerfPanel title={t("ldsDashboard.alarmsByEngine")} tone="ok" info={t("ldsDashboard.infoAlarmsCharts")} dragHandle>
            <EngineBarChart values={byEngine} empty={t("ldsDashboard.noAlarmHistory")} onSelect={onSelectEngine} />
          </PerfPanel>
        </div>
        <div key="alarm-states" className="lds-grid-card">
          <PerfPanel title={t("ldsDashboard.alarmsByState")} tone="ok" info={t("ldsDashboard.infoAlarmsCharts")} dragHandle>
            <GroupedStateChart values={metrics?.alarms_by_state || {}} empty={t("ldsDashboard.noAlarmHistory")} />
          </PerfPanel>
        </div>
        <div key="alarm-far" className="lds-grid-card">
          <PerfPanel title={t("ldsDashboard.farByEngine")} tone="ok" info={t("ldsDashboard.infoAlarmsCharts")} dragHandle>
            <FarByEngine t={t} rates={metrics?.false_alarm_rate_by_engine || {}} empty={t("ldsDashboard.noClassified")} />
          </PerfPanel>
        </div>
        <div key="alarm-trend" className="lds-grid-card">
          <PerfPanel title={t("ldsDashboard.alarmTrend")} tone="ok" info={t("ldsDashboard.infoAlarmsCharts")} dragHandle>
            <HourlyLineChart points={hourly} empty={t("ldsDashboard.noAlarmHistory")} />
          </PerfPanel>
        </div>
      </DashFreeGrid>
      {loadError ? <p className="small text-warning mb-0">{t("ldsDashboard.fetchError")}</p> : null}
      {liveAlarms.length > 0 ? (
        <p className="small text-secondary mb-0">{t("ldsDashboard.activeAlarmsHint", { count: liveAlarms.length })}</p>
      ) : null}
    </div>
  );
}

function engineAlarmTotal(value: LdsEngineAlarmCount | undefined): number {
  if (typeof value === "number") return value;
  return Number(value?.total || 0);
}

function EngineBarChart({
  values,
  empty,
  onSelect,
}: {
  values: Record<string, LdsEngineAlarmCount>;
  empty: string;
  onSelect?: (engine: string) => void;
}) {
  const rows = Object.entries(values);
  const max = Math.max(1, ...rows.map(([, value]) => engineAlarmTotal(value)));
  if (rows.length === 0) return <EmptyState icon="bi-bar-chart" title={empty} />;
  return (
    <div className="lds-bar-chart" role="img" aria-label="alarms by engine">
      {rows.map(([name, value]) => {
        const n = engineAlarmTotal(value);
        return (
          <button
            type="button"
            key={name}
            className="lds-bar-row lds-bar-row--button"
            onClick={() => onSelect?.(name)}
            title={name}
          >
            <span>{name}</span>
            <div className="lds-bar-track">
              <div
                className="lds-bar-fill"
                style={{ width: `${(n / max) * 100}%`, background: ENGINE_COLORS[name] || "var(--bs-primary)" }}
              />
            </div>
            <strong>{n}</strong>
          </button>
        );
      })}
    </div>
  );
}

function EventCharts({ t, stats }: { t: Translate; stats?: LdsEventStats }) {
  const byEngine = stats?.by_engine || {};
  const byState = stats?.by_state || stats?.by_operation_state || {};
  const unknownState = Number(stats?.by_state_unknown || 0);
  const timeseries = stats?.timeseries || [];
  const stampedTotal = Object.values(byState).reduce((sum, value) => sum + Number(value || 0), 0);
  const hasAny = Object.keys(byEngine).length > 0 || timeseries.length > 0 || stampedTotal > 0 || unknownState > 0;
  if (!stats || !hasAny) {
    return (
      <div className="text-center text-muted p-4">
        <i className="bi bi-bar-chart-line fs-2" aria-hidden="true" />
        <p className="mt-2 mb-0">{t("ldsDashboard.noChartData")}</p>
      </div>
    );
  }
  return (
    <div className="lds-event-charts">
      <section>
        <h3 className="lds-chart-title">{t("ldsDashboard.eventsByEngine")}</h3>
        <StackedEngineChart
          byEngine={byEngine}
          byType={stats.by_type || {}}
          byEngineType={stats.by_engine_type}
          empty={t("ldsDashboard.noChartData")}
          preLabel={t("ldsDashboard.eventPreAlarm")}
          leakLabel={t("ldsDashboard.eventLeak")}
          otherLabel={t("ldsDashboard.eventOther")}
        />
      </section>
      <section>
        <h3 className="lds-chart-title">{t("ldsDashboard.eventsTrend")}</h3>
        <p className="small text-secondary mb-2">{t("ldsDashboard.eventsTrendHint")}</p>
        <MultiLineChart points={timeseries} empty={t("ldsDashboard.noChartData")} t={t} />
      </section>
      <section>
        <h3 className="lds-chart-title">{t("ldsDashboard.eventsByState")}</h3>
        <p className="small text-secondary mb-2">{t("ldsDashboard.eventsByStateHint")}</p>
        {stampedTotal > 0 ? (
          <StateDonut
            values={byState}
            empty={t("ldsDashboard.noChartData")}
            centerLabel={t("ldsDashboard.eventsStamped", { total: stampedTotal })}
          />
        ) : (
          <EmptyState icon="bi-pie-chart" title={t("ldsDashboard.noStampedState")} />
        )}
        {unknownState > 0 ? (
          <p className="small text-warning mb-0 mt-2">
            {t("ldsDashboard.eventsStateUnknown", { count: unknownState })}
          </p>
        ) : null}
      </section>
    </div>
  );
}

function StackedEngineChart({
  byEngine,
  byType,
  byEngineType,
  empty,
  preLabel,
  leakLabel,
  otherLabel,
}: {
  byEngine: Record<string, number>;
  byType: Record<string, number>;
  byEngineType?: Record<string, { total?: number; pre_alarm?: number; leak?: number; other?: number }>;
  empty: string;
  preLabel: string;
  leakLabel: string;
  otherLabel: string;
}) {
  const names = Object.keys(byEngineType || byEngine);
  if (names.length === 0) return <EmptyState icon="bi-bar-chart" title={empty} />;
  const totals = names.map((name) => Number(byEngineType?.[name]?.total ?? byEngine[name] ?? 0));
  const max = Math.max(1, ...totals);
  const globalTotal = Number(byType.pre_alarm || 0) + Number(byType.leak || 0) + Number(byType.other || 0) || 1;
  return (
    <div className="lds-stacked-chart">
      {names.map((name) => {
        const typed = byEngineType?.[name];
        const total = Number(typed?.total ?? byEngine[name] ?? 0);
        const pre = typed ? Number(typed.pre_alarm || 0) : total * (Number(byType.pre_alarm || 0) / globalTotal);
        const leak = typed ? Number(typed.leak || 0) : total * (Number(byType.leak || 0) / globalTotal);
        const other = typed ? Number(typed.other || 0) : total * (Number(byType.other || 0) / globalTotal);
        return (
          <div key={name} className="lds-bar-row" title={`${name}: ${preLabel} ${pre}, ${leakLabel} ${leak}, ${otherLabel} ${other}`}>
            <span>{name}</span>
            <div className="lds-bar-track lds-bar-track--stack">
              <div className="lds-bar-fill" style={{ width: `${(pre / max) * 100}%`, background: "#ffc107" }} />
              <div className="lds-bar-fill" style={{ width: `${(leak / max) * 100}%`, background: "#dc3545" }} />
              <div className="lds-bar-fill" style={{ width: `${(other / max) * 100}%`, background: "#0d6efd" }} />
            </div>
            <strong>{total}</strong>
          </div>
        );
      })}
      <ul className="lds-chart-legend">
        <li><i style={{ background: "#ffc107" }} />{preLabel}</li>
        <li><i style={{ background: "#dc3545" }} />{leakLabel}</li>
        <li><i style={{ background: "#0d6efd" }} />{otherLabel}</li>
      </ul>
    </div>
  );
}

const TS_META_KEYS = new Set(["time", "label", "total"]);

function formatHourLabel(row: Record<string, string | number>): string {
  if (typeof row.label === "string" && row.label) return row.label;
  const raw = String(row.time || "");
  try {
    const dt = new Date(raw);
    if (!Number.isNaN(dt.getTime())) {
      return dt.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hour12: false });
    }
  } catch {
    /* ignore */
  }
  return raw.slice(11, 16) || raw;
}

function MultiLineChart({
  points,
  empty,
  t,
}: {
  points: Array<Record<string, string | number>>;
  empty: string;
  t: Translate;
}) {
  if (points.length === 0) return <EmptyState icon="bi-graph-up" title={empty} />;
  const engines = Array.from(
    new Set(points.flatMap((row) => Object.keys(row).filter((key) => !TS_META_KEYS.has(key))))
  );
  const totals = points.map((row) => Number(row.total ?? engines.reduce((sum, name) => sum + Number(row[name] || 0), 0)));
  const max = Math.max(1, ...engines.flatMap((name) => points.map((row) => Number(row[name] || 0))), ...totals);
  const w = 560;
  const h = 180;
  const padL = 36;
  const padR = 12;
  const padT = 12;
  const padB = 36;
  const plotW = w - padL - padR;
  const plotH = h - padT - padB;
  const n = Math.max(1, points.length - 1);
  const yTicks = [0, Math.round(max / 2), max];
  const xStep = Math.max(1, Math.floor(points.length / 6));
  const peakIdx = totals.indexOf(Math.max(...totals));
  const peak = points[peakIdx];
  const peakTotal = totals[peakIdx] || 0;

  return (
    <div className="lds-trend-chart">
      <svg className="lds-line-chart" viewBox={`0 0 ${w} ${h}`} role="img" aria-label={t("ldsDashboard.eventsTrend")}>
        {yTicks.map((tick) => {
          const y = padT + plotH - (tick / max) * plotH;
          return (
            <g key={`y-${tick}`}>
              <line x1={padL} y1={y} x2={w - padR} y2={y} stroke="currentColor" strokeOpacity="0.12" />
              <text x={padL - 6} y={y + 3} textAnchor="end" className="lds-chart-axis">
                {tick}
              </text>
            </g>
          );
        })}
        <line x1={padL} y1={padT + plotH} x2={w - padR} y2={padT + plotH} stroke="currentColor" strokeOpacity="0.35" />
        <line x1={padL} y1={padT} x2={padL} y2={padT + plotH} stroke="currentColor" strokeOpacity="0.35" />
        {engines.map((name) => {
          const coords = points.map((row, index) => {
            const x = padL + (index / n) * plotW;
            const y = padT + plotH - (Number(row[name] || 0) / max) * plotH;
            return { x, y, n: Number(row[name] || 0) };
          });
          return (
            <g key={name}>
              <polyline
                fill="none"
                stroke={ENGINE_COLORS[name] || "var(--bs-primary)"}
                strokeWidth="2"
                points={coords.map((c) => `${c.x},${c.y}`).join(" ")}
              />
              {coords.map((c, index) => (
                <circle key={`${name}-${index}`} cx={c.x} cy={c.y} r="3" fill={ENGINE_COLORS[name] || "var(--bs-primary)"}>
                  <title>
                    {`${formatHourLabel(points[index])} · ${name}: ${c.n} · ${t("ldsDashboard.eventsHourTotal")}: ${totals[index]}`}
                  </title>
                </circle>
              ))}
            </g>
          );
        })}
        {points.map((row, index) => {
          if (index % xStep !== 0 && index !== points.length - 1) return null;
          const x = padL + (index / n) * plotW;
          return (
            <text key={`x-${index}`} x={x} y={h - 10} textAnchor="middle" className="lds-chart-axis">
              {formatHourLabel(row)}
            </text>
          );
        })}
      </svg>
      <p className="small text-secondary mb-1">
        {t("ldsDashboard.eventsTrendPeak", {
          time: peak ? formatHourLabel(peak) : "—",
          count: peakTotal,
        })}
      </p>
      <ul className="lds-chart-legend">
        {engines.map((name) => (
          <li key={name}>
            <i style={{ background: ENGINE_COLORS[name] || "var(--bs-primary)" }} />
            {name}
          </li>
        ))}
      </ul>
      <div className="lds-trend-table-wrap">
        <table className="table table-sm mb-0 lds-table lds-trend-table">
          <thead>
            <tr>
              <th>{t("ldsDashboard.hour")}</th>
              {engines.map((name) => (
                <th key={name}>{name}</th>
              ))}
              <th>{t("ldsDashboard.eventsHourTotal")}</th>
            </tr>
          </thead>
          <tbody>
            {points.map((row, index) => (
              <tr key={`${row.time}-${index}`}>
                <td>{formatHourLabel(row)}</td>
                {engines.map((name) => (
                  <td key={name}>{Number(row[name] || 0)}</td>
                ))}
                <td>
                  <strong>{totals[index]}</strong>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StateDonut({
  values,
  empty,
  centerLabel,
}: {
  values: Record<string, number>;
  empty: string;
  centerLabel: string;
}) {
  const total = Object.values(values).reduce((sum, value) => sum + Number(value || 0), 0);
  if (total <= 0) return <EmptyState icon="bi-pie-chart" title={empty} />;
  const colors: Record<string, string> = { SS: "#0d6efd", SI: "#6f42c1", TS: "#fd7e14" };
  let offset = 0;
  const r = 42;
  const c = 2 * Math.PI * r;
  return (
    <div className="lds-donut">
      <svg viewBox="0 0 120 120" aria-hidden="true">
        {Object.entries(values).map(([name, raw]) => {
          const value = Number(raw || 0);
          const dash = (value / total) * c;
          const circle = (
            <circle
              key={name}
              cx="60"
              cy="60"
              r={r}
              fill="none"
              stroke={colors[name] || "#6c757d"}
              strokeWidth="16"
              strokeDasharray={`${dash} ${c - dash}`}
              strokeDashoffset={-offset}
              transform="rotate(-90 60 60)"
            />
          );
          offset += dash;
          return circle;
        })}
        <text x="60" y="64" textAnchor="middle" className="lds-donut-value">
          {total}
        </text>
      </svg>
      <ul>
        {Object.entries(values).map(([name, raw]) => (
          <li key={name}>
            <i style={{ background: colors[name] || "#6c757d" }} />
            {name} ({Number(raw || 0)})
          </li>
        ))}
        <li className="text-secondary">{centerLabel}</li>
      </ul>
    </div>
  );
}

function GroupedStateChart({ values, empty }: { values: Record<string, Record<string, number>>; empty: string }) {
  const modes = ["SS", "SI", "TS"];
  const engines = Array.from(new Set(modes.flatMap((mode) => Object.keys(values[mode] || {}))));
  if (engines.length === 0) return <EmptyState icon="bi-bar-chart" title={empty} />;
  const max = Math.max(
    1,
    ...modes.flatMap((mode) => engines.map((name) => Number(values[mode]?.[name] || 0)))
  );
  return (
    <div className="lds-grouped-chart">
      {modes.map((mode) => (
        <div key={mode} className="lds-grouped-col">
          <strong>{mode}</strong>
          {engines.map((name) => {
            const n = Number(values[mode]?.[name] || 0);
            return (
              <div key={name} className="lds-grouped-bar" title={`${name}: ${n}`}>
                <div style={{ height: `${(n / max) * 80}px`, background: ENGINE_COLORS[name] || "var(--bs-primary)" }} />
                <span>{name}</span>
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}

function FarByEngine({ rates, empty, t }: { rates: Record<string, number | null>; empty: string; t: Translate }) {
  const rows = Object.entries(rates);
  if (rows.length === 0) return <EmptyState icon="bi-speedometer2" title={empty} />;
  return (
    <div className="lds-far-list">
      {rows.map(([name, rate]) => {
        const warn = rate != null && rate > 10;
        return (
          <div key={name} className="lds-far-row">
            <span>{name}</span>
            <strong>{formatNumber(rate, 1, "%")}</strong>
            <span className={`badge ${warn ? "text-bg-warning" : "text-bg-success"}`}>
              {warn ? t("ldsDashboard.review") : t("ldsDashboard.highSensitivity")}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function ClassDonut({
  tp,
  fp,
  precision,
  empty,
  tpLabel,
  fpLabel,
}: {
  tp: number;
  fp: number;
  precision: number | null;
  empty: string;
  tpLabel: string;
  fpLabel: string;
}) {
  const total = tp + fp;
  if (total <= 0) return <EmptyState icon="bi-pie-chart" title={empty} />;
  const tpPct = (tp / total) * 100;
  const r = 42;
  const c = 2 * Math.PI * r;
  const tpDash = (tp / total) * c;
  return (
    <div className="lds-donut">
      <svg viewBox="0 0 120 120" aria-hidden="true">
        <circle cx="60" cy="60" r={r} fill="none" stroke="#dc3545" strokeWidth="16" />
        <circle
          cx="60"
          cy="60"
          r={r}
          fill="none"
          stroke="#28a745"
          strokeWidth="16"
          strokeDasharray={`${tpDash} ${c - tpDash}`}
          strokeDashoffset={c * 0.25}
          transform="rotate(-90 60 60)"
        />
        <text x="60" y="58" textAnchor="middle" className="lds-donut-value">
          {precision == null ? "—" : `${precision.toFixed(1)}%`}
        </text>
        <text x="60" y="74" textAnchor="middle" className="lds-donut-label">
          {tpPct.toFixed(0)}%
        </text>
      </svg>
      <ul>
        <li>
          <i style={{ background: "#28a745" }} />
          {tpLabel} ({tp})
        </li>
        <li>
          <i style={{ background: "#dc3545" }} />
          {fpLabel} ({fp})
        </li>
      </ul>
    </div>
  );
}

function HourlyLineChart({ points, empty }: { points: Array<{ t?: string; v?: number }>; empty: string }) {
  if (points.length === 0) return <EmptyState icon="bi-graph-up" title={empty} />;
  const values = points.map((row) => Number(row.v) || 0);
  const max = Math.max(1, ...values);
  const w = 560;
  const h = 140;
  const pad = 12;
  const coords = values.map((value, index) => {
    const x = pad + (index / Math.max(1, values.length - 1)) * (w - pad * 2);
    const y = h - pad - (value / max) * (h - pad * 2);
    return `${x},${y}`;
  });
  return (
    <svg className="lds-line-chart" viewBox={`0 0 ${w} ${h}`} role="img" aria-label="hourly alarms">
      <polyline fill="none" stroke="var(--bs-primary)" strokeWidth="2" points={coords.join(" ")} />
      {values.map((value, index) => {
        const [x, y] = coords[index].split(",");
        return <circle key={`${points[index]?.t}-${index}`} cx={x} cy={y} r="3" fill="var(--bs-primary)" />;
      })}
    </svg>
  );
}

function DashFreeGrid({
  width,
  layouts,
  gridEpoch,
  onLayoutChange,
  children,
}: {
  width: number;
  layouts: Record<string, DashLayoutItem[]>;
  gridEpoch: number;
  onLayoutChange: (current: Layout, all: Partial<Record<string, Layout>>) => void;
  children: ReactNode;
}) {
  return (
    <ResponsiveGridLayout
      key={gridEpoch}
      className="layout"
      width={width}
      layouts={layouts}
      breakpoints={{ lg: 1200, md: 996, sm: 768, xs: 480, xxs: 0 }}
      cols={{ lg: 12, md: 12, sm: 12, xs: 12, xxs: 12 }}
      rowHeight={60}
      margin={[8, 8]}
      containerPadding={[8, 8]}
      dragConfig={{
        enabled: true,
        bounded: true,
        handle: ".lds-card-handle",
        cancel: ".perf-tile__tools,button,a,input,select,textarea",
        threshold: 3,
      }}
      resizeConfig={{ enabled: true, handles: ["se"] }}
      compactor={GRID_COMPACTOR}
      onLayoutChange={onLayoutChange}
    >
      {children}
    </ResponsiveGridLayout>
  );
}

function normalizeItem(item: LayoutItem | DashLayoutItem): DashLayoutItem {
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

function EmptyState({
  icon,
  title,
  tone = "neutral",
}: {
  icon: string;
  title: string;
  tone?: "ok" | "warn" | "neutral";
}) {
  return (
    <div className={`lds-empty-state lds-empty-state--${tone}`}>
      <i className={`bi ${icon}`} aria-hidden="true" />
      <p>{title}</p>
    </div>
  );
}

function UnitHeader({ label, unit }: { label: string; unit?: string }) {
  return (
    <th>
      {label}
      {unit ? <span className="text-muted fw-normal d-block small">{unit}</span> : null}
    </th>
  );
}

function stateIcon(state?: string): { icon: string; tone: string } {
  const value = (state || "").toLowerCase();
  if (value === "leaking" || value === "leak") return { icon: "bi-exclamation-octagon-fill", tone: "text-danger" };
  if (value.includes("pre_alarm") || value.includes("pre-alarm")) return { icon: "bi-exclamation-triangle-fill", tone: "text-warning" };
  if (value === "running") return { icon: "bi-play-circle-fill", tone: "text-success" };
  return { icon: "bi-hourglass-split", tone: "text-secondary" };
}

function estimateValue(row: LdsEngineRow, key: "flow" | "size" | "location"): number | null {
  if (key === "flow") return row.flow ?? row.leak_flow ?? null;
  if (key === "size") return row.size ?? row.leak_size ?? null;
  return row.location ?? row.leak_location ?? null;
}

function EngineTable({
  engines,
  t,
}: {
  engines: LdsEngineRow[];
  t: Translate;
  detailed?: boolean;
}) {
  if (engines.length === 0) {
    return <EmptyState icon="bi-cpu" title={t("ldsDashboard.noEngines")} />;
  }
  return (
    <div className="lds-table-wrap">
      <table className="table table-sm mb-0 lds-table lds-engine-table">
        <thead>
          <tr>
            <th>{t("ldsDashboard.engine")}</th>
            <th>{t("ldsDashboard.state")}</th>
            <UnitHeader label={t("ldsDashboard.likelihood")} unit="(%)" />
            <UnitHeader label={t("ldsDashboard.leakFlow")} unit="(kg/s)" />
            <UnitHeader label={t("ldsDashboard.leakSize")} unit="(in)" />
            <UnitHeader label={t("ldsDashboard.leakLocation")} unit="(m)" />
          </tr>
        </thead>
        <tbody>
          {engines.map((row) => {
            const mark = stateIcon(row.state);
            return (
              <tr key={row.name}>
                <td>{row.name}</td>
                <td>
                  <span className="lds-state-cell">
                    <i className={`bi ${mark.icon} ${mark.tone}`} aria-hidden="true" />
                    <span>{row.state}</span>
                  </span>
                </td>
                <td>{formatNumber(row.likelihood, 1)}</td>
                <td>{formatNumber(estimateValue(row, "flow"), 3)}</td>
                <td>{formatNumber(estimateValue(row, "size"), 3)}</td>
                <td>{formatNumber(estimateValue(row, "location"), 1)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function CoverageMatrix({
  coverage,
  current,
  t,
}: {
  coverage: Record<string, Record<string, boolean>>;
  current: "SS" | "SI" | "TS" | "";
  t: Translate;
}) {
  const modes = ["SS", "SI", "TS"] as const;
  const labels: Record<(typeof modes)[number], string> = {
    SS: t("ldsDashboard.modeSS"),
    SI: t("ldsDashboard.modeSI"),
    TS: t("ldsDashboard.modeTS"),
  };
  const rows = Object.keys(coverage);
  if (rows.length === 0) {
    return <EmptyState icon="bi-grid-3x3" title={t("ldsDashboard.noCoverage")} />;
  }
  const totals = modes.map((mode) => rows.filter((name) => name !== "LDS" && coverage[name]?.[mode]).length);
  const denom = rows.filter((name) => name !== "LDS").length || rows.length;
  return (
    <div className="lds-table-wrap">
      <table className="table table-sm mb-0 lds-table lds-coverage-table">
        <thead>
          <tr>
            <th>{t("ldsDashboard.engine")}</th>
            {modes.map((mode) => (
              <th key={mode} className={current === mode ? "lds-coverage-col--current" : undefined}>
                {labels[mode]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((name) => (
            <tr key={name}>
              <td>{name}</td>
              {modes.map((mode) => (
                <td key={mode} className={current === mode ? "lds-coverage-col--current" : undefined}>
                  <CoverageMark ok={Boolean(coverage[name]?.[mode])} />
                </td>
              ))}
            </tr>
          ))}
          <tr className="lds-coverage-total">
            <td>{t("ldsDashboard.currentCoverage")}</td>
            {totals.map((count, index) => (
              <td key={modes[index]} className={current === modes[index] ? "lds-coverage-col--current" : undefined}>
                {count}/{denom}
              </td>
            ))}
          </tr>
        </tbody>
      </table>
    </div>
  );
}

function CoverageMark({ ok }: { ok: boolean }) {
  return (
    <span className={ok ? "lds-coverage-mark lds-coverage-mark--ok" : "lds-coverage-mark lds-coverage-mark--no"} aria-label={ok ? "yes" : "no"}>
      <i className={`bi ${ok ? "bi-check-circle-fill" : "bi-x-circle-fill"}`} aria-hidden="true" />
    </span>
  );
}
