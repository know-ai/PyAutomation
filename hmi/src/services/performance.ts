import api from "./api";

export type NodeClockMetrics = {
  enabled?: boolean;
  synced?: boolean | null;
  warn?: boolean;
  offset_ms?: number | null;
};

export type NodePerformanceSnapshot = {
  status?: string;
  METRICS_AGE_MS?: number | null;
  NODE_ID?: string | null;
  NODE_AREA?: string | null;
  NODE_SITE?: string | null;
  MULTI_EDGE_ENABLED?: boolean;
  uptime_s?: number | null;
  HOST_RSS_MB?: number | null;
  HOST_CPU_PERCENT?: number | null;
  HOST_DISK_FREE_GB?: number | null;
  HOST_DISK_USED_PERCENT?: number | null;
  HOST_THREADS?: number | null;
  HTTP_REQUESTS_TOTAL?: number | null;
  HTTP_REQUESTS_1M?: number | null;
  HTTP_5XX_TOTAL?: number | null;
  HTTP_5XX_1M?: number | null;
  HTTP_IN_FLIGHT?: number | null;
  HMI_ACTIVE_CLIENTS?: number | null;
  HMI_SESSIONS_SAMPLE_AGE_MS?: number | null;
  DB_CONNECTED?: boolean | null;
  DB_LATENCY_MS?: number | null;
  DB_ACTIVE_CONNECTIONS?: number | null;
  DB_CONNECTIONS_LOCAL?: number | null;
  DB_TXN_PER_MIN?: number | null;
  DB_DISK_FREE_GB?: number | null;
  SAF_QUEUE_DEPTH?: number | null;
  SAF_REPLICATION_LAG_MS?: number | null;
  SAF_DISK_BYTES?: number | null;
  OPC_MONITORED_COUNT?: number | null;
  CVT_TAG_COUNT?: number | null;
  CVT_LOCK_CONTENTION?: number | null;
  SAMPLE_LAG_MS?: number | null;
  ACQUISITION_READY?: boolean | null;
  CATALOG_PENDING_ROWS?: number | null;
  CATALOG_ORPHAN_ROWS?: number | null;
  CATALOG_LAST_SYNC?: string | null;
  CATALOG_SYNC_ERRORS?: number | null;
  CATALOG_ORPHAN_ALARM?: boolean | null;
  DERIVED_TAGS_COUNT?: number | null;
  WORKERS?: Record<string, { name?: string; state?: string; last_cycle_utc?: string | null }>;
  clock?: NodeClockMetrics;
  PERF_ALARMS?: PerfAlarmsCatalog;
  TRENDS?: Partial<Record<"cpu" | "rss" | "disk" | "http" | "saf", { t: number; v: number }[]>>;
  message?: string;
};

export type PerfAlarmCatalogEntry = {
  key: string;
  field?: string;
  enabled?: boolean;
  threshold?: number | null;
  unit?: string;
  alarm?: string;
  tag?: string;
};

export type PerfAlarmsCatalog = {
  enabled?: boolean;
  debounce_count?: number;
  alarms?: PerfAlarmCatalogEntry[];
};

export const PERF_ALARM_KEYS = [
  "cpu",
  "disk",
  "saf_queue",
  "saf_lag",
  "metrics_age",
  "db_conn",
  "http_5xx",
  "field_stale",
  "saf_deadletter",
  "hub_lag",
  "saf_shed",
  "saf_ingest",
  "saf_rate",
] as const;

export type PerfAlarmKey = (typeof PERF_ALARM_KEYS)[number];

export const FOCUS_POLL_MS = 3000;
export const HIDDEN_POLL_MS = 30000;
export const SPARKLINE_POINTS = 60;

export function pollIntervalMs(hidden: boolean): number {
  return hidden ? HIDDEN_POLL_MS : FOCUS_POLL_MS;
}

export function pushRing(values: number[], next: number, max = SPARKLINE_POINTS): number[] {
  const out = values.length >= max ? values.slice(values.length - max + 1) : values.slice();
  out.push(next);
  return out;
}

export { canViewPerformance, canControlOps, canDestroyOps } from "../utils/access";

export async function getNodePerformance(): Promise<NodePerformanceSnapshot> {
  const { data } = await api.get("/health/node", { timeout: 4000 });
  return data as NodePerformanceSnapshot;
}
