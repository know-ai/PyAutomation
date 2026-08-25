import { createSlice, PayloadAction } from "@reduxjs/toolkit";
import type { Tag } from "../../services/tags";
import { logout } from "./authSlice";

/** Opciones de ventana temporal en la HMI (minutos). */
export const TIME_SPAN_OPTIONS_MINUTES = [1, 2, 3, 5] as const;
export type TimeSpanMinutes = (typeof TIME_SPAN_OPTIONS_MINUTES)[number];
export const DEFAULT_TIME_SPAN_MINUTES: TimeSpanMinutes = 2;
/** Máximo time span seleccionable → retención de seguridad en Redux. */
export const MAX_HISTORY_TIME_MS =
  Math.max(...TIME_SPAN_OPTIONS_MINUTES) * 60 * 1000;
/** Tope de tags con historial (LRU de no suscritos). */
export const MAX_HISTORY_TAGS = 64;
export const HISTORY_STORAGE_KEY = "pyautomation.tagHistory";
/** Tope de muestras encoladas por tag entre flushes (CA-RT-5). */
export const HISTORY_POINTS_PER_FLUSH = 20;
/** Persistencia: solo series suscritas / recientes. */
export const HISTORY_PERSIST_MAX_TAGS = 24;
/** ~5 min @ 1 Hz (máximo time span de UI). */
export const HISTORY_PERSIST_MAX_POINTS = 300;

/** @deprecated Preferir poda por tiempo; alias de compatibilidad. */
export const MAX_HISTORY_POINTS = HISTORY_PERSIST_MAX_POINTS;

export interface TagHistoryPoint {
  timestamp: string;
  value: number;
}

interface TagsState {
  tagValues: Record<string, Tag>;
  tagHistory: Record<string, TagHistoryPoint[]>;
  historySubscribers: Record<string, number>;
}

const isValidPoint = (pt: unknown): pt is TagHistoryPoint => {
  if (!pt || typeof pt !== "object") return false;
  const p = pt as TagHistoryPoint;
  return (
    typeof p.timestamp === "string" &&
    typeof p.value === "number" &&
    !Number.isNaN(p.value)
  );
};

/** Epoch ms from a history point timestamp (NaN if unparseable). */
export function pointTimeMs(pt: TagHistoryPoint): number {
  const ms = Date.parse(pt.timestamp);
  return Number.isFinite(ms) ? ms : NaN;
}

/** Normalize any parseable timestamp string to UTC ISO millis (matches on.tag). */
export function normalizeHistoryTimestamp(raw: string): string | null {
  if (!raw || typeof raw !== "string") return null;
  const ms = Date.parse(raw);
  if (!Number.isFinite(ms)) return null;
  return new Date(ms).toISOString();
}

/**
 * Descarta puntos anteriores a ``nowMs - timeSpanMs``.
 * Ancla en reloj de pared para que tags inactivos vacíen el buffer.
 * El array se asume ordenado por timestamp ascendente.
 */
export function pruneHistoryByTime(
  history: TagHistoryPoint[],
  timeSpanMs: number,
  nowMs: number = Date.now()
): TagHistoryPoint[] {
  if (!history.length || timeSpanMs <= 0) return [];
  const cutoff = nowMs - timeSpanMs;
  let lo = 0;
  let hi = history.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    const t = pointTimeMs(history[mid]);
    if (!Number.isFinite(t) || t < cutoff) lo = mid + 1;
    else hi = mid;
  }
  return lo === 0 ? history : history.slice(lo);
}

export const normalizeTimeSpanMinutes = (value: unknown): TimeSpanMinutes => {
  const n = typeof value === "number" ? value : Number(value);
  if (
    TIME_SPAN_OPTIONS_MINUTES.includes(n as TimeSpanMinutes)
  ) {
    return n as TimeSpanMinutes;
  }
  return DEFAULT_TIME_SPAN_MINUTES;
};

/** Migra configs antiguas con bufferSize (puntos) a minutos. */
export const timeSpanFromLegacyBufferSize = (bufferSize: unknown): TimeSpanMinutes => {
  const n = typeof bufferSize === "number" ? bufferSize : Number(bufferSize);
  if (!Number.isFinite(n)) return DEFAULT_TIME_SPAN_MINUTES;
  if (n <= 90) return 1;
  if (n <= 150) return 2;
  if (n <= 240) return 3;
  return 5;
};

