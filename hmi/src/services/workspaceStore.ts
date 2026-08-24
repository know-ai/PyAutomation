import { type StripChartConfig } from "../components/StripChart";
import {
  DEFAULT_TIME_SPAN_MINUTES,
  normalizeTimeSpanMinutes,
  timeSpanFromLegacyBufferSize,
} from "../store/slices/tagsSlice";
import api from "./api";

export const REALTIME_TRENDS_KIND = "real-time-trends" as const;
export const REALTIME_TRENDS_SCHEMA_VERSION = 2;
export const REALTIME_TRENDS_STORAGE_KEY = "pyautomation.workspace.realtime-trends.v1";
const LEGACY_STORAGE_KEY = "realTimeTrends_layout";

export const WORKSPACE_SCOPE = "station" as const;
export const MAX_STATION_CHARTS = 24;
const TITLE_MAX_LEN = 80;
const MIN_GRID_W = 4;
const MAX_GRID_W = 12;
const MIN_GRID_H = 6;

export type RealTimeTrendsWorkspace = {
  schemaVersion: number;
  kind: typeof REALTIME_TRENDS_KIND;
  /** Workstation/HMI client — not a logged-in user. */
  scope: typeof WORKSPACE_SCOPE;
  updatedAt: string;
  charts: StripChartConfig[];
};

function clampInt(value: unknown, min: number, max: number, fallback: number): number {
  const parsed = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(max, Math.max(min, Math.trunc(parsed)));
}

function sanitizeTitle(value: unknown, fallback: string): string {
  if (typeof value !== "string") return fallback;
  const trimmed = value.replace(/[\u0000-\u001F\u007F]/g, "").trim();
  if (!trimmed) return fallback;
  return trimmed.slice(0, TITLE_MAX_LEN);
}

function sanitizeTagNames(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  const names: string[] = [];
  const seen = new Set<string>();
  for (const item of value) {
    if (typeof item !== "string") continue;
    const name = item.trim();
    if (!name || seen.has(name)) continue;
    seen.add(name);
    names.push(name);
    if (names.length >= 16) break;
  }
  return names;
}

function sanitizeChart(raw: unknown, index: number): StripChartConfig | null {
  if (!raw || typeof raw !== "object") return null;
  const row = raw as Record<string, unknown>;
  const id =
    typeof row.id === "string" && row.id.trim()
      ? row.id.trim().slice(0, 80)
      : `stripchart-${index + 1}`;
  const timeSpanMinutes =
    row.timeSpanMinutes != null
      ? normalizeTimeSpanMinutes(row.timeSpanMinutes)
      : row.bufferSize != null
        ? timeSpanFromLegacyBufferSize(row.bufferSize)
        : DEFAULT_TIME_SPAN_MINUTES;
  return {
    id,
    title: sanitizeTitle(row.title, `Chart ${index + 1}`),
    tagNames: sanitizeTagNames(row.tagNames),
    timeSpanMinutes,
    x: clampInt(row.x, 0, MAX_GRID_W - MIN_GRID_W, 0),
    y: clampInt(row.y, 0, 10_000, 0),
    w: clampInt(row.w, MIN_GRID_W, MAX_GRID_W, 6),
    h: clampInt(row.h, MIN_GRID_H, 48, MIN_GRID_H),
  };
}

function sanitizeCharts(value: unknown): StripChartConfig[] {
  if (!Array.isArray(value)) return [];
  const charts: StripChartConfig[] = [];
  const ids = new Set<string>();
  for (const item of value) {
    const chart = sanitizeChart(item, charts.length);
    if (!chart) continue;
    let id = chart.id;
    if (ids.has(id)) id = `${id}-${charts.length}`;
    ids.add(id);
    charts.push({ ...chart, id });
    if (charts.length >= MAX_STATION_CHARTS) break;
  }
  return charts;
}

function emptyWorkspace(): RealTimeTrendsWorkspace {
  return {
    schemaVersion: REALTIME_TRENDS_SCHEMA_VERSION,
    kind: REALTIME_TRENDS_KIND,
    scope: WORKSPACE_SCOPE,
    updatedAt: new Date().toISOString(),
    charts: [],
  };
}

