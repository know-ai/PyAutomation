import { axiosErrorMessage } from "./health";
import {
  getNodePerformance,
  pollIntervalMs,
  type NodePerformanceSnapshot,
  type PerfAlarmsCatalog,
} from "./performance";

export type SparkKey = "cpu" | "rss" | "disk" | "http" | "saf";
export type TrendPoint = { t: number; v: number };

export const TREND_WINDOW_MS = 5 * 60 * 1000;
export const TREND_MAX_POINTS = 120;

export type PerformanceTrendState = {
  snapshot: NodePerformanceSnapshot;
  series: Record<SparkKey, TrendPoint[]>;
  errorStatus: number | null;
  errorMessage: string | null;
  updatedAt: number | null;
};

const EMPTY_SERIES: Record<SparkKey, TrendPoint[]> = {
  cpu: [],
  rss: [],
  disk: [],
  http: [],
  saf: [],
};

const listeners = new Set<() => void>();

let state: PerformanceTrendState = {
  snapshot: {},
  series: EMPTY_SERIES,
  errorStatus: null,
  errorMessage: null,
  updatedAt: null,
};

let started = false;
let timer: ReturnType<typeof setInterval> | undefined;
let inFlight = false;

function emit() {
  listeners.forEach((listener) => listener());
}

const SPARK_KEYS: SparkKey[] = ["cpu", "rss", "disk", "http", "saf"];

function asPoints(raw: unknown): TrendPoint[] | null {
  if (!Array.isArray(raw)) return null;
  const points: TrendPoint[] = [];
  for (const item of raw) {
    const row = item as { t?: unknown; v?: unknown };
    const t = Number(row?.t);
    const v = Number(row?.v);
    if (!Number.isFinite(t) || !Number.isFinite(v)) continue;
    points.push({ t, v });
  }
  return points;
}

function metricOf(data: NodePerformanceSnapshot, key: SparkKey): number | null {
  const map: Record<SparkKey, number | null | undefined> = {
    cpu: data.HOST_CPU_PERCENT,
    rss: data.HOST_RSS_MB,
    disk: data.HOST_DISK_USED_PERCENT,
    http: data.HTTP_REQUESTS_1M,
    saf: data.SAF_QUEUE_DEPTH,
  };
  const value = map[key];
  return value == null || Number.isNaN(Number(value)) ? null : Number(value);
}

function mergeSeries(
  data: NodePerformanceSnapshot,
  prev: Record<SparkKey, TrendPoint[]>,
  now: number
): Record<SparkKey, TrendPoint[]> {
  const server = data.TRENDS;
  const next = { ...prev };
  for (const key of SPARK_KEYS) {
    if (server && Object.prototype.hasOwnProperty.call(server, key)) {
      next[key] = asPoints(server[key]) || [];
      continue;
    }
    const value = metricOf(data, key);
    next[key] = value == null ? prev[key] : pushPoint(prev[key], value, now);
  }
  return next;
}

function pushPoint(points: TrendPoint[], value: number, now: number): TrendPoint[] {
  const cut = now - TREND_WINDOW_MS;
  const next = points.length && points[points.length - 1].t === now
    ? points.slice(0, -1).concat({ t: now, v: value })
    : points.concat({ t: now, v: value });
  const pruned = next.filter((point) => point.t >= cut);
  return pruned.length > TREND_MAX_POINTS ? pruned.slice(pruned.length - TREND_MAX_POINTS) : pruned;
}

function emptyState(): PerformanceTrendState {
  return {
    snapshot: {},
    series: { cpu: [], rss: [], disk: [], http: [], saf: [] },
    errorStatus: null,
    errorMessage: null,
    updatedAt: null,
  };
}

async function tick() {
  if (inFlight) return;
  inFlight = true;
  try {
    const data = await getNodePerformance();
    const now = Date.now();
    state = {
      snapshot: data,
      errorStatus: null,
      errorMessage: null,
      updatedAt: now,
      series: mergeSeries(data, state.series, now),
    };
    emit();
  } catch (err: unknown) {
    const status = (err as { response?: { status?: number } })?.response?.status ?? null;
    state = {
      ...state,
      errorStatus: status,
      errorMessage: axiosErrorMessage(err, ""),
    };
    emit();
  } finally {
    inFlight = false;
  }
}

function arm() {
  if (timer) clearInterval(timer);
  timer = setInterval(() => {
    void tick();
  }, pollIntervalMs(Boolean(document.hidden)));
}

function onVisibility() {
  arm();
  if (!document.hidden) void tick();
}

export function subscribePerformanceTrends(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function getPerformanceTrendState(): PerformanceTrendState {
  return state;
}

export function startPerformanceTrendSampler(): void {
  if (started || typeof document === "undefined") return;
  started = true;
  void tick();
  arm();
  document.addEventListener("visibilitychange", onVisibility);
}

export function stopPerformanceTrendSampler(clear = false): void {
  started = false;
  if (timer) {
    clearInterval(timer);
    timer = undefined;
  }
  if (typeof document !== "undefined") {
    document.removeEventListener("visibilitychange", onVisibility);
  }
  if (clear) {
    state = emptyState();
    emit();
  }
}

export function refreshPerformanceTrends(): Promise<void> {
  return tick();
}

export function patchPerformanceCatalog(catalog: PerfAlarmsCatalog): void {
  state = { ...state, snapshot: { ...state.snapshot, PERF_ALARMS: catalog } };
  emit();
}

export function valuesOf(points: TrendPoint[] | undefined): number[] {
  return (points || []).map((point) => point.v);
}