const trimHistory = (pts: TagHistoryPoint[], nowMs: number = Date.now()): TagHistoryPoint[] =>
  pruneHistoryByTime(pts, MAX_HISTORY_TIME_MS, nowMs);

export const mergeHistoryPoints = (
  existing: TagHistoryPoint[],
  incoming: TagHistoryPoint[]
): TagHistoryPoint[] => {
  if (incoming.length === 0) return trimHistory(existing);
  if (existing.length === 0) {
    return trimHistory(
      incoming
        .filter(isValidPoint)
        .map((p) => {
          const ts = normalizeHistoryTimestamp(p.timestamp) || p.timestamp;
          return { timestamp: ts, value: p.value };
        })
    );
  }

  // Dedupe by epoch ms so ISO (socket) and legacy display formats collapse.
  const byMs = new Map<number, TagHistoryPoint>();
  const ingest = (p: TagHistoryPoint) => {
    if (!isValidPoint(p)) return;
    const iso = normalizeHistoryTimestamp(p.timestamp);
    const ms = iso ? Date.parse(iso) : pointTimeMs(p);
    if (!Number.isFinite(ms)) return;
    byMs.set(ms, { timestamp: iso || p.timestamp, value: p.value });
  };
  for (const p of existing) ingest(p);
  for (const p of incoming) ingest(p);
  const merged = Array.from(byMs.entries())
    .sort((a, b) => a[0] - b[0])
    .map(([, point]) => point);
  return trimHistory(merged);
};

const lastTimestamp = (pts: TagHistoryPoint[] | undefined): string => {
  if (!pts || pts.length === 0) return "";
  return pts[pts.length - 1]?.timestamp || "";
};

export const evictExcessHistory = (
  history: Record<string, TagHistoryPoint[]>,
  subscribers: Record<string, number> = {}
): Record<string, TagHistoryPoint[]> => {
  const names = Object.keys(history);
  if (names.length <= MAX_HISTORY_TAGS) return history;
  const overflow = names.length - MAX_HISTORY_TAGS;
  const ranked = names
    .filter((n) => !subscribers[n])
    .sort((a, b) => lastTimestamp(history[a]).localeCompare(lastTimestamp(history[b])));
  const next = { ...history };
  for (let i = 0; i < overflow && i < ranked.length; i++) {
    delete next[ranked[i]];
  }
  return next;
};

export const loadPersistedTagHistory = (): Record<string, TagHistoryPoint[]> => {
  try {
    if (typeof localStorage === "undefined") return {};
    const raw = localStorage.getItem(HISTORY_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    const out: Record<string, TagHistoryPoint[]> = {};
    const now = Date.now();
    for (const [name, pts] of Object.entries(parsed)) {
      if (typeof name !== "string" || !name || !Array.isArray(pts)) continue;
      out[name] = trimHistory(pts.filter(isValidPoint), now);
    }
    return evictExcessHistory(out);
  } catch (_e) {
    return {};
  }
};

export const persistTagHistory = (
  history: Record<string, TagHistoryPoint[]>,
  subscribers: Record<string, number> = {}
): void => {
  if (typeof localStorage === "undefined") return;
  const preferred = Object.keys(history)
    .filter((name) => (subscribers[name] || 0) > 0)
    .sort();
  const others = Object.keys(history)
    .filter((name) => !(subscribers[name] > 0))
    .sort((a, b) => lastTimestamp(history[b]).localeCompare(lastTimestamp(history[a])));
  const keepNames = [...preferred, ...others].slice(0, HISTORY_PERSIST_MAX_TAGS);
  const now = Date.now();
  const payload: Record<string, TagHistoryPoint[]> = {};
  for (const name of keepNames) {
    const pts = trimHistory(history[name] || [], now);
    payload[name] =
      pts.length > HISTORY_PERSIST_MAX_POINTS
        ? pts.slice(pts.length - HISTORY_PERSIST_MAX_POINTS)
        : pts;
  }
  try {
    localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(payload));
  } catch (_e) {
    const names = Object.keys(payload).sort(
      (a, b) => lastTimestamp(payload[a]).localeCompare(lastTimestamp(payload[b]))
    );
    const keep = names.slice(Math.floor(names.length / 2));
    const reduced: Record<string, TagHistoryPoint[]> = {};
    keep.forEach((n) => {
      reduced[n] = payload[n];
    });
    try {
      localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(reduced));
    } catch (_retry) {
      try {
        localStorage.removeItem(HISTORY_STORAGE_KEY);
      } catch (_ignore) {
        // quota / private mode
      }
    }
  }
};

