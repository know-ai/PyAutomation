import { type StripChartConfig } from "../components/StripChart";
import {
  DEFAULT_TIME_SPAN_MINUTES,
  normalizeTimeSpanMinutes,
  timeSpanFromLegacyBufferSize,
} from "../store/slices/tagsSlice";
import {
  clampBoxLegacy,
  clampBoxV3,
  DEFAULT_GRID_H,
  DEFAULT_GRID_W,
  GRID_COLS,
  GRID_ROW_HEIGHT,
  isLayoutV3Enabled,
  looksLikeLegacyBox,
  MAX_GRID_H,
  migrateBoxToLegacy,
  migrateBoxToV3,
  MIN_GRID_H,
  MIN_GRID_W,
  type GridMeta,
} from "../utils/realtimeTrendsGrid";
import { getTagsList, type Tag } from "./tags";
import api from "./api";

export const REALTIME_TRENDS_KIND = "real-time-trends" as const;
export const REALTIME_TRENDS_SCHEMA_VERSION = 3;
export const REALTIME_TRENDS_STORAGE_KEY = "pyautomation.workspace.realtime-trends.v1";
const LEGACY_STORAGE_KEY = "realTimeTrends_layout";

export const WORKSPACE_SCOPE = "station" as const;
export const MAX_STATION_CHARTS = 24;
const TITLE_MAX_LEN = 80;
const PUT_TIMEOUT_MS = 10_000;
const BREAKER_FAILS = 3;
const BREAKER_COOLDOWN_MS = 5 * 60_000;
const BREAKER_RETRY_MS = 60_000;

export type RealTimeTrendsWorkspace = {
  schemaVersion: number;
  kind: typeof REALTIME_TRENDS_KIND;
  /** Workstation/HMI client — not a logged-in user. */
  scope: typeof WORKSPACE_SCOPE;
  updatedAt: string;
  grid: GridMeta;
  panelTitle: string;
  charts: StripChartConfig[];
};

export type WorkspaceSyncStatus = "ok" | "offline" | "retrying";

type SyncListener = (status: WorkspaceSyncStatus) => void;

let _failCount = 0;
let _openUntil = 0;
let _syncStatus: WorkspaceSyncStatus = "ok";
const _syncListeners = new Set<SyncListener>();
let _retryTimer: ReturnType<typeof setInterval> | null = null;
let _pendingPersist: { charts: StripChartConfig[]; panelTitle: string } | null = null;

function emitSync(status: WorkspaceSyncStatus): void {
  _syncStatus = status;
  _syncListeners.forEach((listener) => {
    try {
      listener(status);
    } catch {
      /* ignore */
    }
  });
}

export function getWorkspaceSyncStatus(): WorkspaceSyncStatus {
  return _syncStatus;
}

export function subscribeWorkspaceSync(listener: SyncListener): () => void {
  _syncListeners.add(listener);
  listener(_syncStatus);
  return () => {
    _syncListeners.delete(listener);
  };
}

function stopRetryLoop(): void {
  if (typeof window === "undefined" || _retryTimer == null) return;
  window.clearInterval(_retryTimer);
  _retryTimer = null;
}

function ensureRetryLoop(): void {
  if (typeof window === "undefined" || _retryTimer != null) return;
  _retryTimer = window.setInterval(() => {
    if (_syncStatus === "ok") {
      stopRetryLoop();
      return;
    }
    if (Date.now() < _openUntil) return;
    const pending = _pendingPersist;
    if (!pending) return;
    emitSync("retrying");
    void persistStationRealtimeTrends(pending.charts, { panelTitle: pending.panelTitle });
  }, BREAKER_RETRY_MS);
}

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