function parseLegacyCharts(raw: string): StripChartConfig[] | null {
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return null;
    return sanitizeCharts(parsed);
  } catch {
    return null;
  }
}

function parseWorkspace(raw: string): RealTimeTrendsWorkspace | null {
  try {
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return null;
    const doc = parsed as Record<string, unknown>;
    if (doc.kind != null && doc.kind !== REALTIME_TRENDS_KIND) return null;
    const version = Number(doc.schemaVersion ?? 1);
    if (!Number.isFinite(version) || version > REALTIME_TRENDS_SCHEMA_VERSION) {
      return null;
    }
    return {
      schemaVersion: REALTIME_TRENDS_SCHEMA_VERSION,
      kind: REALTIME_TRENDS_KIND,
      scope: WORKSPACE_SCOPE,
      updatedAt: typeof doc.updatedAt === "string" ? doc.updatedAt : new Date().toISOString(),
      charts: sanitizeCharts(doc.charts),
    };
  } catch {
    return null;
  }
}

function readKey(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeKey(key: string, value: string): boolean {
  try {
    localStorage.setItem(key, value);
    const roundTrip = localStorage.getItem(key);
    return roundTrip === value;
  } catch {
    return false;
  }
}

export function loadStationRealtimeTrends(): RealTimeTrendsWorkspace {
  const current = readKey(REALTIME_TRENDS_STORAGE_KEY);
  if (current) {
    const parsed = parseWorkspace(current);
    if (parsed) return parsed;
  }

  const legacy = readKey(LEGACY_STORAGE_KEY);
  if (legacy) {
    const charts = parseLegacyCharts(legacy);
    if (charts && charts.length > 0) {
      const migrated: RealTimeTrendsWorkspace = {
        ...emptyWorkspace(),
        charts,
      };
      saveStationRealtimeTrends(migrated.charts);
      return { ...migrated, updatedAt: new Date().toISOString() };
    }
  }

  return emptyWorkspace();
}

export function saveStationRealtimeTrends(charts: StripChartConfig[]): boolean {
  const document: RealTimeTrendsWorkspace = {
    schemaVersion: REALTIME_TRENDS_SCHEMA_VERSION,
    kind: REALTIME_TRENDS_KIND,
    scope: WORKSPACE_SCOPE,
    updatedAt: new Date().toISOString(),
    charts: sanitizeCharts(charts),
  };
  const serialized = JSON.stringify(document);
  return writeKey(REALTIME_TRENDS_STORAGE_KEY, serialized);
}

async function getRemoteWorkspace(): Promise<RealTimeTrendsWorkspace | null> {
  try {
    const { data } = await api.get("/settings/workspace/realtime-trends");
    return parseWorkspace(JSON.stringify(data));
  } catch {
    return null;
  }
}

async function putRemoteWorkspace(charts: StripChartConfig[]): Promise<boolean> {
  try {
    const document: RealTimeTrendsWorkspace = {
      schemaVersion: REALTIME_TRENDS_SCHEMA_VERSION,
      kind: REALTIME_TRENDS_KIND,
      scope: WORKSPACE_SCOPE,
      updatedAt: new Date().toISOString(),
      charts: sanitizeCharts(charts),
    };
    await api.put("/settings/workspace/realtime-trends", document);
    return true;
  } catch {
    return false;
  }
}

/** localStorage cache + station file on the server (`./db/`). */
export async function persistStationRealtimeTrends(charts: StripChartConfig[]): Promise<boolean> {
  const localOk = saveStationRealtimeTrends(charts);
  const remoteOk = await putRemoteWorkspace(charts);
  return localOk || remoteOk;
}

/**
 * Server is the station source of truth (survives host power cycle).
 * If the server is empty, migrate the browser cache once.
 */
export async function hydrateStationRealtimeTrends(): Promise<StripChartConfig[]> {
  const local = loadStationRealtimeTrends();
  const remote = await getRemoteWorkspace();
  if (remote && remote.charts.length > 0) {
    saveStationRealtimeTrends(remote.charts);
    return remote.charts;
  }
  if (local.charts.length > 0) {
    await putRemoteWorkspace(local.charts);
    return local.charts;
  }
  return remote ? remote.charts : local.charts;
}

export function createStationChartId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `stripchart-${crypto.randomUUID()}`;
  }
  return `stripchart-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