export const isTagHistoryTracked = (
  subscribers: Record<string, number>,
  history: Record<string, TagHistoryPoint[]>,
  name: string
): boolean => !!subscribers[name] || Array.isArray(history[name]);

const tagToHistoryPoint = (tag: Tag): TagHistoryPoint | null => {
  if (!tag.name || tag.value === undefined || tag.value === null) return null;
  const numericValue =
    typeof tag.value === "boolean" ? (tag.value ? 1 : 0) : Number(tag.value);
  if (Number.isNaN(numericValue)) return null;
  const timestamp =
    typeof tag.timestamp === "string" ? tag.timestamp : new Date().toISOString();
  return { timestamp, value: numericValue };
};

const appendPointsToHistory = (state: TagsState, name: string, tags: Tag[]) => {
  if (!name || tags.length === 0) return;
  if (!isTagHistoryTracked(state.historySubscribers, state.tagHistory, name)) return;
  const history = state.tagHistory[name] || [];
  for (const tag of tags) {
    const point = tagToHistoryPoint(tag);
    if (!point) continue;
    history.push(point);
  }
  state.tagHistory[name] = trimHistory(history);
  if (Object.keys(state.tagHistory).length > MAX_HISTORY_TAGS) {
    state.tagHistory = evictExcessHistory(state.tagHistory, state.historySubscribers);
  }
};

const initialState: TagsState = {
  tagValues: {},
  tagHistory: loadPersistedTagHistory(),
  historySubscribers: {},
};

const tagsSlice = createSlice({
  name: "tags",
  initialState,
  reducers: {
    updateTagValue: (state, action: PayloadAction<Tag>) => {
      const tag = action.payload;
      if (tag.name) {
        state.tagValues[tag.name] = tag;
      }
    },
    updateTagValuesBatch: (state, action: PayloadAction<Tag[]>) => {
      action.payload.forEach((tag) => {
        if (tag.name) {
          state.tagValues[tag.name] = tag;
        }
      });
    },
    appendTagHistoryPoints: (
      state,
      action: PayloadAction<Array<{ name: string; points: Tag[] }>>
    ) => {
      action.payload.forEach(({ name, points }) => {
        appendPointsToHistory(state, name, points);
      });
    },
    backfillTagHistory: (
      state,
      action: PayloadAction<Record<string, TagHistoryPoint[]>>
    ) => {
      for (const [name, points] of Object.entries(action.payload)) {
        if (!state.historySubscribers[name]) continue;
        const existing = state.tagHistory[name] || [];
        state.tagHistory[name] = mergeHistoryPoints(existing, points);
      }
      if (Object.keys(state.tagHistory).length > MAX_HISTORY_TAGS) {
        state.tagHistory = evictExcessHistory(state.tagHistory, state.historySubscribers);
      }
    },
    subscribeTagHistory: (state, action: PayloadAction<string>) => {
      const name = action.payload;
      if (!name) return;
      state.historySubscribers[name] = (state.historySubscribers[name] || 0) + 1;
      if (!state.tagHistory[name]) {
        state.tagHistory[name] = [];
      }
      if (Object.keys(state.tagHistory).length > MAX_HISTORY_TAGS) {
        state.tagHistory = evictExcessHistory(state.tagHistory, state.historySubscribers);
      }
    },
    unsubscribeTagHistory: (state, action: PayloadAction<string>) => {
      const name = action.payload;
      if (!name) return;
      const next = (state.historySubscribers[name] || 1) - 1;
      if (next <= 0) {
        delete state.historySubscribers[name];
      } else {
        state.historySubscribers[name] = next;
      }
    },
    clearTagValues: (state) => {
      state.tagValues = {};
      state.historySubscribers = {};
    },
  },
  extraReducers: (builder) => {
    builder.addCase(logout, (state) => {
      persistTagHistory(state.tagHistory, state.historySubscribers);
      state.tagValues = {};
      state.historySubscribers = {};
    });
  },
});

export const {
  updateTagValue,
  updateTagValuesBatch,
  appendTagHistoryPoints,
  backfillTagHistory,
  subscribeTagHistory,
  unsubscribeTagHistory,
  clearTagValues,
} = tagsSlice.actions;
export default tagsSlice.reducer;