function sanitizeOptionalTitle(value: unknown): string {
  if (typeof value !== "string") return "";
  return sanitizeTitle(value, "");
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

function sanitizeBool(value: unknown, fallback: boolean): boolean {
  if (typeof value === "boolean") return value;
  if (value === 1 || value === "1" || value === "true") return true;
  if (value === 0 || value === "0" || value === "false") return false;
  return fallback;
}

function readGrid(doc: Record<string, unknown> | null): GridMeta | null {
  const raw = doc?.grid;
  if (!raw || typeof raw !== "object") return null;
  const grid = raw as Record<string, unknown>;
  const cols = Number(grid.cols);
  const rowHeight = Number(grid.rowHeight);
  if (!Number.isFinite(cols) || !Number.isFinite(rowHeight)) return null;
  return { cols, rowHeight };
}

function sanitizeChart(
  raw: unknown,
  index: number,
  schemaVersion: number,
  grid: GridMeta | null,
  useV3: boolean
): StripChartConfig | null {
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
  let box = {
    x: clampInt(row.x, 0, 10_000, 0),
    y: clampInt(row.y, 0, 10_000, 0),
    w: clampInt(row.w, 1, 10_000, DEFAULT_GRID_W),
    h: clampInt(row.h, 1, 10_000, DEFAULT_GRID_H),
  };
  const legacy = looksLikeLegacyBox(box, schemaVersion, grid);
  if (legacy) {
    box = clampBoxLegacy(box);
    if (useV3) box = clampBoxV3(migrateBoxToV3(box));
  } else if (useV3) {
    box = clampBoxV3(box);
  } else {
    box = clampBoxLegacy(migrateBoxToLegacy(box));
  }
  return {
    id,
    title: sanitizeTitle(row.title, `Chart ${index + 1}`),
    tagNames: sanitizeTagNames(row.tagNames),
    timeSpanMinutes,
    showThresholds: sanitizeBool(row.showThresholds, true),
    x: box.x,
    y: box.y,
    w: box.w,
    h: box.h,
  };
}

function sanitizeCharts(
  value: unknown,
  schemaVersion: number,
  grid: GridMeta | null,
  useV3: boolean
): StripChartConfig[] {
  if (!Array.isArray(value)) return [];
  const charts: StripChartConfig[] = [];
  const ids = new Set<string>();
  for (const item of value) {
    const chart = sanitizeChart(item, charts.length, schemaVersion, grid, useV3);
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
  const useV3 = isLayoutV3Enabled();
  return {
    schemaVersion: useV3 ? REALTIME_TRENDS_SCHEMA_VERSION : 2,
    kind: REALTIME_TRENDS_KIND,
    scope: WORKSPACE_SCOPE,
    updatedAt: new Date().toISOString(),
    grid: useV3
      ? { cols: GRID_COLS, rowHeight: GRID_ROW_HEIGHT }
      : { cols: 12, rowHeight: 40 },
    panelTitle: "",
    charts: [],
  };
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
    const useV3 = isLayoutV3Enabled();
    const grid = readGrid(doc);
    return {
      schemaVersion: useV3 ? REALTIME_TRENDS_SCHEMA_VERSION : 2,
      kind: REALTIME_TRENDS_KIND,
      scope: WORKSPACE_SCOPE,
      updatedAt: typeof doc.updatedAt === "string" ? doc.updatedAt : new Date().toISOString(),
      grid: useV3
        ? { cols: GRID_COLS, rowHeight: GRID_ROW_HEIGHT }
        : { cols: 12, rowHeight: 40 },
      panelTitle: sanitizeOptionalTitle(doc.panelTitle),
      charts: sanitizeCharts(doc.charts, version, grid, useV3),
    };
  } catch {
    return null;
  }
}

function parseLegacyCharts(raw: string): StripChartConfig[] | null {
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return null;
    return sanitizeCharts(parsed, 1, null, isLayoutV3Enabled());
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

function buildDocument(
  charts: StripChartConfig[],
  panelTitle: string
): RealTimeTrendsWorkspace {
  const useV3 = isLayoutV3Enabled();
  return {
    schemaVersion: useV3 ? REALTIME_TRENDS_SCHEMA_VERSION : 2,
    kind: REALTIME_TRENDS_KIND,
    scope: WORKSPACE_SCOPE,
    updatedAt: new Date().toISOString(),
    grid: useV3
      ? { cols: GRID_COLS, rowHeight: GRID_ROW_HEIGHT }
      : { cols: 12, rowHeight: 40 },
    panelTitle: sanitizeOptionalTitle(panelTitle),
    charts: sanitizeCharts(
      charts,
      useV3 ? REALTIME_TRENDS_SCHEMA_VERSION : 2,
      useV3 ? { cols: GRID_COLS, rowHeight: GRID_ROW_HEIGHT } : { cols: 12, rowHeight: 40 },
      useV3
    ),
  };
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
      saveStationRealtimeTrends(migrated.charts, { panelTitle: migrated.panelTitle });
      return { ...migrated, updatedAt: new Date().toISOString() };
    }
  }

  return emptyWorkspace();
}

export function saveStationRealtimeTrends(
  charts: StripChartConfig[],
  extras?: { panelTitle?: string }
): boolean {
  const previous = loadStationRealtimeTrends();
  const document = buildDocument(charts, extras?.panelTitle ?? previous.panelTitle);
  return writeKey(REALTIME_TRENDS_STORAGE_KEY, JSON.stringify(document));
}

export function exportStationRealtimeTrends(
  charts: StripChartConfig[],
  extras?: { panelTitle?: string }
): string {
  const previous = loadStationRealtimeTrends();
  return JSON.stringify(
    buildDocument(charts, extras?.panelTitle ?? previous.panelTitle),
    null,
    2
  );
}

export function importStationRealtimeTrends(raw: string): RealTimeTrendsWorkspace | null {
  return parseWorkspace(raw);
}

async function getRemoteWorkspace(): Promise<RealTimeTrendsWorkspace | null> {
  try {
    const { data } = await api.get("/settings/workspace/realtime-trends", {
      timeout: PUT_TIMEOUT_MS,
    });
    return parseWorkspace(JSON.stringify(data));
  } catch {
    return null;
  }
}

async function putRemoteWorkspace(document: RealTimeTrendsWorkspace): Promise<boolean> {
  if (Date.now() < _openUntil) {
    emitSync("offline");
    return false;
  }
  try {
    await api.put("/settings/workspace/realtime-trends", document, {
      timeout: PUT_TIMEOUT_MS,
    });
    _failCount = 0;
    _openUntil = 0;
    stopRetryLoop();
    emitSync("ok");
    return true;
  } catch {
    _failCount += 1;
    if (_failCount >= BREAKER_FAILS) {
      _openUntil = Date.now() + BREAKER_COOLDOWN_MS;
      emitSync("offline");
      ensureRetryLoop();
    } else {
      emitSync("retrying");
      ensureRetryLoop();
    }
    return false;
  }
}

/** localStorage cache + station file on the server (`./db/`). */
export async function persistStationRealtimeTrends(
  charts: StripChartConfig[],
  extras?: { panelTitle?: string }
): Promise<boolean> {
  const previous = loadStationRealtimeTrends();
  const panelTitle = extras?.panelTitle ?? previous.panelTitle;
  _pendingPersist = { charts, panelTitle };
  const document = buildDocument(charts, panelTitle);
  const localOk = writeKey(REALTIME_TRENDS_STORAGE_KEY, JSON.stringify(document));
  const remoteOk = await putRemoteWorkspace(document);
  return localOk || remoteOk;
}

/**
 * Server is the station source of truth (survives host power cycle).
 * If the server is empty, migrate the browser cache once.
 */
export async function hydrateStationRealtimeTrends(): Promise<RealTimeTrendsWorkspace> {
  const local = loadStationRealtimeTrends();
  const remote = await getRemoteWorkspace();
  if (remote && remote.charts.length > 0) {
    saveStationRealtimeTrends(remote.charts, { panelTitle: remote.panelTitle });
    return remote;
  }
  if (local.charts.length > 0) {
    await persistStationRealtimeTrends(local.charts, { panelTitle: local.panelTitle });
    return local;
  }
  return remote ?? local;
}

export function createStationChartId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `stripchart-${crypto.randomUUID()}`;
  }
  return `stripchart-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export function createDefaultStripChart(title: string, y: number): StripChartConfig {
  const useV3 = isLayoutV3Enabled();
  return {
    id: createStationChartId(),
    title,
    tagNames: [],
    timeSpanMinutes: DEFAULT_TIME_SPAN_MINUTES,
    showThresholds: true,
    x: 0,
    y,
    w: useV3 ? DEFAULT_GRID_W : 6,
    h: useV3 ? DEFAULT_GRID_H : 6,
  };
}

let _catalog: Tag[] | null = null;
let _catalogPromise: Promise<Tag[]> | null = null;

export function peekStationTagCatalog(): Tag[] | null {
  return _catalog;
}

export function loadStationTagCatalog(force = false): Promise<Tag[]> {
  if (!force && _catalog) return Promise.resolve(_catalog);
  if (!force && _catalogPromise) return _catalogPromise;
  _catalogPromise = getTagsList()
    .then((tags) => {
      _catalog = tags || [];
      return _catalog;
    })
    .catch((error) => {
      _catalogPromise = null;
      throw error;
    });
  return _catalogPromise;
}

export { MIN_GRID_H, MIN_GRID_W, MAX_GRID_H, GRID_COLS, GRID_ROW_HEIGHT };
